"""Tests for MlflowAzureMLHook and MLflow integration."""

import os
from unittest.mock import MagicMock, patch

import pytest

from kedro_azureml.config import KedroAzureMLConfig
from kedro_azureml.constants import (
    KEDRO_AZUREML_MLFLOW_ENABLED,
    KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME,
    KEDRO_AZUREML_MLFLOW_NODE_NAME,
    KEDRO_AZUREML_MLFLOW_RUN_NAME,
)
from kedro_azureml.mlflow_hook import MlflowAzureMLHook


MLFLOW_ENV_VARS = [
    KEDRO_AZUREML_MLFLOW_ENABLED,
    KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME,
    KEDRO_AZUREML_MLFLOW_NODE_NAME,
    KEDRO_AZUREML_MLFLOW_RUN_NAME,
    "MLFLOW_EXPERIMENT_NAME",
    "MLFLOW_RUN_ID",
    "KEDRO_ENV",
]


@pytest.fixture(autouse=True)
def clean_env():
    """Remove MLflow-related env vars before and after each test."""
    saved = {k: os.environ.pop(k, None) for k in MLFLOW_ENV_VARS}
    yield
    for k in MLFLOW_ENV_VARS:
        os.environ.pop(k, None)
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


@pytest.fixture
def hook():
    return MlflowAzureMLHook()


class TestAfterContextCreated:
    def test_noop_when_disabled(self, hook):
        """Hook does nothing when KEDRO_AZUREML_MLFLOW_ENABLED != '1'."""
        hook.after_context_created(context=MagicMock())
        assert "MLFLOW_EXPERIMENT_NAME" not in os.environ

    def test_sets_experiment_name_env_var(self, hook):
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"
        os.environ[KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME] = "my-experiment"

        hook.after_context_created(context=MagicMock())

        assert os.environ["MLFLOW_EXPERIMENT_NAME"] == "my-experiment"

    def test_skips_when_no_experiment_name(self, hook):
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"

        hook.after_context_created(context=MagicMock())

        assert "MLFLOW_EXPERIMENT_NAME" not in os.environ


