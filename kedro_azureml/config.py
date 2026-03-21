from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, RootModel, model_validator

from kedro_azureml.utils import update_dict


class WorkspaceConfig(BaseModel):
    """Azure ML workspace identity (subscription + resource group + name)."""

    subscription_id: str
    resource_group: str
    name: str


class WorkspacesConfig(RootModel[Dict[str, WorkspaceConfig]]):
    """Named workspaces with a mandatory ``__default__`` entry.

    Example YAML::

        workspace:
          __default__:
            subscription_id: "abc"
            resource_group: rg-dev
            name: aml-dev
          prod:
            subscription_id: "xyz"
            resource_group: rg-prod
            name: aml-prod

    Jobs reference a workspace by name; ``resolve(name)`` falls back to
    ``__default__`` when *name* is ``None``.
    """

    @model_validator(mode="after")
    def _validate_default_key(self) -> "WorkspacesConfig":
        if "__default__" not in self.root:
            raise ValueError("WorkspacesConfig must contain a '__default__' key")
        return self

    def resolve(self, name: Optional[str] = None) -> WorkspaceConfig:
        """Return the workspace for *name*, falling back to ``__default__``."""
        if name and name in self.root:
            return self.root[name]
        if name and name not in self.root:
            raise KeyError(
                f"Workspace '{name}' not found. "
                f"Available: {', '.join(sorted(self.root.keys()))}"
            )
        return self.root["__default__"]


class ClusterConfig(BaseModel):
    cluster_name: str


class ComputeConfig(RootModel[Dict[str, ClusterConfig]]):
    """Flat dict of named compute clusters. ``__default__`` is mandatory.

    Example YAML::

        compute:
          __default__:
            cluster_name: cpu-8
          gpu-nodes:
            cluster_name: gpu-4

    Access ``config.compute["__default__"]`` or use ``resolve(tag)``
    to look up a cluster by node tag, falling back to ``__default__``.
    """

    @model_validator(mode="after")
    def _validate_default_key(self) -> "ComputeConfig":
        if "__default__" not in self.root:
            raise ValueError("ComputeConfig must contain a '__default__' key")
        return self

    def resolve(self, tag: Optional[str] = None) -> ClusterConfig:
        """Return the cluster for *tag*, falling back to ``__default__``."""
        if tag and tag in self.root:
            return self.root["__default__"].model_copy(
                update=self.root[tag].model_dump(exclude_none=True)
            )
        return self.root["__default__"]


class ExecutionConfig(BaseModel):
    """How code is packaged and run inside the Azure ML environment."""

    environment: Optional[str] = None
    code_directory: Optional[str] = None
    working_directory: Optional[str] = None


class CronScheduleConfig(BaseModel):
    """Maps to azure.ai.ml.entities.CronTrigger."""

    expression: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    time_zone: str = "UTC"


class RecurrencePatternConfig(BaseModel):
    """Maps to azure.ai.ml.entities.RecurrencePattern."""

    hours: Optional[List[int]] = None
    minutes: Optional[List[int]] = None
    week_days: Optional[List[str]] = None


class RecurrenceScheduleConfig(BaseModel):
    """Maps to azure.ai.ml.entities.RecurrenceTrigger."""

    frequency: str
    interval: int
    schedule: Optional[RecurrencePatternConfig] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    time_zone: str = "UTC"


class ScheduleConfig(BaseModel):
    """Exactly one of ``cron`` or ``recurrence`` must be set."""

    cron: Optional[CronScheduleConfig] = None
    recurrence: Optional[RecurrenceScheduleConfig] = None

    @model_validator(mode="after")
    def _validate_exactly_one_trigger(self) -> "ScheduleConfig":
        if self.cron and self.recurrence:
            raise ValueError(
                "ScheduleConfig must have exactly one of 'cron' or 'recurrence', not both"
            )
        if not self.cron and not self.recurrence:
            raise ValueError(
                "ScheduleConfig must have exactly one of 'cron' or 'recurrence'"
            )
        return self


class PipelineFilterOptions(BaseModel):
    """Kedro pipeline filter options – mirrors kedro-dagster's PipelineOptions."""

    pipeline_name: str = "__default__"
    from_nodes: Optional[List[str]] = None
    to_nodes: Optional[List[str]] = None
    node_names: Optional[List[str]] = None
    from_inputs: Optional[List[str]] = None
    to_outputs: Optional[List[str]] = None
    node_namespaces: Optional[List[str]] = None
    tags: Optional[List[str]] = None

    def to_filter_kwargs(self) -> Dict[str, Any]:
        """Return non-None filter kwargs suitable for ``Pipeline.filter()``."""
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
    """A single job configuration. ``schedule`` is optional — omit for ad-hoc jobs."""

    pipeline: PipelineFilterOptions
    workspace: Optional[str] = None
    experiment_name: Optional[str] = None
    display_name: Optional[str] = None
    compute: Optional[str] = None
    schedule: Optional[Union[ScheduleConfig, str]] = None
    description: Optional[str] = None


class KedroAzureMLConfig(BaseModel):
    workspace: WorkspacesConfig
    compute: ComputeConfig
    execution: ExecutionConfig = ExecutionConfig()
    schedules: Dict[str, ScheduleConfig] = {}
    jobs: Dict[str, JobConfig] = {}


CONFIG_TEMPLATE_YAML = """
workspace:
  __default__:
    # Azure subscription ID
    subscription_id: "{subscription_id}"
    # Azure resource group
    resource_group: "{resource_group}"
    # Azure ML Workspace name
    name: "{workspace_name}"

compute:
  __default__:
    cluster_name: "{cluster_name}"
  # gpu-nodes:
  #   cluster_name: "<gpu_cluster_name>"

execution:
  # Azure ML Environment to use during pipeline execution
  environment: {environment_name}
  # Path to directory to upload, or null to disable code upload
  code_directory: {code_directory}
  # Path to the directory in the Docker image to run the code from
  # Ignored when code_directory is set
  working_directory: /home/kedro_docker
""".strip()

# This auto-validates the template above during import
_CONFIG_TEMPLATE = KedroAzureMLConfig.model_validate(
    update_dict(
        yaml.safe_load(CONFIG_TEMPLATE_YAML),
        ("execution.code_directory", None),
        ("execution.environment", None),
    )
)
