"""Pydantic configuration models for the Kedro AzureML Pipeline plugin."""

from typing import Any

import yaml
from pydantic import BaseModel, RootModel, model_validator


class WorkspaceConfig(BaseModel):
    """Azure ML workspace identity.

    Parameters
    ----------
    subscription_id : str
        Azure subscription ID.
    resource_group : str
        Azure resource group name.
    name : str
        Azure ML workspace name.

    See Also
    --------
    `kedro_azureml_pipeline.config.WorkspacesConfig` : Named workspace registry.
    `kedro_azureml_pipeline.config.KedroAzureMLConfig` : Top-level plugin configuration.
    """

    subscription_id: str
    resource_group: str
    name: str


class WorkspacesConfig(RootModel[dict[str, WorkspaceConfig]]):
    """Named workspaces with a mandatory ``__default__`` entry.

    Jobs reference a workspace by name; ``resolve`` falls back to
    ``__default__`` when *name* is ``None``.

    See Also
    --------
    `kedro_azureml_pipeline.config.WorkspaceConfig` : Single workspace identity.
    `kedro_azureml_pipeline.config.KedroAzureMLConfig` : Top-level plugin configuration.
    """

    @model_validator(mode="after")
    def _validate_default_key(self) -> "WorkspacesConfig":
        """Ensure a ``__default__`` workspace is present.

        Returns
        -------
        WorkspacesConfig
            The validated instance.

        Raises
        ------
        ValueError
            If the ``__default__`` key is missing.
        """
        if "__default__" not in self.root:
            raise ValueError("WorkspacesConfig must contain a '__default__' key")
        return self

    def resolve(self, name: str | None = None) -> WorkspaceConfig:
        """Return the workspace for *name*, falling back to ``__default__``.

        Parameters
        ----------
        name : str or None
            Workspace name to look up. Falls back to ``__default__``
            when ``None``.

        Returns
        -------
        WorkspaceConfig
            The resolved workspace configuration.

        Raises
        ------
        KeyError
            If *name* is given but not found in the mapping.
        """
        if name and name in self.root:
            return self.root[name]
        if name and name not in self.root:
            raise KeyError(f"Workspace '{name}' not found. Available: {', '.join(sorted(self.root.keys()))}")
        return self.root["__default__"]


class ClusterConfig(BaseModel):
    """Single compute cluster reference.

    Parameters
    ----------
    cluster_name : str
        Name of the Azure ML compute cluster.

    See Also
    --------
    `kedro_azureml_pipeline.config.ComputeConfig` : Named compute cluster registry.
    """

    cluster_name: str


class ComputeConfig(RootModel[dict[str, ClusterConfig]]):
    """Named compute clusters with a mandatory ``__default__`` entry.

    Use ``resolve(tag)`` to look up a cluster by node tag,
    falling back to ``__default__``.

    See Also
    --------
    `kedro_azureml_pipeline.config.ClusterConfig` : Single cluster entry.
    `kedro_azureml_pipeline.generator.AzureMLPipelineGenerator` : Uses compute config for node routing.
    """

    @model_validator(mode="after")
    def _validate_default_key(self) -> "ComputeConfig":
        """Ensure a ``__default__`` compute entry is present.

        Returns
        -------
        ComputeConfig
            The validated instance.

        Raises
        ------
        ValueError
            If the ``__default__`` key is missing.
        """
        if "__default__" not in self.root:
            raise ValueError("ComputeConfig must contain a '__default__' key")
        return self

    def resolve(self, tag: str | None = None) -> ClusterConfig:
        """Return the cluster for *tag*, falling back to ``__default__``.

        Parameters
        ----------
        tag : str or None
            Node tag to look up. Falls back to ``__default__``
            when ``None``.

        Returns
        -------
        ClusterConfig
            The resolved cluster configuration.
        """
        if tag and tag in self.root:
            return self.root["__default__"].model_copy(update=self.root[tag].model_dump(exclude_none=True))
        return self.root["__default__"]