class TestBeforePipelineRun:
    def test_noop_when_disabled(self, hook):
        hook.before_pipeline_run(
            run_params={"pipeline_name": "test"},
            pipeline=MagicMock(),
            catalog=MagicMock(),
        )

    @patch("kedro_azureml.mlflow_hook.mlflow", create=True)
    def test_noop_when_no_active_run(self, mock_mlflow, hook):
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"

        # Import and patch at module level
        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            mock_mlflow.active_run.return_value = None
            hook.before_pipeline_run(
                run_params={"pipeline_name": "test"},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )
            mock_mlflow.set_tags.assert_not_called()

    def test_starts_run_with_correct_experiment(self, hook):
        """When MLFLOW_RUN_ID is set by AzureML, the hook should start the
        run under the job experiment — not whatever mlflow.yml says."""
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"
        os.environ[KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME] = "job-experiment"
        os.environ["MLFLOW_RUN_ID"] = "aml-run-123"

        mock_mlflow = MagicMock()
        # First call (before we start): no active run.
        # Second call (after start_run): return the run.
        mock_active_run = MagicMock()
        mock_active_run.info.run_id = "aml-run-123"
        mock_mlflow.active_run.side_effect = [None, mock_active_run]

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            hook.before_pipeline_run(
                run_params={},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )

        mock_mlflow.set_experiment.assert_called_once_with("job-experiment")
        mock_mlflow.start_run.assert_called_once_with(run_id="aml-run-123")

    def test_skips_start_run_when_no_mlflow_run_id(self, hook):
        """Without MLFLOW_RUN_ID, the hook sets the experiment but does not
        start a run (lets kedro-mlflow handle it)."""
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"
        os.environ[KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME] = "job-experiment"

        mock_mlflow = MagicMock()
        mock_mlflow.active_run.return_value = None

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            hook.before_pipeline_run(
                run_params={},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )

        mock_mlflow.set_experiment.assert_called_once_with("job-experiment")
        mock_mlflow.start_run.assert_not_called()

    def test_skips_experiment_override_when_run_already_active(self, hook):
        """If a run is already active, the hook should not start another."""
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"
        os.environ[KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME] = "job-experiment"
        os.environ["MLFLOW_RUN_ID"] = "aml-run-123"

        mock_mlflow = MagicMock()
        mock_active_run = MagicMock()
        mock_active_run.info.run_id = "aml-run-123"
        mock_mlflow.active_run.return_value = mock_active_run

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            hook.before_pipeline_run(
                run_params={},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )

        mock_mlflow.set_experiment.assert_not_called()
        mock_mlflow.start_run.assert_not_called()

    def test_tags_active_run(self, hook):
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"
        os.environ[KEDRO_AZUREML_MLFLOW_NODE_NAME] = "train_model"
        os.environ[KEDRO_AZUREML_MLFLOW_RUN_NAME] = "my-pipeline"
        os.environ["KEDRO_ENV"] = "prod"

        mock_mlflow = MagicMock()
        mock_active_run = MagicMock()
        mock_active_run.info.run_id = "run-123"
        mock_mlflow.active_run.return_value = mock_active_run

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            hook.before_pipeline_run(
                run_params={"pipeline_name": "__default__"},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )

        mock_mlflow.set_tags.assert_called_once()
        tags = mock_mlflow.set_tags.call_args[0][0]
        assert tags["kedro.node_name"] == "train_model"
        assert tags["kedro.pipeline_run_name"] == "my-pipeline"
        assert tags["kedro.env"] == "prod"
        assert tags["kedro.pipeline_name"] == "__default__"

    def test_sets_child_run_name(self, hook):
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"
        os.environ[KEDRO_AZUREML_MLFLOW_NODE_NAME] = "train_model"
        os.environ[KEDRO_AZUREML_MLFLOW_RUN_NAME] = "my-pipeline"

        mock_mlflow = MagicMock()
        mock_active_run = MagicMock()
        mock_active_run.info.run_id = "run-123"
        mock_mlflow.active_run.return_value = mock_active_run

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            hook.before_pipeline_run(
                run_params={},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )

        mock_mlflow.MlflowClient().set_tag.assert_called_once_with(
            "run-123", "mlflow.runName", "my-pipeline :: train_model"
        )

    def test_child_run_name_without_run_name(self, hook):
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"
        os.environ[KEDRO_AZUREML_MLFLOW_NODE_NAME] = "train_model"

        mock_mlflow = MagicMock()
        mock_active_run = MagicMock()
        mock_active_run.info.run_id = "run-123"
        mock_mlflow.active_run.return_value = mock_active_run

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            hook.before_pipeline_run(
                run_params={},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )

        mock_mlflow.MlflowClient().set_tag.assert_called_once_with(
            "run-123", "mlflow.runName", "train_model"
        )

    def test_graceful_when_mlflow_not_installed(self, hook):
        """Hook should not crash when mlflow is not importable."""
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"

        with patch.dict("sys.modules", {"mlflow": None}):
            # Should not raise
            hook.before_pipeline_run(
                run_params={},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )


class TestOnPipelineError:
    def test_noop_when_disabled(self, hook):
        hook.on_pipeline_error(
            error=RuntimeError("boom"),
            run_params={},
            pipeline=MagicMock(),
            catalog=MagicMock(),
        )

    def test_tags_run_with_error(self, hook):
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"
        os.environ[KEDRO_AZUREML_MLFLOW_NODE_NAME] = "train_model"

        mock_mlflow = MagicMock()
        mock_mlflow.active_run.return_value = MagicMock()

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            hook.on_pipeline_error(
                error=RuntimeError("something broke"),
                run_params={},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )

        mock_mlflow.set_tag.assert_any_call("kedro.error", "something broke")
        mock_mlflow.set_tag.assert_any_call("kedro.failed_node", "train_model")

    def test_noop_when_no_active_run(self, hook):
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"

        mock_mlflow = MagicMock()
        mock_mlflow.active_run.return_value = None

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            hook.on_pipeline_error(
                error=RuntimeError("boom"),
                run_params={},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )

        mock_mlflow.set_tag.assert_not_called()

    def test_truncates_long_error_message(self, hook):
        os.environ[KEDRO_AZUREML_MLFLOW_ENABLED] = "1"

        mock_mlflow = MagicMock()
        mock_mlflow.active_run.return_value = MagicMock()
        long_error = "x" * 500

        with patch.dict("sys.modules", {"mlflow": mock_mlflow}):
            hook.on_pipeline_error(
                error=RuntimeError(long_error),
                run_params={},
                pipeline=MagicMock(),
                catalog=MagicMock(),
            )

        error_tag_call = [
            c for c in mock_mlflow.set_tag.call_args_list if c[0][0] == "kedro.error"
        ][0]
        assert len(error_tag_call[0][1]) == 250
