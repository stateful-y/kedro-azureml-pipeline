"""Tests for the schedule configuration models, pipeline filtering, scheduler module,
and the ``kedro azureml submit`` CLI command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from azure.ai.ml.entities import CronTrigger, JobSchedule, RecurrenceTrigger
from kedro.pipeline import Pipeline, node, pipeline

from kedro_azureml_pipeline.config import (
    _CONFIG_TEMPLATE,
    CronScheduleConfig,
    JobConfig,
    KedroAzureMLConfig,
    PipelineFilterOptions,
    RecurrencePatternConfig,
    RecurrenceScheduleConfig,
    ScheduleConfig,
    WorkspaceConfig,
)
from kedro_azureml_pipeline.generator import AzureMLPipelineGenerator
from kedro_azureml_pipeline.scheduler import (
    build_job_schedule,
    build_trigger,
    resolve_schedule,
)
from tests.utils import create_kedro_conf_dirs, identity

FULL_CONFIG_YAML = """
workspace:
  __default__:
    subscription_id: "00000000-0000-0000-0000-000000000000"
    resource_group: "rg"
    name: "workspace"

compute:
  __default__:
    cluster_name: "unit-tests-cluster"

execution:
  environment: "aml-env@latest"
  code_directory: null
  working_directory: /home/kedro

schedules:
  daily_morning:
    cron:
      expression: "0 6 * * *"
      time_zone: "UTC"
  weekly_monday:
    recurrence:
      frequency: "week"
      interval: 1
      schedule:
        hours: [9]
        minutes: [0]
        week_days: ["Monday"]
      time_zone: "Eastern Standard Time"

jobs:
  etl_daily:
    pipeline:
      pipeline_name: __default__
      tags: ["etl"]
    schedule: daily_morning
    display_name: "Daily ETL Pipeline"
    description: "Runs ETL every morning"
  full_pipeline_weekly:
    pipeline:
      pipeline_name: __default__
      from_nodes: ["node1"]
      to_nodes: ["node3"]
    schedule: weekly_monday
  inline_schedule_job:
    pipeline:
      pipeline_name: __default__
    schedule:
      cron:
        expression: "30 12 * * *"