class ExecutionConfig(BaseModel):
    """Code packaging and execution settings for Azure ML.

    Parameters
    ----------
    environment : str or None
        Azure ML environment name (e.g. ``my-env@latest``).
    code_directory : str or None
        Local directory to upload as a code snapshot, or ``None``
        to disable code upload.
    working_directory : str or None
        Working directory inside the compute container.

    See Also
    --------
    `kedro_azureml_pipeline.config.KedroAzureMLConfig` : Top-level plugin configuration.
    `kedro_azureml_pipeline.generator.AzureMLPipelineGenerator` : Consumes execution config.
    """

    environment: str | None = None
    code_directory: str | None = None
    working_directory: str | None = None


class CronScheduleConfig(BaseModel):
    """Cron schedule configuration mapping to ``azure.ai.ml.entities.CronTrigger``.

    Parameters
    ----------
    expression : str
        Cron expression (e.g. ``"0 8 * * 1-5"``).
    start_time : str or None
        ISO 8601 start time.
    end_time : str or None
        ISO 8601 end time.
    time_zone : str
        IANA time zone (default ``"UTC"``).
    """

    expression: str
    start_time: str | None = None
    end_time: str | None = None
    time_zone: str = "UTC"


class RecurrencePatternConfig(BaseModel):
    """Recurrence pattern mapping to ``azure.ai.ml.entities.RecurrencePattern``.

    Parameters
    ----------
    hours : list of int or None
        Hours of the day to trigger.
    minutes : list of int or None
        Minutes of the hour to trigger.
    week_days : list of str or None
        Days of the week to trigger (e.g. ``["Monday", "Friday"]``).
    """

    hours: list[int] | None = None
    minutes: list[int] | None = None
    week_days: list[str] | None = None


class RecurrenceScheduleConfig(BaseModel):
    """Recurrence schedule mapping to ``azure.ai.ml.entities.RecurrenceTrigger``.

    Parameters
    ----------
    frequency : str
        Recurrence frequency (e.g. ``"day"``, ``"week"``).
    interval : int
        Number of frequency units between runs.
    schedule : RecurrencePatternConfig or None
        Optional detailed recurrence pattern.
    start_time : str or None
        ISO 8601 start time.
    end_time : str or None
        ISO 8601 end time.
    time_zone : str
        IANA time zone (default ``"UTC"``).
    """

    frequency: str
    interval: int
    schedule: RecurrencePatternConfig | None = None
    start_time: str | None = None
    end_time: str | None = None
    time_zone: str = "UTC"


class ScheduleConfig(BaseModel):
    """Schedule trigger configuration requiring exactly one of ``cron`` or ``recurrence``.

    Parameters
    ----------
    cron : CronScheduleConfig or None
        Cron-based trigger.
    recurrence : RecurrenceScheduleConfig or None
        Recurrence-based trigger.

    See Also
    --------
    `kedro_azureml_pipeline.config.CronScheduleConfig` : Cron trigger details.
    `kedro_azureml_pipeline.config.RecurrenceScheduleConfig` : Recurrence trigger details.
    `kedro_azureml_pipeline.scheduler.build_trigger` : Converts this config to Azure ML trigger.
    """

    cron: CronScheduleConfig | None = None
    recurrence: RecurrenceScheduleConfig | None = None

    @model_validator(mode="after")
    def _validate_exactly_one_trigger(self) -> "ScheduleConfig":
        """Ensure exactly one of ``cron`` or ``recurrence`` is set.

        Returns
        -------
        ScheduleConfig
            The validated instance.

        Raises
        ------
        ValueError
            If both or neither trigger is set.
        """
        if self.cron and self.recurrence:
            raise ValueError("ScheduleConfig must have exactly one of 'cron' or 'recurrence', not both")
        if not self.cron and not self.recurrence:
            raise ValueError("ScheduleConfig must have exactly one of 'cron' or 'recurrence'")
        return self


