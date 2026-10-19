"""Pydantic configuration models for the Kedro AzureML Pipeline plugin."""

from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator


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
    cluster_name : str or None
        Name of the Azure ML compute cluster. Required on the
        ``__default__`` entry. A tag entry that omits it inherits the
        ``__default__`` cluster during resolution.
    instance_type : str or None
        Name of the Azure ML instance type to run steps under. Only
        meaningful when ``cluster_name`` is an attached Kubernetes
        compute target, where instance types are ``InstanceType``
        custom resources defined on the cluster. When omitted, Azure ML
        runs steps under ``defaultinstancetype``, whose stock definition
        limits each step to 2 CPU cores, 2 GiB of memory, and no GPU.
        AmlCompute clusters ignore this field.

    Examples
    --------
    ```yaml
    compute:
      __default__:
        cluster_name: "k8s-compute"
      gpu-nodes:
        cluster_name: "k8s-compute"
        instance_type: "gpu-large"
    ```

    See Also
    --------
    [ComputeConfig][kedro_azureml_pipeline.config.ComputeConfig] : Named compute cluster registry.
    """

    model_config = ConfigDict(extra="forbid")

    cluster_name: str | None = Field(
        default=None,
        description="Name of the Azure ML compute cluster. Required on '__default__'; tag entries inherit it when omitted.",
    )
    instance_type: str | None = Field(
        default=None,
        description="Azure ML instance type for Kubernetes compute targets. None means the cluster's defaultinstancetype.",
    )


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
            If the ``__default__`` key is missing, or if it does not
            set ``cluster_name``.
        """
        if "__default__" not in self.root:
            raise ValueError("ComputeConfig must contain a '__default__' key")
        if self.root["__default__"].cluster_name is None:
            raise ValueError("The '__default__' compute entry must set cluster_name")
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


class LimitsConfig(BaseModel):
    """Run-duration limits for Azure ML pipeline steps.

    Maps to ``azure.ai.ml.entities.CommandJobLimits`` applied on each invoked
    command component. The timeout is a hang guard rather than an expected
    duration: Azure ML cancels the step once it is reached, releasing the
    instances the step was holding.

    Retry settings are deliberately absent. ``RetrySettings`` is declared for
    parallel and sweep jobs only, so on a command step the Azure ML SDK reports
    it as an unknown field and the service ignores it. Azure ML does not retry
    command steps, and this plugin emits only command steps.

    Parameters
    ----------
    timeout : int
        Maximum run duration in seconds, after which the step is cancelled.

    Examples
    --------
    ```yaml
    jobs:
      nightly:
        pipeline:
          pipeline_name: data_processing
        limits:
          timeout: 3600
    ```

    See Also
    --------
    [JobConfig][kedro_azureml_pipeline.config.JobConfig] : Uses limits per job.
    """

    model_config = ConfigDict(extra="forbid")

    timeout: int = Field(ge=1, description="Maximum run duration in seconds, after which the step is cancelled.")


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


NotificationEventName = Literal["start", "success", "failure", "warning", "recovered"]


