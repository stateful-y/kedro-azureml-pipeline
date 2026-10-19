"""Tests for the Pydantic configuration models."""

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from kedro_azureml_pipeline.config import (
    _CONFIG_TEMPLATE,
    ClusterConfig,
    ComputeConfig,
    CronScheduleConfig,
    ExecutionConfig,
    JobConfig,
    KedroAzureMLConfig,
    LimitsConfig,
    NotificationConfig,
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


class TestClusterConfig:
    """Single compute entry fields."""

    def test_instance_type_defaults_to_none(self):
        cluster = ClusterConfig(cluster_name="cpu")
        assert cluster.instance_type is None

    def test_instance_type_loads(self):
        cluster = ClusterConfig(cluster_name="k8s-compute", instance_type="gpu-large")
        assert cluster.instance_type == "gpu-large"

    def test_unknown_key_is_rejected_by_name(self):
        with pytest.raises(ValidationError, match="node_selector"):
            ClusterConfig(cluster_name="cpu", node_selector="gpu=true")


class TestComputeConfig:
    """Keyed compute lookup with ``__default__`` enforcement."""

    def test_requires_default_key(self):
        with pytest.raises(ValueError, match="__default__"):
            ComputeConfig(root={"gpu": ClusterConfig(cluster_name="gpu-cluster")})

    def test_default_entry_requires_cluster_name(self):
        with pytest.raises(ValueError, match="cluster_name"):
            ComputeConfig(root={"__default__": ClusterConfig(instance_type="gpu-large")})

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

    def test_resolve_instance_type_only_inherits_cluster_name(self):
        cc = ComputeConfig(
            root={
                "__default__": ClusterConfig(cluster_name="k8s-compute"),
                "gpu": ClusterConfig(instance_type="gpu-large"),
            }
        )
        resolved = cc.resolve("gpu")
        assert resolved.cluster_name == "k8s-compute"
        assert resolved.instance_type == "gpu-large"

    def test_resolve_cluster_name_only_inherits_instance_type(self):
        cc = ComputeConfig(
            root={
                "__default__": ClusterConfig(cluster_name="k8s-compute", instance_type="cpu-small"),
                "other": ClusterConfig(cluster_name="other-compute"),
            }
        )
        resolved = cc.resolve("other")
        assert resolved.cluster_name == "other-compute"
        assert resolved.instance_type == "cpu-small"


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


class TestLimitsConfig:
    """Run-duration limit validation."""

    def test_basic_creation(self):
        lc = LimitsConfig(timeout=3600)
        assert lc.timeout == 3600

    def test_zero_timeout_raises(self):
        with pytest.raises(ValidationError):
            LimitsConfig(timeout=0)

    def test_negative_timeout_raises(self):
        with pytest.raises(ValidationError):
            LimitsConfig(timeout=-1)

    def test_timeout_is_required(self):
        with pytest.raises(ValidationError):
            LimitsConfig()

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            LimitsConfig(timeout=60, max_retries=3)


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

    def test_params_default_none(self):
        jc = JobConfig(pipeline=PipelineFilterOptions(pipeline_name="pipe"))
        assert jc.params is None

    def test_params_set(self):
        jc = JobConfig(
            pipeline=PipelineFilterOptions(pipeline_name="pipe"),
            params={"arena_snapshot": "2026-06", "model.lr": 0.01},
        )
        assert jc.params == {"arena_snapshot": "2026-06", "model.lr": 0.01}


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

    def test_yaml_round_trip_with_limits(self):
        """`limits` survives a full YAML round trip through the top-level config."""
        raw = """
workspace:
  __default__:
    subscription_id: "sub"
    resource_group: "rg"
    name: "ws"
compute:
  __default__:
    cluster_name: "cpu"
jobs:
  inference:
    pipeline:
      pipeline_name: model_inference
    limits:
      timeout: 3600
"""
        cfg = KedroAzureMLConfig.model_validate(yaml.safe_load(raw))
        assert cfg.jobs["inference"].limits is not None
        assert cfg.jobs["inference"].limits.timeout == 3600

    def test_limits_default_none(self):
        jc = JobConfig(pipeline=PipelineFilterOptions(pipeline_name="pipe"))
        assert jc.limits is None

    def test_yaml_with_retry_is_rejected(self):
        """`retry` was removed; extra="forbid" must surface it by name, not ignore it.

        Azure ML only honours retry_settings on parallel and sweep jobs, never on the
        command steps this plugin emits, so the setting was removed rather than left
        to look effective. A project upgrading with a stale `retry:` block must be
        told which key to delete.
        """
        raw = """
workspace:
  __default__:
    subscription_id: "sub"
    resource_group: "rg"
    name: "ws"
compute:
  __default__:
    cluster_name: "cpu"
jobs:
  inference:
    pipeline:
      pipeline_name: model_inference
    retry:
      max_retries: 3
      timeout: 3600
"""
        with pytest.raises(ValidationError) as excinfo:
            KedroAzureMLConfig.model_validate(yaml.safe_load(raw))
        assert "retry" in str(excinfo.value)


class TestWorkspaceConfigProperty:
    """Property-based tests for WorkspaceConfig."""

    @given(
        sub=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Pd"))),
        rg=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Pd"))),
        name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Pd"))),
    )
    def test_workspace_round_trips_fields(self, sub, rg, name):
        """WorkspaceConfig preserves all three fields."""
        ws = WorkspaceConfig(subscription_id=sub, resource_group=rg, name=name)
        assert ws.subscription_id == sub
        assert ws.resource_group == rg
        assert ws.name == name


class TestScheduleConfigProperty:
    """Property-based tests for ScheduleConfig triggers."""

    @given(expression=st.from_regex(r"[0-9*/, -]{5,30}", fullmatch=True))
    def test_cron_accepts_any_expression_string(self, expression):
        """ScheduleConfig with cron accepts arbitrary expression strings."""
        sc = ScheduleConfig(cron=CronScheduleConfig(expression=expression))
        assert sc.cron.expression == expression


def _config_with_notifications(notifications: dict, jobs: dict) -> dict:
    """Minimal ``azureml.yml`` mapping with the given notifications and jobs."""
    return {
        "workspace": {"__default__": {"subscription_id": "s", "resource_group": "r", "name": "n"}},
        "compute": {"__default__": {"cluster_name": "c"}},
        "notifications": notifications,
        "jobs": jobs,
    }


class TestNotificationConfig:
    """Webhook notification definitions and their job references."""

    def test_minimal_definition_defaults(self):
        cfg = NotificationConfig(webhook_env="SLACK_WEBHOOK_URL", events=["failure"])
        assert cfg.payload is None
        assert cfg.wait_timeout == 1800

    def test_explicit_none_payload_accepted(self):
        assert NotificationConfig(webhook_env="X", events=["failure"], payload=None).payload is None

    def test_payload_reference_accepted(self):
        cfg = NotificationConfig(webhook_env="X", events=["start"], payload="pkg.mod:build")
        assert cfg.payload == "pkg.mod:build"

    @pytest.mark.parametrize("payload", ["nocolon", ":build", "pkg.mod:"])
    def test_payload_reference_shape_enforced(self, payload):
        with pytest.raises(ValidationError, match="module.path:function_name"):
            NotificationConfig(webhook_env="X", events=["start"], payload=payload)

    def test_invalid_event_rejected(self):
        with pytest.raises(ValidationError, match="'start', 'success', 'failure', 'warning' or 'recovered'"):
            NotificationConfig(webhook_env="X", events=["bogus"])

    def test_warning_and_recovered_events_parse_with_their_defaults(self):
        cfg = NotificationConfig(webhook_env="X", events=["failure", "warning", "recovered"])
        assert cfg.events == ["failure", "warning", "recovered"]
        assert (cfg.warning_repeat_hours, cfg.warning_repeat_tolerance_minutes) == (24, 15)

    @pytest.mark.parametrize(
        ("field", "value"), [("warning_repeat_hours", 0), ("warning_repeat_tolerance_minutes", -1)]
    )
    def test_out_of_range_repeat_settings_are_refused(self, field, value):
        with pytest.raises(ValidationError, match=field):
            NotificationConfig(webhook_env="X", events=["warning"], **{field: value})

    def test_empty_events_rejected(self):
        with pytest.raises(ValidationError, match="at least 1"):
            NotificationConfig(webhook_env="X", events=[])

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            NotificationConfig(webhook_env="X", events=["start"], icon=":bell:")

    def test_slack_api_transport_needs_no_webhook(self):
        cfg = NotificationConfig(token_env="SLACK_BOT_TOKEN", channel="C0123456789", events=["start"])
        assert cfg.webhook_env is None
        assert cfg.model_dump()["channel"] == "C0123456789"

    def test_both_transports_accepted(self):
        cfg = NotificationConfig(webhook_env="X", token_env="T", channel="C1", events=["start"])
        assert (cfg.webhook_env, cfg.token_env, cfg.channel) == ("X", "T", "C1")

    @pytest.mark.parametrize("extra", [{"token_env": "T"}, {"channel": "C1"}])
    def test_token_and_channel_go_together(self, extra):
        with pytest.raises(ValidationError, match="token_env and channel must be set together"):
            NotificationConfig(webhook_env="X", events=["start"], **extra)

    def test_no_transport_rejected(self):
        with pytest.raises(ValidationError, match="webhook_env, or token_env with channel"):
            NotificationConfig(events=["start"])

    def test_yaml_events_key_is_not_a_boolean(self):
        """``events`` was chosen over ``on`` because YAML 1.1 reads a bare ``on`` as true."""
        parsed = yaml.safe_load("events: [start, failure]\nwebhook_env: X")
        assert NotificationConfig.model_validate(parsed).events == ["start", "failure"]

    def test_job_reference_resolves(self):
        cfg = KedroAzureMLConfig.model_validate(
            _config_with_notifications(
                {"alerts": {"webhook_env": "SLACK_WEBHOOK_URL", "events": ["start", "failure"]}},
                {
                    "nightly": {
                        "pipeline": {"pipeline_name": "p"},
                        "notifications": "alerts",
                        "limits": {"timeout": 3600},
                    }
                },
            )
        )
        assert cfg.jobs["nightly"].notifications == "alerts"
        assert cfg.notifications["alerts"].events == ["start", "failure"]

    def test_unknown_reference_rejected(self):
        with pytest.raises(ValidationError, match="Job 'nightly' references notification 'nope'"):
            KedroAzureMLConfig.model_validate(
                _config_with_notifications(
                    {}, {"nightly": {"pipeline": {"pipeline_name": "p"}, "notifications": "nope"}}
                )
            )

    def test_wait_timeout_equal_to_step_timeout_rejected(self):
        with pytest.raises(
            ValidationError, match=r"wait_timeout \(1800s\) must be below the job's limits.timeout \(1800s\)"
        ):
            KedroAzureMLConfig.model_validate(
                _config_with_notifications(
                    {"alerts": {"webhook_env": "X", "events": ["success"]}},
                    {
                        "nightly": {
                            "pipeline": {"pipeline_name": "p"},
                            "notifications": "alerts",
                            "limits": {"timeout": 1800},
                        }
                    },
                )
            )

    def test_wait_timeout_below_step_timeout_accepted(self):
        cfg = KedroAzureMLConfig.model_validate(
            _config_with_notifications(
                {"alerts": {"webhook_env": "X", "events": ["success"], "wait_timeout": 600}},
                {
                    "nightly": {
                        "pipeline": {"pipeline_name": "p"},
                        "notifications": "alerts",
                        "limits": {"timeout": 601},
                    }
                },
            )
        )
        assert cfg.notifications["alerts"].wait_timeout == 600

    def test_no_step_timeout_accepts_any_wait(self):
        cfg = KedroAzureMLConfig.model_validate(
            _config_with_notifications(
                {"alerts": {"webhook_env": "X", "events": ["success"], "wait_timeout": 99999}},
                {"nightly": {"pipeline": {"pipeline_name": "p"}, "notifications": "alerts"}},
            )
        )
        assert cfg.jobs["nightly"].limits is None

    def test_job_without_reference_ignores_definitions(self):
        cfg = KedroAzureMLConfig.model_validate(
            _config_with_notifications(
                {"alerts": {"webhook_env": "X", "events": ["success"]}},
                {"nightly": {"pipeline": {"pipeline_name": "p"}}},
            )
        )
        assert cfg.jobs["nightly"].notifications is None
