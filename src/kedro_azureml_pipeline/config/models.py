"""Pydantic configuration models for the Kedro AzureML Pipeline plugin."""

from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


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
    [WorkspacesConfig][kedro_azureml_pipeline.config.WorkspacesConfig] : Named workspace registry.
    [KedroAzureMLConfig][kedro_azureml_pipeline.config.KedroAzureMLConfig] : Top-level plugin configuration.
    """

    model_config = ConfigDict(extra="forbid")

    subscription_id: str = Field(description="Azure subscription ID.")
    resource_group: str = Field(description="Azure resource group name.")
    name: str = Field(description="Azure ML workspace name.")


class WorkspacesConfig(RootModel[dict[str, WorkspaceConfig]]):
    """Named workspaces with a mandatory ``__default__`` entry.

    Jobs reference a workspace by name; ``resolve`` falls back to
    ``__default__`` when *name* is ``None``.

    See Also
    --------
    [WorkspaceConfig][kedro_azureml_pipeline.config.WorkspaceConfig] : Single workspace identity.
    [KedroAzureMLConfig][kedro_azureml_pipeline.config.KedroAzureMLConfig] : Top-level plugin configuration.
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
    [ComputeConfig][kedro_azureml_pipeline.config.ComputeConfig] : Named compute cluster registry.
    """

    model_config = ConfigDict(extra="forbid")

    cluster_name: str = Field(description="Name of the Azure ML compute cluster.")


class ComputeConfig(RootModel[dict[str, ClusterConfig]]):
    """Named compute clusters with a mandatory ``__default__`` entry.

    Use ``resolve(tag)`` to look up a cluster by node tag,
    falling back to ``__default__``.

    See Also
    --------
    [ClusterConfig][kedro_azureml_pipeline.config.ClusterConfig] : Single cluster entry.
    [AzureMLPipelineGenerator][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] : Uses compute config for node routing.
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
    [KedroAzureMLConfig][kedro_azureml_pipeline.config.KedroAzureMLConfig] : Top-level plugin configuration.
    [AzureMLPipelineGenerator][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] : Consumes execution config.
    """

    model_config = ConfigDict(extra="forbid")

    environment: str | None = Field(default=None, description="Azure ML environment name (e.g. 'my-env@latest').")
    code_directory: str | None = Field(
        default=None, description="Local directory to upload as a code snapshot, or None to disable code upload."
    )
    working_directory: str | None = Field(default=None, description="Working directory inside the compute container.")


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

    model_config = ConfigDict(extra="forbid")

    expression: str = Field(description="Cron expression (e.g. '0 8 * * 1-5').")
    start_time: str | None = Field(default=None, description="ISO 8601 start time.")
    end_time: str | None = Field(default=None, description="ISO 8601 end time.")
    time_zone: str = Field(default="UTC", description="IANA time zone.")


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

    model_config = ConfigDict(extra="forbid")

    hours: list[int] | None = Field(default=None, description="Hours of the day to trigger.")
    minutes: list[int] | None = Field(default=None, description="Minutes of the hour to trigger.")
    week_days: list[str] | None = Field(
        default=None, description="Days of the week to trigger (e.g. ['Monday', 'Friday'])."
    )


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

    model_config = ConfigDict(extra="forbid")

    frequency: str = Field(description="Recurrence frequency (e.g. 'day', 'week').")
    interval: int = Field(description="Number of frequency units between runs.")
    schedule: RecurrencePatternConfig | None = Field(default=None, description="Optional detailed recurrence pattern.")
    start_time: str | None = Field(default=None, description="ISO 8601 start time.")
    end_time: str | None = Field(default=None, description="ISO 8601 end time.")
    time_zone: str = Field(default="UTC", description="IANA time zone.")


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
    [CronScheduleConfig][kedro_azureml_pipeline.config.CronScheduleConfig] : Cron trigger details.
    [RecurrenceScheduleConfig][kedro_azureml_pipeline.config.RecurrenceScheduleConfig] : Recurrence trigger details.
    [build_trigger][kedro_azureml_pipeline.scheduler.build_trigger] : Converts this config to Azure ML trigger.
    """

    model_config = ConfigDict(extra="forbid")

    cron: CronScheduleConfig | None = Field(default=None, description="Cron-based trigger.")
    recurrence: RecurrenceScheduleConfig | None = Field(default=None, description="Recurrence-based trigger.")

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
    [JobConfig][kedro_azureml_pipeline.config.JobConfig] : Uses filter options per job.
    [AzureMLPipelineGenerator][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] : Applies filters during generation.
    """

    model_config = ConfigDict(extra="forbid")

    pipeline_name: str = Field(default="__default__", description="Kedro pipeline name.")
    from_nodes: list[str] | None = Field(default=None, description="Start from these nodes.")
    to_nodes: list[str] | None = Field(default=None, description="Run up to these nodes.")
    node_names: list[str] | None = Field(default=None, description="Run only these specific nodes.")
    from_inputs: list[str] | None = Field(default=None, description="Start from nodes that produce these datasets.")
    to_outputs: list[str] | None = Field(default=None, description="Run up to nodes that produce these datasets.")
    node_namespaces: list[str] | None = Field(default=None, description="Filter by namespace.")
    tags: list[str] | None = Field(default=None, description="Filter by tag.")

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

    Examples
    --------
    ```yaml
    jobs:
      __default__:
        pipeline:
          pipeline_name: __default__
        experiment_name: "my-experiment"
      nightly:
        pipeline:
          pipeline_name: data_processing
        schedule:
          cron:
            expression: "0 2 * * *"
    ```

    See Also
    --------
    [PipelineFilterOptions][kedro_azureml_pipeline.config.PipelineFilterOptions] : Pipeline node filtering.
    [ScheduleConfig][kedro_azureml_pipeline.config.ScheduleConfig] : Schedule trigger specification.
    """

    model_config = ConfigDict(extra="forbid")

    pipeline: PipelineFilterOptions = Field(description="Pipeline selection and filter options.")
    workspace: str | None = Field(default=None, description="Named workspace to use (falls back to '__default__').")
    experiment_name: str | None = Field(default=None, description="Azure ML experiment name.")
    display_name: str | None = Field(default=None, description="Display name shown in the Azure ML portal.")
    compute: str | None = Field(default=None, description="Named compute entry to use.")
    schedule: ScheduleConfig | str | None = Field(
        default=None, description="Inline schedule, named schedule reference, or None for ad-hoc."
    )
    description: str | None = Field(default=None, description="Human-readable job description.")


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

    Examples
    --------
    ```yaml
    # conf/base/azureml.yml
    workspace:
      __default__:
        subscription_id: "abc-123"
        resource_group: "my-rg"
        name: "my-workspace"

    compute:
      __default__:
        cluster_name: "cpu-cluster"

    execution:
      environment: "my-env@latest"

    jobs:
      __default__:
        pipeline:
          pipeline_name: __default__
    ```

    See Also
    --------
    [WorkspacesConfig][kedro_azureml_pipeline.config.WorkspacesConfig] : Workspace definitions.
    [ComputeConfig][kedro_azureml_pipeline.config.ComputeConfig] : Compute cluster definitions.
    [JobConfig][kedro_azureml_pipeline.config.JobConfig] : Individual job configurations.
    [KedroContextManager][kedro_azureml_pipeline.manager.KedroContextManager] : Loads and validates this config.
    """

    model_config = ConfigDict(extra="forbid")

    workspace: WorkspacesConfig = Field(description="Named Azure ML workspace definitions.")
    compute: ComputeConfig = Field(description="Named compute cluster definitions.")
    execution: ExecutionConfig = Field(
        default_factory=ExecutionConfig, description="Code packaging and execution settings."
    )
    schedules: dict[str, ScheduleConfig] = Field(
        default_factory=dict, description="Reusable named schedule definitions."
    )
    jobs: dict[str, JobConfig] = Field(default_factory=dict, description="Named job definitions.")


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