"""


@pytest.fixture()
def full_config() -> KedroAzureMLConfig:
    return KedroAzureMLConfig.model_validate(yaml.safe_load(FULL_CONFIG_YAML))


@pytest.fixture()
def tagged_pipeline() -> Pipeline:
    return pipeline([
        node(identity, inputs="input_data", outputs="i2", name="node1", tags=["etl"]),
        node(identity, inputs="i2", outputs="i3", name="node2", tags=["ml"]),
        node(identity, inputs="i3", outputs="output_data", name="node3", tags=["etl"]),
    ])


class TestConfigModels:
    """Schedule and pipeline filter config parsing."""

    def test_full_config_parses_correctly(self, full_config: KedroAzureMLConfig):
        assert full_config.schedules is not None
        assert "daily_morning" in full_config.schedules
        assert "weekly_monday" in full_config.schedules
        assert full_config.jobs is not None
        assert len(full_config.jobs) == 3

    def test_cron_schedule_parsed(self, full_config: KedroAzureMLConfig):
        daily = full_config.schedules["daily_morning"]
        assert daily.cron is not None
        assert daily.recurrence is None
        assert daily.cron.expression == "0 6 * * *"
        assert daily.cron.time_zone == "UTC"

    def test_recurrence_schedule_parsed(self, full_config: KedroAzureMLConfig):
        weekly = full_config.schedules["weekly_monday"]
        assert weekly.recurrence is not None
        assert weekly.cron is None
        assert weekly.recurrence.frequency == "week"
        assert weekly.recurrence.interval == 1
        assert weekly.recurrence.schedule.hours == [9]
        assert weekly.recurrence.schedule.week_days == ["Monday"]

    def test_job_config_parsed(self, full_config: KedroAzureMLConfig):
        etl = full_config.jobs["etl_daily"]
        assert etl.pipeline.pipeline_name == "__default__"
        assert etl.pipeline.tags == ["etl"]
        assert etl.schedule == "daily_morning"
        assert etl.display_name == "Daily ETL Pipeline"

    def test_inline_schedule_parsed(self, full_config: KedroAzureMLConfig):
        inline_job = full_config.jobs["inline_schedule_job"]
        assert isinstance(inline_job.schedule, ScheduleConfig)
        assert inline_job.schedule.cron.expression == "30 12 * * *"

    def test_backward_compatibility_no_schedules(self):
        """Existing configs without schedules/jobs still parse fine."""
        config = _CONFIG_TEMPLATE.model_copy(deep=True)
        assert config.schedules == {}
        assert config.jobs == {}

    def test_schedule_config_requires_exactly_one_trigger(self):
        with pytest.raises(ValueError, match="exactly one"):
            ScheduleConfig(cron=None, recurrence=None)

        with pytest.raises(ValueError, match="exactly one"):
            ScheduleConfig(
                cron=CronScheduleConfig(expression="0 0 * * *"),
                recurrence=RecurrenceScheduleConfig(frequency="day", interval=1),
            )

    def test_pipeline_filter_options_to_filter_kwargs(self):
        opts = PipelineFilterOptions(
            pipeline_name="my_pipe",
            tags=["t1", "t2"],
            from_nodes=["n1"],
        )
        kwargs = opts.to_filter_kwargs()
        assert kwargs == {"tags": ["t1", "t2"], "from_nodes": ["n1"]}

    def test_pipeline_filter_options_empty_when_no_filters(self):
        opts = PipelineFilterOptions(pipeline_name="__default__")
        assert opts.to_filter_kwargs() == {}


class TestPipelineFiltering:
    """Generator pipeline filtering via ``PipelineFilterOptions``."""

    def test_generator_with_tag_filter(self, tagged_pipeline, dummy_plugin_config, multi_catalog):
        filter_opts = PipelineFilterOptions(
            pipeline_name="test_pipe",
            tags=["etl"],
        )
        with patch.object(
            AzureMLPipelineGenerator,
            "get_kedro_pipeline",
            return_value=tagged_pipeline,
        ):
            generator = AzureMLPipelineGenerator(
                "test_pipe",
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="test/env@latest",
                filter_options=filter_opts,
            )
            job = generator.generate()
            # Only node1 and node3 have the "etl" tag
            assert set(job.jobs.keys()) == {"node1", "node3"}

    def test_generator_with_from_to_nodes_filter(self, tagged_pipeline, dummy_plugin_config, multi_catalog):
        filter_opts = PipelineFilterOptions(
            pipeline_name="test_pipe",
            from_nodes=["node2"],
            to_nodes=["node3"],
        )
        with patch.object(
            AzureMLPipelineGenerator,
            "get_kedro_pipeline",
            return_value=tagged_pipeline,
        ):
            generator = AzureMLPipelineGenerator(
                "test_pipe",
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="test/env@latest",
                filter_options=filter_opts,
            )
            job = generator.generate()
            assert set(job.jobs.keys()) == {"node2", "node3"}

    def test_generator_without_filter_keeps_all_nodes(self, tagged_pipeline, dummy_plugin_config, multi_catalog):
        with patch.object(
            AzureMLPipelineGenerator,
            "get_kedro_pipeline",
            return_value=tagged_pipeline,
        ):
            generator = AzureMLPipelineGenerator(
                "test_pipe",
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="test/env@latest",
            )
            job = generator.generate()
            assert set(job.jobs.keys()) == {"node1", "node2", "node3"}


class TestScheduler:
    """Schedule resolution, trigger building, and job schedule creation."""

    def test_resolve_schedule_by_name(self, full_config: KedroAzureMLConfig):
        result = resolve_schedule("daily_morning", full_config.schedules)
        assert result.cron is not None
        assert result.cron.expression == "0 6 * * *"

    def test_resolve_schedule_inline(self):
        inline = ScheduleConfig(cron=CronScheduleConfig(expression="15 10 * * *"))
        result = resolve_schedule(inline, None)
        assert result is inline

    def test_resolve_schedule_missing_raises(self):
        with pytest.raises(KeyError, match="not_real"):
            resolve_schedule("not_real", {})

    def test_build_cron_trigger(self):
        cfg = ScheduleConfig(
            cron=CronScheduleConfig(
                expression="0 6 * * *",
                time_zone="Eastern Standard Time",
                start_time="2025-01-01T00:00:00",
            )
        )
        trigger = build_trigger(cfg)
        assert isinstance(trigger, CronTrigger)
        assert trigger.expression == "0 6 * * *"
        assert trigger.time_zone == "Eastern Standard Time"

    def test_build_recurrence_trigger(self):
        cfg = ScheduleConfig(
            recurrence=RecurrenceScheduleConfig(
                frequency="week",
                interval=2,
                schedule=RecurrencePatternConfig(hours=[10], minutes=[30], week_days=["Monday", "Friday"]),
                time_zone="UTC",
            )
        )
        trigger = build_trigger(cfg)
        assert isinstance(trigger, RecurrenceTrigger)
        assert trigger.frequency == "week"
        assert trigger.interval == 2

    def test_build_job_schedule(self):
        trigger = CronTrigger(expression="0 6 * * *")
        mock_job = MagicMock()
        schedule = build_job_schedule(
            name="test_schedule",
            trigger=trigger,
            pipeline_job=mock_job,
            display_name="Test Display",
            description="A test schedule",
        )
        assert isinstance(schedule, JobSchedule)
        assert schedule.name == "test_schedule"


class TestScheduleCLI:
    """``kedro azureml schedule`` CLI integration."""

    def test_schedule_workspace_and_env_echo(
        self,
        tagged_pipeline,
        dummy_plugin_config,
        multi_catalog,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """``--workspace`` and ``--azureml-environment`` echo overrides."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)
        dummy_plugin_config.schedules = {
            "daily": ScheduleConfig(cron=CronScheduleConfig(expression="0 6 * * *")),
        }
        dummy_plugin_config.jobs = {
            "test_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                schedule="daily",
            ),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = multi_catalog
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=tagged_pipeline,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.schedule,
                ["-j", "test_job", "--dry-run", "--workspace", "__default__", "--azureml-environment", "my-env@latest"],
                obj=cli_context,
            )
            assert result.exit_code == 0, result.output
            assert "Overriding workspace to: __default__" in result.output
            assert "Overriding Azure ML Environment to: my-env@latest" in result.output

    def test_schedule_failure_exit_code(
        self,
        tagged_pipeline,
        dummy_plugin_config,
        multi_catalog,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """When a schedule fails, exit code is non-zero."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager
        from kedro_azureml_pipeline.scheduler import AzureMLScheduleClient

        create_kedro_conf_dirs(tmp_path)
        dummy_plugin_config.schedules = {
            "daily": ScheduleConfig(cron=CronScheduleConfig(expression="0 6 * * *")),
        }
        dummy_plugin_config.jobs = {
            "test_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                schedule="daily",
            ),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = multi_catalog
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=tagged_pipeline,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.object(
                AzureMLScheduleClient,
                "create_or_update_schedule",
                side_effect=RuntimeError("Azure error"),
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.schedule,
                ["-j", "test_job"],
                obj=cli_context,
            )
            assert result.exit_code == 1
            assert "Some schedules failed" in result.output
            assert "Failed to schedule job" in result.output

    def test_schedule_succeeds_non_dry_run(
        self,
        tagged_pipeline,
        dummy_plugin_config,
        multi_catalog,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """Non-dry-run success echoes the created schedule name."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager
        from kedro_azureml_pipeline.scheduler import AzureMLScheduleClient

        create_kedro_conf_dirs(tmp_path)
        dummy_plugin_config.schedules = {
            "daily": ScheduleConfig(cron=CronScheduleConfig(expression="0 6 * * *")),
        }
        dummy_plugin_config.jobs = {
            "test_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                schedule="daily",
            ),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = multi_catalog
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        mock_result = MagicMock()
        mock_result.name = "test_job"

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=tagged_pipeline,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.object(
                AzureMLScheduleClient,
                "create_or_update_schedule",
                return_value=mock_result,
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.schedule,
                ["-j", "test_job"],
                obj=cli_context,
            )
            assert result.exit_code == 0, result.output
            assert "created/updated successfully" in result.output
            assert "All schedules created successfully" in result.output

    def test_schedule_dry_run(
        self,
        tagged_pipeline,
        dummy_plugin_config,
        multi_catalog,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """--dry-run should report what would be created without calling Azure."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)

        # Extend plugin config with schedules + jobs
        dummy_plugin_config.schedules = {
            "daily": ScheduleConfig(cron=CronScheduleConfig(expression="0 6 * * *")),
        }
        dummy_plugin_config.jobs = {
            "test_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                schedule="daily",
            ),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = multi_catalog
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=tagged_pipeline,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.schedule,
                ["-j", "test_job", "--dry-run"],
                obj=cli_context,
            )
            assert result.exit_code == 0, result.output
            assert "[DRY RUN]" in result.output
            assert "test_job" in result.output

    def test_schedule_job_filter(
        self,
        tagged_pipeline,
        dummy_plugin_config,
        multi_catalog,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """--job flag should filter to only the named job."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)

        dummy_plugin_config.schedules = {
            "daily": ScheduleConfig(cron=CronScheduleConfig(expression="0 6 * * *")),
        }
        dummy_plugin_config.jobs = {
            "job_a": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                schedule="daily",
            ),
            "job_b": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                schedule="daily",
            ),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = multi_catalog
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=tagged_pipeline,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.schedule,
                ["--dry-run", "-j", "job_a"],
                obj=cli_context,
            )
            assert result.exit_code == 0, result.output
            assert "job_a" in result.output
            assert "job_b" not in result.output
            assert "1 succeeded" in result.output

    def test_schedule_missing_job_name_errors(
        self,
        dummy_plugin_config,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """Requesting a non-existent job name should error."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)

        dummy_plugin_config.schedules = {
            "daily": ScheduleConfig(cron=CronScheduleConfig(expression="0 6 * * *")),
        }
        dummy_plugin_config.jobs = {
            "real_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                schedule="daily",
            ),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.schedule,
                ["--dry-run", "-j", "nonexistent"],
                obj=cli_context,
            )
            assert result.exit_code != 0
            assert "not found" in result.output

    def test_schedule_no_jobs_config_errors(
        self,
        dummy_plugin_config,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """Schedule should error when no jobs section exists in config."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)

        # No jobs configured
        assert dummy_plugin_config.jobs == {}

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.schedule,
                ["-j", "any_job", "--dry-run"],
                obj=cli_context,
            )
            assert result.exit_code != 0
            assert "No 'jobs' section" in result.output

    def test_schedule_job_without_schedule_config_errors(
        self,
        tagged_pipeline,
        dummy_plugin_config,
        multi_catalog,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """Schedule should error when a job has no schedule configured."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)

        dummy_plugin_config.jobs = {
            "no_schedule_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
            ),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = multi_catalog
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=tagged_pipeline,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.schedule,
                ["-j", "no_schedule_job", "--dry-run"],
                obj=cli_context,
            )
            assert result.exit_code != 0
            assert "no schedule configured" in result.output


class TestRunCLI:
    """``kedro azureml run`` CLI integration."""

    def test_run_dry_run(
        self,
        tagged_pipeline,
        dummy_plugin_config,
        multi_catalog,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """--dry-run should report what would be run without calling Azure."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)

        dummy_plugin_config.jobs = {
            "test_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
            ),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = multi_catalog
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=tagged_pipeline,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.run,
                ["-j", "test_job", "--dry-run"],
                obj=cli_context,
            )
            assert result.exit_code == 0, result.output
            assert "[DRY RUN]" in result.output
            assert "Would run" in result.output
            assert "test_job" in result.output

    def test_run_ignores_schedule_config(
        self,
        tagged_pipeline,
        dummy_plugin_config,
        multi_catalog,
        patched_kedro_package,
        cli_context,
        tmp_path,
    ):
        """run should ignore schedule config and run immediately."""
        from click.testing import CliRunner

        import kedro_azureml_pipeline.cli.commands as cli
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)

        dummy_plugin_config.schedules = {
            "daily": ScheduleConfig(cron=CronScheduleConfig(expression="0 6 * * *")),
        }
        dummy_plugin_config.jobs = {
            "scheduled_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                schedule="daily",
            ),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = multi_catalog
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=tagged_pipeline,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.run,
                ["-j", "scheduled_job", "--dry-run"],
                obj=cli_context,
            )
            assert result.exit_code == 0, result.output
            assert "[DRY RUN]" in result.output
            assert "Would run" in result.output
            assert "Would create schedule" not in result.output