class PipelineFilterOptions(BaseModel):
    """Kedro pipeline filter options for selecting nodes.

    Parameters
    ----------
    pipeline_name : str
        Kedro pipeline name (default ``"__default__"``).
    from_nodes : list of str or None
        Start from these nodes.
    to_nodes : list of str or None
        Run up to these nodes.
    node_names : list of str or None
        Run only these specific nodes.
    from_inputs : list of str or None
        Start from nodes that produce these datasets.
    to_outputs : list of str or None
        Run up to nodes that produce these datasets.
    node_namespaces : list of str or None
        Filter by namespace.
    tags : list of str or None
        Filter by tag.

    See Also
    --------
    `kedro_azureml_pipeline.config.JobConfig` : Uses filter options per job.
    `kedro_azureml_pipeline.generator.AzureMLPipelineGenerator` : Applies filters during generation.
    """

    pipeline_name: str = "__default__"
    from_nodes: list[str] | None = None
    to_nodes: list[str] | None = None
    node_names: list[str] | None = None
    from_inputs: list[str] | None = None
    to_outputs: list[str] | None = None
    node_namespaces: list[str] | None = None
    tags: list[str] | None = None

    def to_filter_kwargs(self) -> dict[str, Any]:
        """Return non-None filter kwargs suitable for ``Pipeline.filter()``.

        Returns
        -------
        dict of str to Any
            Only keys whose values are not ``None``.
        """
        mapping = {
            "node_names": self.node_names,
            "from_nodes": self.from_nodes,
            "to_nodes": self.to_nodes,
            "from_inputs": self.from_inputs,
            "to_outputs": self.to_outputs,
            "node_namespaces": self.node_namespaces,
            "tags": self.tags,
        }
        return {k: v for k, v in mapping.items() if v is not None}


class JobConfig(BaseModel):
    """A single named job configuration.

    Parameters
    ----------
    pipeline : PipelineFilterOptions
        Pipeline selection and filter options.
    workspace : str or None
        Named workspace to use (falls back to ``__default__``).
    experiment_name : str or None
        Azure ML experiment name.
    display_name : str or None
        Display name shown in the Azure ML portal.
    compute : str or None
        Named compute entry to use.
    schedule : ScheduleConfig or str or None
        Inline schedule, named schedule reference, or ``None`` for ad-hoc.
    description : str or None
        Human-readable job description.

    See Also
    --------
    `kedro_azureml_pipeline.config.PipelineFilterOptions` : Pipeline node filtering.
    `kedro_azureml_pipeline.config.ScheduleConfig` : Schedule trigger specification.
    `kedro_azureml_pipeline.cli_functions.submit_scheduled_jobs` : Submits configured jobs.
    """

    pipeline: PipelineFilterOptions
    workspace: str | None = None
    experiment_name: str | None = None
    display_name: str | None = None
    compute: str | None = None
    schedule: ScheduleConfig | str | None = None
    description: str | None = None


class KedroAzureMLConfig(BaseModel):
    """Top-level plugin configuration loaded from ``azureml.yml``.

    Parameters
    ----------
    workspace : WorkspacesConfig
        Named Azure ML workspace definitions.
    compute : ComputeConfig
        Named compute cluster definitions.
    execution : ExecutionConfig
        Code packaging and execution settings.
    schedules : dict of str to ScheduleConfig
        Reusable named schedule definitions.
    jobs : dict of str to JobConfig
        Named job definitions.

    See Also
    --------
    `kedro_azureml_pipeline.config.WorkspacesConfig` : Workspace definitions.
    `kedro_azureml_pipeline.config.ComputeConfig` : Compute cluster definitions.
    `kedro_azureml_pipeline.config.JobConfig` : Individual job configurations.
    `kedro_azureml_pipeline.manager.KedroContextManager` : Loads and validates this config.
    """

    workspace: WorkspacesConfig
    compute: ComputeConfig
    execution: ExecutionConfig = ExecutionConfig()
    schedules: dict[str, ScheduleConfig] = {}
    jobs: dict[str, JobConfig] = {}


CONFIG_TEMPLATE_YAML = """
workspace:
  __default__:
    # Azure subscription ID
    subscription_id: "<subscription_id>"
    # Azure resource group
    resource_group: "<resource_group>"
    # Azure ML Workspace name
    name: "<workspace_name>"

compute:
  __default__:
    cluster_name: "<cluster_name>"
  # gpu-nodes:
  #   cluster_name: "<gpu_cluster_name>"

execution:
  # Azure ML Environment to use during pipeline execution
  environment: "<environment>"
  # Path to directory to upload, or null to disable code upload
  code_directory: "."
  # Path to the directory in the Docker image to run the code from
  # Ignored when code_directory is set
  working_directory: /home/kedro_docker
""".strip()

_CONFIG_TEMPLATE = KedroAzureMLConfig.model_validate(yaml.safe_load(CONFIG_TEMPLATE_YAML))
