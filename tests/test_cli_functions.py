"""Tests for CLI helper functions."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest

from kedro_azureml_pipeline.cli.functions import (
    _read_mlflow_experiment_name,
    default_job_callback,
    dynamic_import_job_schedule_func_from_str,
    parse_extra_env_params,
    parse_runtime_params,
    verify_configuration_directory_for_azure,
    warn_about_ignore_files,
)
from kedro_azureml_pipeline.utils import CliContext


class TestParseRuntimeParams:
    """JSON parameter parsing."""

    def test_valid_json(self):
        result = parse_runtime_params('{"a": 1}', silent=True)
        assert result == {"a": 1}

    def test_empty_string_returns_none(self):
        assert parse_runtime_params("", silent=True) is None

    def test_falsy_returns_none(self):
        assert parse_runtime_params(None, silent=True) is None

    def test_quoted_json(self):
        result = parse_runtime_params('\'{"key": "value"}\'', silent=True)
        assert result == {"key": "value"}


class TestParseExtraEnvParams:
    """KEY=VALUE environment variable parsing."""

    def test_valid_entries(self):
        result = parse_extra_env_params(["A=B", "C=D"])
        assert result == {"A": "B", "C": "D"}

    def test_value_with_equals(self):
        result = parse_extra_env_params(["A=B=C"])
        assert result == {"A": "B=C"}

    def test_empty_value(self):
        result = parse_extra_env_params(["KEY="])
        assert result == {"KEY": ""}

    def test_invalid_format_raises(self):
        with pytest.raises(Exception, match="Invalid env-var"):
            parse_extra_env_params(["NO_EQUALS"])

    def test_invalid_key_raises(self):
        with pytest.raises(Exception, match="Invalid env-var"):
            parse_extra_env_params(["2+2=4"])

    def test_empty_list(self):
        assert parse_extra_env_params([]) == {}


class TestDynamicImportJobScheduleFunc:
    """Dynamic function import from dotted paths."""

    def test_returns_none_for_none_input(self):
        result = dynamic_import_job_schedule_func_from_str(ctx=MagicMock(), param=MagicMock(), import_str=None)
        assert result is None

    def test_bad_format_raises(self):
        with pytest.raises(click.BadParameter, match="format"):
            dynamic_import_job_schedule_func_from_str(ctx=MagicMock(), param=MagicMock(), import_str="no_colon")

    def test_nonexistent_module_raises(self):
        with pytest.raises(click.BadParameter):
            dynamic_import_job_schedule_func_from_str(
                ctx=MagicMock(), param=MagicMock(), import_str="nonexistent.module:func"
            )

    def test_valid_import(self):
        result = dynamic_import_job_schedule_func_from_str(
            ctx=MagicMock(), param=MagicMock(), import_str="os.path:exists"
        )
        assert callable(result)

    def test_non_callable_attribute_raises(self):
        with pytest.raises(click.BadParameter, match="not a callable"):
            dynamic_import_job_schedule_func_from_str(ctx=MagicMock(), param=MagicMock(), import_str="os.path:sep")


class TestWarnAboutIgnoreFiles:
    """Warnings for .amlignore and .gitignore state."""

    def test_empty_amlignore_warns(self, tmp_path):
        (tmp_path / ".amlignore").write_text("")
        with patch.object(Path, "cwd", return_value=tmp_path):
            # Should not raise; just emits a styled message
            warn_about_ignore_files()

    def test_filled_amlignore_no_warning(self, tmp_path):
        (tmp_path / ".amlignore").write_text("*.pyc\n__pycache__/")
        with patch.object(Path, "cwd", return_value=tmp_path):
            warn_about_ignore_files()

    def test_no_ignore_files(self, tmp_path):
        with patch.object(Path, "cwd", return_value=tmp_path):
            warn_about_ignore_files()

    def test_gitignore_present_without_amlignore(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.pyc")
        with patch.object(Path, "cwd", return_value=tmp_path):
            warn_about_ignore_files()


class TestVerifyConfigurationDirectory:
    """Configuration directory validation for Azure submissions."""

    def test_non_empty_dir_passes(self, tmp_path):
        conf_dir = tmp_path / "conf" / "base"
        conf_dir.mkdir(parents=True)
        (conf_dir / "catalog.yml").write_text("key: value")

        metadata = MagicMock()
        ctx = CliContext(env="base", metadata=metadata)
        click_ctx = MagicMock()

        with patch.object(Path, "cwd", return_value=tmp_path):
            verify_configuration_directory_for_azure(click_ctx, ctx)

        click_ctx.exit.assert_not_called()

    def test_empty_dir_prompts_and_aborts(self, tmp_path):
        conf_dir = tmp_path / "conf" / "staging"
        conf_dir.mkdir(parents=True)

        metadata = MagicMock()
        ctx = CliContext(env="staging", metadata=metadata)
        click_ctx = MagicMock()

        with (
            patch.object(Path, "cwd", return_value=tmp_path),
            patch("click.confirm", return_value=False),
        ):
            verify_configuration_directory_for_azure(click_ctx, ctx)
            click_ctx.exit.assert_called_once_with(2)

    def test_missing_dir_prompts(self, tmp_path):
        metadata = MagicMock()
        ctx = CliContext(env="nonexistent", metadata=metadata)
        click_ctx = MagicMock()

        with (
            patch.object(Path, "cwd", return_value=tmp_path),
            patch("click.confirm", return_value=True),
        ):
            verify_configuration_directory_for_azure(click_ctx, ctx)
            # confirm returned True, so no exit(2)
            click_ctx.exit.assert_not_called()


class TestDefaultJobCallback:
    """Default callback prints the studio URL."""

    def test_prints_studio_url(self, capsys):
        job = MagicMock()
        job.studio_url = "https://ml.azure.com/runs/123"
        default_job_callback(job)
        assert "https://ml.azure.com/runs/123" in capsys.readouterr().out


class TestReadMlflowExperimentName:
    """``_read_mlflow_experiment_name`` reads from mlflow.yml via the config loader."""

    def test_returns_name_when_configured(self):
        mgr = MagicMock()
        mgr.context.config_loader.__getitem__ = MagicMock(
            return_value={"tracking": {"experiment": {"name": "my-experiment"}}}
        )
        assert _read_mlflow_experiment_name(mgr) == "my-experiment"

    def test_returns_none_when_name_missing(self):
        mgr = MagicMock()
        mgr.context.config_loader.__getitem__ = MagicMock(return_value={"tracking": {}})
        assert _read_mlflow_experiment_name(mgr) is None

    def test_returns_none_on_key_error(self):
        mgr = MagicMock()
        mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))
        assert _read_mlflow_experiment_name(mgr) is None

    def test_returns_none_on_type_error(self):
        mgr = MagicMock()
        mgr.context.config_loader.__getitem__ = MagicMock(side_effect=TypeError)
        assert _read_mlflow_experiment_name(mgr) is None
