"""Tests for the Pydantic configuration models."""

import pytest
import yaml
from pydantic import ValidationError

from kedro_azureml_pipeline.config import (
    _CONFIG_TEMPLATE,
    ClusterConfig,
    ComputeConfig,
    CronScheduleConfig,
    ExecutionConfig,
    JobConfig,
    KedroAzureMLConfig,
    PipelineFilterOptions,
    RecurrencePatternConfig,
    RecurrenceScheduleConfig,
    ScheduleConfig,
    WorkspaceConfig,
    WorkspacesConfig,
)


class TestWorkspaceConfig:
    """Atomic workspace config fields."""

    def test_basic_creation(self):
        ws = WorkspaceConfig(subscription_id="sub-1", resource_group="rg-1", name="ws-1")
        assert ws.subscription_id == "sub-1"
        assert ws.resource_group == "rg-1"
        assert ws.name == "ws-1"

    def test_missing_field_raises(self):
        with pytest.raises(ValidationError):
            WorkspaceConfig(subscription_id="sub-1", resource_group="rg-1")


class TestWorkspacesConfig:
    """Keyed workspace lookup with ``__default__`` enforcement."""

    def test_requires_default_key(self):
        with pytest.raises(ValueError, match="__default__"):
            WorkspacesConfig(root={"other": WorkspaceConfig(subscription_id="s", resource_group="r", name="n")})

    def test_resolve_returns_default(self):
        ws = WorkspacesConfig(root={"__default__": WorkspaceConfig(subscription_id="s", resource_group="r", name="n")})
        assert ws.resolve().name == "n"
        assert ws.resolve(None).name == "n"

    def test_resolve_named_workspace(self):
        ws = WorkspacesConfig(
            root={
                "__default__": WorkspaceConfig(subscription_id="s", resource_group="r", name="default"),
                "prod": WorkspaceConfig(subscription_id="s", resource_group="r", name="prod-ws"),
            }
        )
        assert ws.resolve("prod").name == "prod-ws"

    def test_resolve_missing_workspace_raises(self):
        ws = WorkspacesConfig(root={"__default__": WorkspaceConfig(subscription_id="s", resource_group="r", name="n")})
        with pytest.raises(KeyError, match="missing"):
            ws.resolve("missing")


class TestComputeConfig:
    """Keyed compute lookup with ``__default__`` enforcement."""

    def test_requires_default_key(self):
        with pytest.raises(ValueError, match="__default__"):
            ComputeConfig(root={"gpu": ClusterConfig(cluster_name="gpu-cluster")})

    def test_resolve_returns_default(self):
        cc = ComputeConfig(root={"__default__": ClusterConfig(cluster_name="cpu")})
        assert cc.resolve().cluster_name == "cpu"
        assert cc.resolve(None).cluster_name == "cpu"

    def test_resolve_known_tag_merges_with_default(self):
        cc = ComputeConfig(
            root={
                "__default__": ClusterConfig(cluster_name="cpu"),
                "gpu": ClusterConfig(cluster_name="gpu-cluster"),
            }
        )
        resolved = cc.resolve("gpu")
        assert resolved.cluster_name == "gpu-cluster"

    def test_resolve_unknown_tag_returns_default(self):
        cc = ComputeConfig(root={"__default__": ClusterConfig(cluster_name="cpu")})
        assert cc.resolve("nonexistent").cluster_name == "cpu"


class TestExecutionConfig:
    """Execution config defaults."""

    def test_defaults_are_none(self):
        ec = ExecutionConfig()
        assert ec.environment is None
        assert ec.code_directory is None
        assert ec.working_directory is None

    def test_all_fields_set(self):
        ec = ExecutionConfig(environment="env@latest", code_directory=".", working_directory="/home/kedro")
        assert ec.environment == "env@latest"