class TestBuildTriggerEdgeCases:
    """Coverage for optional trigger fields (start_time, end_time, pattern)."""

    def test_cron_trigger_with_start_and_end_time(self):
        cfg = ScheduleConfig(
            cron=CronScheduleConfig(
                expression="0 6 * * *",
                start_time="2025-01-01T00:00:00",
                end_time="2025-12-31T23:59:59",
            )
        )
        trigger = build_trigger(cfg)
        assert isinstance(trigger, CronTrigger)
        assert trigger.start_time == "2025-01-01T00:00:00"
        assert trigger.end_time == "2025-12-31T23:59:59"

    def test_recurrence_trigger_with_start_and_end_time(self):
        cfg = ScheduleConfig(
            recurrence=RecurrenceScheduleConfig(
                frequency="day",
                interval=1,
                start_time="2025-01-01T00:00:00",
                end_time="2025-12-31T23:59:59",
            )
        )
        trigger = build_trigger(cfg)
        assert isinstance(trigger, RecurrenceTrigger)
        assert trigger.start_time == "2025-01-01T00:00:00"
        assert trigger.end_time == "2025-12-31T23:59:59"

    def test_recurrence_trigger_without_schedule_pattern(self):
        """Recurrence without a pattern (no hours/minutes/weekdays)."""
        cfg = ScheduleConfig(
            recurrence=RecurrenceScheduleConfig(
                frequency="hour",
                interval=4,
            )
        )
        trigger = build_trigger(cfg)
        assert isinstance(trigger, RecurrenceTrigger)
        assert trigger.frequency == "hour"
        assert trigger.interval == 4

    def test_recurrence_trigger_with_partial_pattern(self):
        """Recurrence with only hours and minutes set in the pattern."""
        cfg = ScheduleConfig(
            recurrence=RecurrenceScheduleConfig(
                frequency="day",
                interval=1,
                schedule=RecurrencePatternConfig(hours=[9, 17], minutes=[0]),
            )
        )
        trigger = build_trigger(cfg)
        assert isinstance(trigger, RecurrenceTrigger)

    def test_recurrence_trigger_full_pattern(self):
        """Recurrence with hours, minutes, and week_days in the pattern."""
        cfg = ScheduleConfig(
            recurrence=RecurrenceScheduleConfig(
                frequency="week",
                interval=1,
                schedule=RecurrencePatternConfig(
                    hours=[9],
                    minutes=[0, 30],
                    week_days=["Monday", "Friday"],
                ),
            )
        )
        trigger = build_trigger(cfg)
        assert isinstance(trigger, RecurrenceTrigger)
        assert trigger.schedule.hours == [9]
        assert trigger.schedule.minutes == [0, 30]
        assert trigger.schedule.week_days == ["Monday", "Friday"]


class TestAzureMLScheduleClient:
    """Coverage for schedule client create/update."""

    def test_create_or_update_schedule(self):
        from kedro_azureml_pipeline.scheduler import AzureMLScheduleClient

        schedule_client = AzureMLScheduleClient()
        mock_schedule = MagicMock(spec=JobSchedule)
        mock_workspace = MagicMock(spec=WorkspaceConfig)

        with patch("kedro_azureml_pipeline.scheduler._get_azureml_client") as mock_ctx:
            mock_ml_client = MagicMock()
            mock_result = MagicMock()
            mock_result.name = "test-schedule"
            mock_ml_client.schedules.begin_create_or_update.return_value.result.return_value = mock_result
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ml_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = schedule_client.create_or_update_schedule(mock_schedule, mock_workspace)
            assert result.name == "test-schedule"
            mock_ml_client.schedules.begin_create_or_update.assert_called_once_with(schedule=mock_schedule)
