"""Azure ML pipeline generation from Kedro pipelines."""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from azure.ai.ml import (
    Input,
    MpiDistribution,
    Output,
    PyTorchDistribution,
    TensorFlowDistribution,
    command,
)
from azure.ai.ml.dsl import pipeline as azure_pipeline
from azure.ai.ml.entities import CommandJobLimits, Environment, Job
from azure.ai.ml.entities._builders import Command
from kedro.io import DataCatalog
from kedro.pipeline import Pipeline
from kedro.pipeline.node import Node

from kedro_azureml_pipeline.config import (
    ClusterConfig,
    KedroAzureMLConfig,
    LimitsConfig,
    NotificationConfig,
    PipelineFilterOptions,
)
from kedro_azureml_pipeline.constants import (
    DISTRIBUTED_CONFIG_FIELD,
    KEDRO_AZUREML_MLFLOW_ENABLED,
    KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME,
    KEDRO_AZUREML_MLFLOW_NODE_NAME,
    KEDRO_AZUREML_MLFLOW_RUN_NAME,
    KEDRO_AZUREML_NOTIFY,
    KEDRO_AZUREML_NOTIFY_OUTCOME,
    KEDRO_AZUREML_NOTIFY_SIBLINGS,
    KEDRO_AZUREML_NOTIFY_START,
    PARAMS_PREFIX,
)
from kedro_azureml_pipeline.datasets import AzureMLAssetDataset, AzureMLDatastoreDataset
from kedro_azureml_pipeline.distributed import DistributedNodeConfig
from kedro_azureml_pipeline.distributed.config import Framework

logger = logging.getLogger(__name__)

#: Appended to every step command. Azure ML surfaces a signal death as a bare
#: nonzero exit, so the one fact that matters for diagnosis, which signal, never
#: reaches the failure page. It has to be classified in the shell: nothing inside
#: the Python process survives a SIGSEGV or SIGKILL to report it.
EXIT_CLASSIFICATION_SUFFIX = (
    '; rc=$?; if [ "$rc" -gt 128 ]; then '
    'echo "kedro azureml execute: killed by signal $((rc-128)) (SIG$(kill -l $((rc-128)))). '
    "A signal death is a native crash or an external kill (out-of-memory, preemption); "
    'the Python-level traceback, if any, is in user_logs/std_log_process_*.txt" >&2; '
    "fi; exit $rc"
)


class ConfigException(BaseException):
    """Raised when pipeline generator configuration is invalid.

    See Also
    --------
    [AzureMLPipelineGenerator][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] : Generator that raises this.
    """

    pass


@dataclass(frozen=True)
class NotificationRoles:
    """Which steps of a job speak for it.

    Parameters
    ----------
    announcer : str
        Name of the root node whose step posts ``start``.
    poster : str
        Name of the leaf node whose step posts the outcome.
    siblings : tuple of str
        Names of the other leaf nodes the poster waits for.

    See Also
    --------
    [AzureMLPipelineGenerator][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] : Computes the roles.
    [NotificationHook][kedro_azureml_pipeline.hooks.NotificationHook] : Reads them from the step environment.
    """

    announcer: str
    poster: str
    siblings: tuple[str, ...]