class TestScheduleConfig:
    """Schedule trigger validation."""

    def test_cron_only(self):
        sc = ScheduleConfig(cron=CronScheduleConfig(expression="0 6 * * *"))
        assert sc.cron is not None
        assert sc.recurrence is None

    def test_recurrence_only(self):
        sc = ScheduleConfig(recurrence=RecurrenceScheduleConfig(frequency="day", interval=1))
        assert sc.recurrence is not None
        assert sc.cron is None

    def test_neither_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            ScheduleConfig(cron=None, recurrence=None)

    def test_both_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            ScheduleConfig(
                cron=CronScheduleConfig(expression="0 0 * * *"),
                recurrence=RecurrenceScheduleConfig(frequency="day", interval=1),
            )


class TestRecurrencePatternConfig:
    """Recurrence pattern optional fields."""

    def test_all_none_by_default(self):
        rpc = RecurrencePatternConfig()
        assert rpc.hours is None
        assert rpc.minutes is None
        assert rpc.week_days is None

    def test_populated(self):
        rpc = RecurrencePatternConfig(hours=[9], minutes=[0], week_days=["Monday"])
        assert rpc.hours == [9]


class TestPipelineFilterOptions:
    """Pipeline filter kwargs generation."""

    def test_defaults(self):
        opts = PipelineFilterOptions()
        assert opts.pipeline_name == "__default__"
        assert opts.to_filter_kwargs() == {}

    def test_all_filters_set(self):
        opts = PipelineFilterOptions(
            pipeline_name="pipe",
            tags=["t1"],
            from_nodes=["n1"],
            to_nodes=["n2"],
            node_names=["n3"],
            from_inputs=["in"],
            to_outputs=["out"],
            node_namespaces=["ns"],
        )
        kwargs = opts.to_filter_kwargs()
        assert "tags" in kwargs
        assert "from_nodes" in kwargs
        assert len(kwargs) == 7

    def test_partial_filters(self):
        opts = PipelineFilterOptions(pipeline_name="p", tags=["etl"])
        assert opts.to_filter_kwargs() == {"tags": ["etl"]}


class TestJobConfig:
    """Job config defaults and optional fields."""

    def test_minimal(self):
        jc = JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__"))
        assert jc.workspace is None
        assert jc.schedule is None
        assert jc.display_name is None

    def test_with_inline_schedule(self):
        jc = JobConfig(
            pipeline=PipelineFilterOptions(pipeline_name="pipe"),
            schedule=ScheduleConfig(cron=CronScheduleConfig(expression="0 0 * * *")),
        )
        assert isinstance(jc.schedule, ScheduleConfig)

    def test_with_named_schedule_ref(self):
        jc = JobConfig(
            pipeline=PipelineFilterOptions(pipeline_name="pipe"),
            schedule="daily_morning",
        )
        assert jc.schedule == "daily_morning"


class TestKedroAzureMLConfig:
    """Top-level config parsing and template."""

    def test_config_template_is_valid(self):
        assert _CONFIG_TEMPLATE.workspace.resolve().subscription_id == "<subscription_id>"
        assert _CONFIG_TEMPLATE.compute.resolve().cluster_name == "<cluster_name>"
        assert _CONFIG_TEMPLATE.execution.environment == "<environment>"

    def test_empty_schedules_and_jobs_by_default(self):
        cfg = KedroAzureMLConfig(
            workspace=WorkspacesConfig(
                root={"__default__": WorkspaceConfig(subscription_id="s", resource_group="r", name="n")}
            ),
            compute=ComputeConfig(root={"__default__": ClusterConfig(cluster_name="cpu")}),
        )
        assert cfg.schedules == {}
        assert cfg.jobs == {}

    def test_full_yaml_round_trip(self):
        raw = """
workspace:
  __default__:
    subscription_id: "sub"
    resource_group: "rg"
    name: "ws"
compute:
  __default__:
    cluster_name: "cpu"
execution:
  environment: "env@latest"
schedules:
  daily:
    cron:
      expression: "0 6 * * *"
jobs:
  etl:
    pipeline:
      pipeline_name: __default__
    schedule: daily
"""
        cfg = KedroAzureMLConfig.model_validate(yaml.safe_load(raw))
        assert cfg.workspace.resolve().name == "ws"
        assert "daily" in cfg.schedules
        assert cfg.jobs["etl"].schedule == "daily"