class NotificationConfig(BaseModel):
    """Notification for the runs of a job, posted to a webhook or the Slack API.

    Referenced by name from a job's ``notifications`` field. The generator stamps
    the definition into every step of the job, and
    [NotificationHook][kedro_azureml_pipeline.hooks.NotificationHook] posts one
    ``start`` message from a designated root step, one ``failure`` message from
    the step that raised, and one ``success`` message from a designated leaf
    step once every other leaf has finished.

    Two transports exist. A webhook receives the payload as the request body.
    The Slack API (``token_env`` and ``channel``) posts with ``chat.postMessage``
    under the app's bot identity, and threads the outcome messages under the
    ``start`` message of the same run, also sent to the channel. A definition
    may name both: the API is used when the token is present in the step and
    the webhook otherwise.

    Parameters
    ----------
    webhook_env : str or None
        Name of the environment variable, inside the step, that holds the
        webhook URL. The URL itself never appears in configuration.
    token_env : str or None
        Name of the environment variable, inside the step, that holds the Slack
        bot token. Requires ``channel``.
    channel : str or None
        Slack channel ID the API posts to. Requires ``token_env``.
    events : list of {"start", "success", "failure", "warning", "recovered"}
        Events to report. At least one. (Named ``events`` rather than ``on``
        because YAML 1.1 reads a bare ``on`` key as the boolean true.)
        ``warning`` reports a job that finished with a step marked degraded (a
        ``kedro.warning`` tag on its MLflow run), and ``recovered`` its first clean
        run after one; both compare each run with the job's previous completed run.
    payload : str or None
        ``module.path:function_name`` reference to a payload builder. It is
        called with a [NotificationEvent][kedro_azureml_pipeline.hooks.NotificationEvent]
        and returns the mapping posted as the request body. ``None`` posts a
        plain ``{"text": ...}`` payload.
    wait_timeout : int
        Seconds the designated leaf step waits for its sibling leaves before
        posting an outcome-unknown message instead of ``success``. Must be
        below the job's ``limits.timeout`` when one is declared.
    warning_repeat_hours : int
        While a job stays degraded, hours between reminders of the same outage,
        measured between run start times.
    warning_repeat_tolerance_minutes : int
        How many minutes early a reminder may come, so a run starting slightly
        before the interval is up does not push the reminder to the next run.

    Examples
    --------
    ```yaml
    notifications:
      alerts:
        webhook_env: SLACK_WEBHOOK_URL
        events: [start, success, failure]
        payload: my_project.notifications:build_payload
      threaded:
        token_env: SLACK_BOT_TOKEN
        channel: C0123456789
        events: [start, success, failure]

    jobs:
      nightly:
        pipeline:
          pipeline_name: data_processing
        notifications: threaded
    ```

    See Also
    --------
    [JobConfig][kedro_azureml_pipeline.config.JobConfig] : References a definition by name.
    [NotificationHook][kedro_azureml_pipeline.hooks.NotificationHook] : Posts the messages.
    """

    model_config = ConfigDict(extra="forbid")

    webhook_env: str | None = Field(
        default=None, min_length=1, description="Environment variable holding the webhook URL inside the step."
    )
    token_env: str | None = Field(
        default=None, min_length=1, description="Environment variable holding the Slack bot token inside the step."
    )
    channel: str | None = Field(default=None, min_length=1, description="Slack channel ID the API posts to.")
    events: list[NotificationEventName] = Field(min_length=1, description="Events to report.")
    payload: str | None = Field(
        default=None,
        description="Payload builder in 'module.path:function_name' format, or None for the default payload.",
    )
    wait_timeout: int = Field(
        default=1800,
        ge=1,
        description="Seconds the outcome step waits for sibling leaves before posting outcome-unknown.",
    )
    warning_repeat_hours: int = Field(default=24, ge=1, description="Hours between reminders of an ongoing outage.")
    warning_repeat_tolerance_minutes: int = Field(
        default=15, ge=0, description="Minutes early a reminder may come, measured between run start times."
    )

    @field_validator("payload")
    @classmethod
    def _validate_payload_reference(cls, value: str | None) -> str | None:
        """Require the ``module.path:function_name`` shape when a builder is set.

        Parameters
        ----------
        value : str or None
            Raw ``payload`` field.

        Returns
        -------
        str or None
            The validated reference.

        Raises
        ------
        ValueError
            If the reference has no module part or no attribute part.
        """
        if value is None:
            return value
        module_str, _, attr_str = value.partition(":")
        if not module_str or not attr_str:
            raise ValueError("payload must be in 'module.path:function_name' format")
        return value

    @model_validator(mode="after")
    def _validate_transport(self) -> "NotificationConfig":
        """Require a webhook or a complete Slack API pair.

        Returns
        -------
        NotificationConfig
            The validated definition.

        Raises
        ------
        ValueError
            If neither transport is configured, or only one of ``token_env``
            and ``channel`` is set.
        """
        if (self.token_env is None) != (self.channel is None):
            raise ValueError("token_env and channel must be set together")
        if self.webhook_env is None and self.token_env is None:
            raise ValueError("a notification needs webhook_env, or token_env with channel")
        return self


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
    params : dict of str to Any or None
        Job-level runtime parameters merged into every step. CLI --params take precedence.
    limits : LimitsConfig or None
        Run-duration limits applied to every step in this job.
    description : str or None
        Human-readable job description.
    notifications : str or None
        Name of a ``notifications`` definition whose webhook receives this
        job's run events, or ``None`` for no notifications.

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
        limits:
          timeout: 3600
    ```

    See Also
    --------
    [PipelineFilterOptions][kedro_azureml_pipeline.config.PipelineFilterOptions] : Pipeline node filtering.
    [ScheduleConfig][kedro_azureml_pipeline.config.ScheduleConfig] : Schedule trigger specification.
    [LimitsConfig][kedro_azureml_pipeline.config.LimitsConfig] : Run-duration limits.
    [NotificationConfig][kedro_azureml_pipeline.config.NotificationConfig] : Run-outcome notifications.
    """

    model_config = ConfigDict(extra="forbid")

    pipeline: PipelineFilterOptions = Field(description="Pipeline selection and filter options.")
    workspace: str | None = Field(default=None, description="Named workspace to use (falls back to '__default__').")
    experiment_name: str | None = Field(default=None, description="Azure ML experiment name.")
    display_name: str | None = Field(default=None, description="Display name shown in the Azure ML portal.")
    compute: str | None = Field(default=None, description="Named compute entry to use.")
    schedule: ScheduleConfig | str | list[ScheduleConfig | str] | None = Field(
        default=None,
        description="Inline schedule, named schedule reference, a list of either (one trigger deployed per entry), or None for ad-hoc.",
    )
    params: dict[str, Any] | None = Field(
        default=None,
        description="Job-level runtime parameters merged into every step. CLI --params take precedence.",
    )
    limits: LimitsConfig | None = Field(
        default=None, description="Run-duration limits applied to every step in this job."
    )
    description: str | None = Field(default=None, description="Human-readable job description.")
    notifications: str | None = Field(
        default=None, description="Name of a 'notifications' definition to post this job's run events to."
    )


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
    notifications : dict of str to NotificationConfig
        Reusable named webhook notification definitions.
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
    [NotificationConfig][kedro_azureml_pipeline.config.NotificationConfig] : Run-outcome notifications.
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
    notifications: dict[str, NotificationConfig] = Field(
        default_factory=dict, description="Reusable named webhook notification definitions."
    )
    jobs: dict[str, JobConfig] = Field(
        default_factory=dict,
        description="Named job definitions. A key containing '{placeholder}' markers is a job factory whose jobs are derived from the Kedro pipeline namespaces.",
    )

    @model_validator(mode="after")
    def _validate_notification_references(self) -> "KedroAzureMLConfig":
        """Resolve every job's notification reference and check its wait cap.

        A job's ``notifications`` must name a defined entry. When the job also
        declares ``limits.timeout``, the definition's ``wait_timeout`` must be
        below it: the outcome step's wait counts against its own step budget,
        and a step cancelled mid-wait posts nothing.

        Returns
        -------
        KedroAzureMLConfig
            The validated configuration.

        Raises
        ------
        ValueError
            If a reference is undefined or a wait cap is not below the step timeout.
        """
        for job_name, job in self.jobs.items():
            if job.notifications is None:
                continue
            definition = self.notifications.get(job.notifications)
            if definition is None:
                raise ValueError(
                    f"Job '{job_name}' references notification '{job.notifications}' which is not defined "
                    "in the 'notifications' section of azureml.yml"
                )
            if job.limits is not None and definition.wait_timeout >= job.limits.timeout:
                raise ValueError(
                    f"Job '{job_name}': notification '{job.notifications}' wait_timeout ({definition.wait_timeout}s) "
                    f"must be below the job's limits.timeout ({job.limits.timeout}s)"
                )
        return self


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
  #   # Kubernetes compute only: instance type to run steps under
  #   # instance_type: "<instance_type_name>"

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