class AzureMLPipelineGenerator:
    """Translate a Kedro pipeline into an Azure ML pipeline job.

    Parameters
    ----------
    pipeline_name : str
        Registered Kedro pipeline name.
    kedro_environment : str
        Kedro environment name.
    config : KedroAzureMLConfig
        Validated plugin configuration.
    kedro_params : dict of str to Any
        Resolved Kedro parameters.
    catalog : DataCatalog
        Kedro data catalog.
    aml_env : str or None
        Azure ML environment override.
    params : str or None
        Raw parameter string forwarded to ``kedro run``.
    extra_env : dict of str to str or None
        Additional environment variables for Azure ML commands.
    load_versions : dict of str to str or None
        Pinned dataset versions.
    filter_options : PipelineFilterOptions or None
        Node/tag filtering options.
    mlflow_run_name : str or None
        MLflow run name override.
    experiment_name : str or None
        Azure ML experiment name (enables MLflow tracking when set).
    limits_config : LimitsConfig or None
        Run-duration limits applied to every step in the pipeline.
    code : str or None
        Code reference for every step, typically the id of a registered
        code asset. When ``None``, each step carries
        ``execution.code_directory`` and Azure ML resolves it per step.
    notification_config : NotificationConfig or None
        Webhook notification definition stamped into every step, or ``None``.
    job_name : str or None
        Name of the job being generated, carried in the notification payloads.
    display_name : str or None
        Display name of the job, carried in the notification payloads.

    See Also
    --------
    [KedroAzureMLConfig][kedro_azureml_pipeline.config.KedroAzureMLConfig] : Plugin configuration consumed here.
    [AzureMLPipelinesClient][kedro_azureml_pipeline.client.AzureMLPipelinesClient] : Submits the generated pipeline.
    [AzurePipelinesRunner][kedro_azureml_pipeline.runner.AzurePipelinesRunner] : Executes nodes within Azure ML.
    [AzureMLAssetDataset][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] : Datasets wired into the pipeline.
    """

    def __init__(
        self,
        pipeline_name: str,
        kedro_environment: str,
        config: KedroAzureMLConfig,
        kedro_params: dict[str, Any],
        catalog: DataCatalog,
        aml_env: str | None = None,
        params: str | None = None,
        extra_env: dict[str, str] | None = None,
        load_versions: dict[str, str] | None = None,
        filter_options: PipelineFilterOptions | None = None,
        mlflow_run_name: str | None = None,
        experiment_name: str | None = None,
        limits_config: LimitsConfig | None = None,
        code: str | None = None,
        notification_config: NotificationConfig | None = None,
        job_name: str | None = None,
        display_name: str | None = None,
    ):
        if load_versions is None:
            load_versions = {}
        if extra_env is None:
            extra_env = {}
        self.kedro_environment = kedro_environment
        self.code = code

        self.params = params
        self.kedro_params = kedro_params
        self.catalog = catalog
        self.aml_env = aml_env
        self.config = config
        self.pipeline_name = pipeline_name
        self.extra_env = extra_env
        self.load_versions = load_versions
        self.filter_options = filter_options
        self.mlflow_run_name = mlflow_run_name
        self.experiment_name = experiment_name
        self.limits_config = limits_config
        self.notification_config = notification_config
        self.job_name = job_name
        self.display_name = display_name

    def generate(self) -> Job:
        """Build and return the Azure ML pipeline ``Job``.

        Returns
        -------
        Job
            Compiled Azure ML pipeline job ready for submission.
        """
        pipeline = self.get_kedro_pipeline()
        if self.filter_options:
            filter_kwargs = self.filter_options.to_filter_kwargs()
            if filter_kwargs:
                pipeline = pipeline.filter(**filter_kwargs)
        kedro_azure_run_id = uuid4().hex
        roles = self.notification_roles(pipeline)

        logger.info(f"Translating {self.pipeline_name} to Azure ML Pipeline")

        def kedro_azure_pipeline_fn():
            """Build Azure ML pipeline components from Kedro nodes."""
            commands = {}

            for node in pipeline.nodes:
                azure_command = self._construct_azure_command(pipeline, node, kedro_azure_run_id, roles)

                commands[node.name] = azure_command

            # wire the commands into execution graph
            invoked_components = self._connect_commands(pipeline, commands)

            # pipeline outputs
            azure_pipeline_outputs = self._gather_pipeline_outputs(pipeline, invoked_components)
            return azure_pipeline_outputs

        # azure-ai-ml's @pipeline decorator has incomplete overload stubs; the call is valid at runtime.
        pipeline_decorator = azure_pipeline(name=self.pipeline_name)  # ty: ignore[no-matching-overload]
        kedro_azure_pipeline = pipeline_decorator(kedro_azure_pipeline_fn)

        azure_pipeline_job: Job = kedro_azure_pipeline()
        return azure_pipeline_job

    def notification_roles(self, pipeline: Pipeline) -> NotificationRoles | None:
        """Designate the announcer and poster steps of *pipeline*.

        The announcer is the first root in topological order and the poster the
        last leaf, ties broken by node name, so the same pipeline always yields
        the same roles. A single-node pipeline is both.

        Parameters
        ----------
        pipeline : Pipeline
            The filtered Kedro pipeline about to be translated.

        Returns
        -------
        NotificationRoles or None
            The roles, or ``None`` when the job has no notification definition.

        Raises
        ------
        ConfigException
            If ``success`` is enabled on a pipeline with several leaves and the
            job declares no experiment name. The poster identifies its sibling
            leaves through the MLflow integration, which only an experiment
            name activates, so without one it would wait out its cap on every run.
        """
        if self.notification_config is None:
            return None
        dependencies = pipeline.node_dependencies
        topo_index = {node: index for index, group in enumerate(pipeline.grouped_nodes) for node in group}
        has_dependants = {parent for parents in dependencies.values() for parent in parents}
        roots = [node for node in pipeline.nodes if not dependencies[node]]
        leaves = [node for node in pipeline.nodes if node not in has_dependants]
        if len(leaves) > 1 and "success" in self.notification_config.events and not self.experiment_name:
            raise ConfigException(
                f"Job '{self.job_name}' enables the 'success' notification on a pipeline with {len(leaves)} leaf "
                "nodes but declares no experiment_name. The outcome step identifies its sibling leaves through "
                "the MLflow integration, which an experiment name activates."
            )
        announcer = min(roots, key=lambda node: (topo_index[node], node.name))
        poster = max(leaves, key=lambda node: (topo_index[node], node.name))
        siblings = tuple(sorted(node.name for node in leaves if node is not poster))
        return NotificationRoles(announcer=announcer.name, poster=poster.name, siblings=siblings)

    def _notification_env(self, node: Node, roles: NotificationRoles | None) -> dict[str, str]:
        """Environment variables that tell a step its notification duties.

        Parameters
        ----------
        node : Node
            Kedro node the step runs.
        roles : NotificationRoles or None
            Roles computed for the pipeline, or ``None`` for no notifications.

        Returns
        -------
        dict of str to str
            The definition on every step, plus the announcer and poster markers.
        """
        if roles is None or self.notification_config is None:
            return {}
        definition = {
            **self.notification_config.model_dump(),
            "job_name": self.job_name,
            "display_name": self.display_name or self.job_name,
            "pipeline_name": self.pipeline_name,
        }
        env = {KEDRO_AZUREML_NOTIFY: json.dumps(definition)}
        if node.name == roles.announcer:
            env[KEDRO_AZUREML_NOTIFY_START] = "1"
        if node.name == roles.poster:
            env[KEDRO_AZUREML_NOTIFY_OUTCOME] = "1"
            env[KEDRO_AZUREML_NOTIFY_SIBLINGS] = ",".join(roles.siblings)
        return env

    def get_kedro_pipeline(self) -> Pipeline:
        """Retrieve the registered Kedro pipeline by name.

        Returns
        -------
        Pipeline
            The Kedro ``Pipeline`` object.
        """
        from kedro.framework.project import pipelines

        pipeline: Pipeline = pipelines[self.pipeline_name]
        return pipeline

    def get_target_resource_from_node_tags(self, node: Node) -> ClusterConfig:
        """Resolve the compute cluster for *node* from its tags.

        Parameters
        ----------
        node : Node
            Kedro pipeline node.

        Returns
        -------
        ClusterConfig
            Matched cluster configuration.

        Raises
        ------
        ConfigException
            If more than one compute tag matches.
        """
        resource_tags = set(node.tags).intersection(set(self.config.compute.root.keys()))
        if len(resource_tags) > 1:
            raise ConfigException(
                "Node tags contain two values that are in defined in the resource config,"
                "a node can only have a maximum of 1 resource"
            )
        elif len(resource_tags) == 1:
            return self.config.compute.resolve(resource_tags.pop())
        else:
            return self.config.compute.root["__default__"]

    def _sanitize_param_name(self, param_name: str) -> str:
        """Replace non-alphanumeric characters with underscores.

        Parameters
        ----------
        param_name : str
            Original parameter name.

        Returns
        -------
        str
            Sanitized lowercase name suitable for Azure ML.
        """
        return re.sub(r"[^a-z0-9_]", "_", param_name.lower())

    def _sanitize_azure_name(self, name: str) -> str:
        """Normalise a node name for Azure ML component naming.

        Parameters
        ----------
        name : str
            Original name.

        Returns
        -------
        str
            Lowercased name with dots replaced by double underscores.
        """
        return name.lower().replace(".", "__")

    def _get_kedro_param(self, param_name: str, params: dict[str, Any] | None = None):
        """Look up a dot-separated parameter from *params* or ``self.kedro_params``.

        Parameters
        ----------
        param_name : str
            Dot-separated parameter path.
        params : dict of str to Any or None
            Nested dict or object to search (defaults to ``self.kedro_params``).
            When the current level is not a ``Mapping``, attribute access is
            used instead of subscript (e.g. for Pydantic models).

        Returns
        -------
        Any
            Resolved parameter value.
        """
        container = params if params is not None else self.kedro_params

        def _lookup(obj, key):
            """Subscript *obj* by *key*, falling back to getattr for non-dict objects."""
            try:
                return obj[key]
            except TypeError:
                return getattr(obj, key)

        if "." in param_name:
            name, remainder = param_name.split(".", 1)
            return self._get_kedro_param(remainder, _lookup(container, name))
        else:
            return _lookup(container, param_name)

    def _resolve_azure_environment(self) -> str | Environment | None:
        """Return the Azure ML environment name.

        Returns
        -------
        str | Environment | None
            Override ``aml_env`` or the value from config. Docker image URIs
            (e.g. ``myacr.azurecr.io/image:tag``) are wrapped in an
            ``Environment`` object so the SDK treats them as anonymous
            container images rather than named AML environment references.
        """
        env = self.aml_env or self.config.execution.environment
        if env and re.match(r"^[^@:]+\.[^@:/]+/", env):
            return Environment(image=env)
        return env

    def _get_versioned_azureml_dataset_name(self, catalog_name: str, azureml_dataset_name: str):
        """Append a version suffix to an Azure ML dataset path.

        Parameters
        ----------
        catalog_name : str
            Kedro catalog dataset name.
        azureml_dataset_name : str
            Azure ML registered dataset name.

        Returns
        -------
        str
            Dataset name with version suffix.
        """
        version = self.load_versions.get(catalog_name)
        suffix = "@latest" if version is None or version == "latest" else ":" + version
        return azureml_dataset_name + suffix

    def _get_input(self, dataset_name: str, pipeline: Pipeline) -> Input:
        """Build an Azure ML ``Input`` for *dataset_name*.

        Parameters
        ----------
        dataset_name : str
            Kedro dataset name.
        pipeline : Pipeline
            Current Kedro pipeline.

        Returns
        -------
        Input
            Azure ML input specification.

        Raises
        ------
        ValueError
            If a ``uri_file`` asset or an ``AzureMLDatastoreDataset`` is used outside pipeline inputs.
        """
        if self._is_param_or_root_non_azureml_asset_dataset(dataset_name, pipeline):
            return Input(type="string")
        elif dataset_name in self.catalog and isinstance(self.catalog[dataset_name], AzureMLDatastoreDataset):
            if dataset_name not in pipeline.inputs():
                raise ValueError("AzureMLDatastoreDatasets can only be used as pipeline inputs")
            return Input(type="uri_folder")
        elif dataset_name in self.catalog and isinstance(ds := self.catalog[dataset_name], AzureMLAssetDataset):
            if ds._azureml_type == "uri_file" and dataset_name not in pipeline.inputs():
                raise ValueError(
                    "AzureMLAssetDatasets with azureml_type 'uri_file' can only be used as pipeline inputs"
                )
            return Input(type=ds._azureml_type)
        else:
            return Input(type="uri_folder")

    def _get_output(self, name):
        """Build an Azure ML ``Output`` for *name*.

        Parameters
        ----------
        name : str
            Kedro dataset name.

        Returns
        -------
        Output
            Azure ML output specification.

        Raises
        ------
        ValueError
            If a ``uri_file`` asset or an ``AzureMLDatastoreDataset`` is used as an output.
        """
        if name in self.catalog and isinstance(self.catalog[name], AzureMLDatastoreDataset):
            raise ValueError("AzureMLDatastoreDatasets cannot be used as outputs")
        if name in self.catalog and isinstance(ds := self.catalog[name], AzureMLAssetDataset):
            if ds._azureml_type == "uri_file":
                raise ValueError("AzureMLAssetDatasets with azureml_type 'uri_file' cannot be used as outputs")
            return Output(type=ds._azureml_type, name=ds._azureml_dataset)
        else:
            return Output(type="uri_folder")

    def _from_params_or_value(
        self,
        namespace: str | None,
        value_to_parse,
        hint,
        expected_value_type: type = int,
    ):
        """Resolve a literal value or ``params:`` reference.

        Parameters
        ----------
        namespace : str or None
            Optional Kedro node namespace prefix.
        value_to_parse : Any
            Literal value or ``params:`` prefixed string.
        hint : str
            Descriptive label used in error messages.
        expected_value_type : type
            Expected Python type for a literal value.

        Returns
        -------
        Any
            Resolved value.

        Raises
        ------
        ValueError
            If *value_to_parse* is neither a ``params:`` reference nor
            an instance of *expected_value_type*.
        """
        if isinstance(value_to_parse, str) and value_to_parse.startswith(PARAMS_PREFIX):
            prefix = f"{namespace}." if namespace else ""
            return self._get_kedro_param(prefix + value_to_parse.replace(PARAMS_PREFIX, "", 1))
        elif (
            type(value_to_parse) is expected_value_type
        ):  # this is not isinstance() because isinstance(False, int) returns True...
            return value_to_parse
        else:
            msg = f"Expected either `params:` or actual value of type {expected_value_type}"
            msg += f" while parsing: {hint}"
            msg += f", got {value_to_parse}"
            raise ValueError(msg)

    def _is_param_or_root_non_azureml_asset_dataset(self, dataset_name: str, pipeline: Pipeline) -> bool:
        """Check if *dataset_name* is a parameter or a non-asset pipeline input.

        Parameters
        ----------
        dataset_name : str
            Kedro dataset name.
        pipeline : Pipeline
            Current Kedro pipeline.

        Returns
        -------
        bool
            ``True`` if the dataset is a ``params:`` prefix or a
            non-``AzureMLAssetDataset`` pipeline input.
        """
        return dataset_name.startswith(PARAMS_PREFIX) or (
            dataset_name in pipeline.inputs()
            and dataset_name in self.catalog
            and not isinstance(self.catalog[dataset_name], (AzureMLAssetDataset, AzureMLDatastoreDataset))
        )

    def _construct_azure_command(
        self,
        pipeline: Pipeline,
        node: Node,
        kedro_azure_run_id: str,
        roles: NotificationRoles | None = None,
    ):
        """Build an Azure ML ``command`` component for *node*.

        Parameters
        ----------
        pipeline : Pipeline
            Current Kedro pipeline.
        node : Node
            Kedro node to convert.
        kedro_azure_run_id : str
            Unique identifier for the Azure ML run.
        roles : NotificationRoles or None
            Notification roles for the pipeline, or ``None`` for no notifications.

        Returns
        -------
        Command
            Azure ML command component.
        """
        command_kwargs = {}
        command_kwargs.update(self._get_distributed_azure_command_kwargs(node))

        target_resource = self.get_target_resource_from_node_tags(node)

        mlflow_env_vars = {}
        if self.experiment_name is not None:
            mlflow_env_vars[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"
            if self.mlflow_run_name:
                mlflow_env_vars[KEDRO_AZUREML_MLFLOW_RUN_NAME] = self.mlflow_run_name
            if self.experiment_name:
                mlflow_env_vars[KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME] = self.experiment_name
            mlflow_env_vars[KEDRO_AZUREML_MLFLOW_NODE_NAME] = node.name

        return command(
            name=self._sanitize_azure_name(node.name),
            display_name=node.name,
            command=self._prepare_command(node, pipeline),
            compute=target_resource.cluster_name,
            instance_type=target_resource.instance_type,
            environment_variables={
                "KEDRO_ENV": self.kedro_environment,
                **mlflow_env_vars,
                **self._notification_env(node, roles),
                **self.extra_env,
            },
            environment=self._resolve_azure_environment(),
            inputs={self._sanitize_param_name(name): self._get_input(name, pipeline) for name in node.inputs},
            outputs={self._sanitize_param_name(name): self._get_output(name) for name in node.outputs},
            code=self.code if self.code is not None else self.config.execution.code_directory,
            is_deterministic=("deterministic" in node.tags),
            **command_kwargs,
        )

    def _get_distributed_azure_command_kwargs(self, node) -> dict:
        """Build keyword arguments for distributed training if applicable.

        Parameters
        ----------
        node : Node
            Kedro node (may carry a ``DistributedNodeConfig``).

        Returns
        -------
        dict
            Kwargs including ``instance_count`` and ``distribution`` when
            the node is decorated with `@distributed_job`, otherwise empty.
        """
        azure_command_kwargs = {}
        if hasattr(node.func, DISTRIBUTED_CONFIG_FIELD) and isinstance(
            distributed_config := getattr(node.func, DISTRIBUTED_CONFIG_FIELD),
            DistributedNodeConfig,
        ):
            distributed_config: DistributedNodeConfig
            logger.info(f"Using distributed configuration for node {node.name}: {distributed_config}")

            num_nodes: int = self._from_params_or_value(node.namespace, distributed_config.num_nodes, hint="num_nodes")

            processes_per_instance: int = (
                self._from_params_or_value(
                    node.namespace,
                    distributed_config.processes_per_node,
                    hint="processes_per_node",
                )
                if distributed_config.processes_per_node is not None
                else 1
            )

            azure_command_kwargs["instance_count"] = num_nodes
            azure_command_kwargs["distribution"] = {
                Framework.PyTorch: PyTorchDistribution(process_count_per_instance=processes_per_instance),
                Framework.TensorFlow: TensorFlowDistribution(worker_count=num_nodes),
                Framework.MPI: MpiDistribution(process_count_per_instance=processes_per_instance),
            }[distributed_config.framework]
        return azure_command_kwargs

    def _gather_pipeline_outputs(self, pipeline: Pipeline, invoked_components):
        """Collect final outputs from invoked Azure ML components.

        Parameters
        ----------
        pipeline : Pipeline
            Current Kedro pipeline.
        invoked_components : dict
            Mapping of node name to invoked Azure ML component.

        Returns
        -------
        dict
            Mapping of sanitized output name to Azure ML output reference.
        """
        azure_pipeline_outputs = {}
        for pipeline_output in pipeline.outputs():
            sanitized_output_name = self._sanitize_param_name(pipeline_output)
            source_node = next((n for n in pipeline.nodes if pipeline_output in n.outputs), None)
            if source_node is None:
                raise ConfigException(f"There is no node which outputs `{pipeline_output}` dataset")  # pragma: no cover
            azure_pipeline_outputs[sanitized_output_name] = invoked_components[source_node.name].outputs[
                sanitized_output_name
            ]
        return azure_pipeline_outputs

    def _connect_commands(self, pipeline: Pipeline, commands: dict[str, Command]):
        """Wire Azure ML commands into an execution graph.

        Connects command inputs with outputs from upstream commands by
        invoking the Azure ML DSL.

        Parameters
        ----------
        pipeline : Pipeline
            Current Kedro pipeline (provides topological ordering).
        commands : dict of str to Command
            Mapping of node name to Azure ML command.

        Returns
        -------
        dict
            Mapping of node name to invoked Azure ML component.
        """
        node_deps = pipeline.node_dependencies
        invoked_components = {}
        for node in pipeline.nodes:  # pipeline.nodes are sorted topologically
            dependencies = node_deps[node]
            azure_inputs = {}
            for node_input in node.inputs:
                # 1. try to find output in dependencies
                sanitized_input_name = self._sanitize_param_name(node_input)
                output_from_deps = next((d for d in dependencies if node_input in d.outputs), None)
                if output_from_deps:
                    parent_outputs = invoked_components[output_from_deps.name].outputs
                    azure_output = parent_outputs[sanitized_input_name]
                    azure_inputs[sanitized_input_name] = azure_output
                # 2. try to find AzureMLAssetDataset in catalog
                elif node_input in self.catalog and isinstance(ds := self.catalog[node_input], AzureMLAssetDataset):
                    azure_inputs[sanitized_input_name] = Input(
                        type=ds._azureml_type,
                        path=self._get_versioned_azureml_dataset_name(node_input, ds._azureml_dataset),
                    )
                # 3. read a datastore folder by its path
                elif node_input in self.catalog and isinstance(ds := self.catalog[node_input], AzureMLDatastoreDataset):
                    azure_inputs[sanitized_input_name] = Input(type="uri_folder", path=ds.uri)
                # 4. if not found, provide dummy input
                else:
                    azure_inputs[sanitized_input_name] = node_input
            invoked_components[node.name] = commands[node.name](**azure_inputs)
            if self.limits_config is not None:
                invoked_components[node.name].limits = CommandJobLimits(timeout=self.limits_config.timeout)
        return invoked_components

    def _prepare_command(self, node, pipeline):
        """Build the shell command string for a Kedro node execution.

        Parameters
        ----------
        node : Node
            Kedro node.
        pipeline : Pipeline
            Current Kedro pipeline.

        Returns
        -------
        str
            Full shell command for ``kedro azureml execute``, ending with the
            exit-classification suffix that names the signal when the process
            dies of one.
        """
        input_data_paths = (
            [
                f"--az-input={name} " + "${{inputs." + self._sanitize_param_name(name) + "}}"
                for name in node.inputs
                if not self._is_param_or_root_non_azureml_asset_dataset(name, pipeline)
            ]
            if node.inputs
            else []
        )
        output_data_paths = (
            [f"--az-output={name} " + "${{outputs." + self._sanitize_param_name(name) + "}}" for name in node.outputs]
            if node.outputs
            else []
        )
        return (
            (
                f"cd {self.config.execution.working_directory} && "
                if self.config.execution.working_directory is not None and self.config.execution.code_directory is None
                else ""
            )
            + f"kedro azureml -e {self.kedro_environment} execute --pipeline={self.pipeline_name} --node={node.name} "  # noqa
            + " ".join(input_data_paths + output_data_paths)
            + (f" --params='{self.params}'" if self.params else "")
        ).strip() + EXIT_CLASSIFICATION_SUFFIX
