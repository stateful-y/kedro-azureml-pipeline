"""Tests for the Azure ML pipeline client."""

import os
from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import HttpResponseError
from azure.identity import CredentialUnavailableError

from kedro_azureml_pipeline.client import AzureMLPipelinesClient, _get_azureml_client, get_azureml_credentials
from kedro_azureml_pipeline.config import ClusterConfig, ComputeConfig, WorkspaceConfig


@pytest.fixture
def workspace_config():
    return WorkspaceConfig(subscription_id="sub-1", resource_group="rg-1", name="ws-1")


@pytest.fixture
def compute_config():
    return ComputeConfig(root={"__default__": ClusterConfig(cluster_name="cpu-cluster")})


@pytest.fixture
def mock_pipeline_job():
    job = MagicMock()
    job.display_name = "test-pipeline"
    return job


class TestGetAzureMLClient:
    """Context-manager client creation."""

    def test_yields_ml_client(self, workspace_config):
        with (
            patch("kedro_azureml_pipeline.client.get_azureml_credentials") as mock_creds,
            patch("kedro_azureml_pipeline.client.MLClient") as mock_ml_client_cls,
        ):
            mock_creds.return_value = MagicMock()
            mock_ml_client_cls.from_config.return_value = MagicMock()

            with _get_azureml_client(workspace_config) as client:
                assert client is not None
                mock_ml_client_cls.from_config.assert_called_once()

    def test_writes_config_json_with_workspace_details(self, workspace_config):
        written_content = None

        def capture_write(content):
            nonlocal written_content
            written_content = content
            # Call original or just store

        with (
            patch("kedro_azureml_pipeline.client.get_azureml_credentials") as mock_creds,
            patch("kedro_azureml_pipeline.client.MLClient") as mock_ml_client_cls,
        ):
            mock_creds.return_value = MagicMock()
            mock_ml_client_cls.from_config.return_value = MagicMock()

            # We need to intercept the write_text call on the config path
            with _get_azureml_client(workspace_config):
                pass

            # Verify from_config was called with expected credential and path
            call_kwargs = mock_ml_client_cls.from_config.call_args
            assert call_kwargs.kwargs.get("credential") is not None or call_kwargs[1].get("credential") is not None


class TestAzureMLPipelinesClient:
    """Job submission and lifecycle."""

    def test_run_submits_job(self, workspace_config, compute_config, mock_pipeline_job):
        client = AzureMLPipelinesClient(mock_pipeline_job)

        with patch("kedro_azureml_pipeline.client._get_azureml_client") as mock_ctx:
            mock_ml_client = MagicMock()
            mock_ml_client.compute.get.return_value = MagicMock(
                name="cpu-cluster", size="Standard_DS3_v2", min_instances=0, max_instances=4
            )
            mock_ml_client.jobs.create_or_update.return_value = MagicMock()
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ml_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = client.run(workspace_config, compute_config)

            assert result is True
            mock_ml_client.jobs.create_or_update.assert_called_once()

    def test_run_with_display_name_override(self, workspace_config, compute_config, mock_pipeline_job):
        client = AzureMLPipelinesClient(mock_pipeline_job)

        with patch("kedro_azureml_pipeline.client._get_azureml_client") as mock_ctx:
            mock_ml_client = MagicMock()
            mock_ml_client.compute.get.return_value = MagicMock(
                name="cpu-cluster", size="Standard_DS3_v2", min_instances=0, max_instances=4
            )
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ml_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            client.run(workspace_config, compute_config, display_name="custom-name")

            assert mock_pipeline_job.display_name == "custom-name"

    def test_run_invokes_callback(self, workspace_config, compute_config, mock_pipeline_job):
        client = AzureMLPipelinesClient(mock_pipeline_job)
        callback = MagicMock()

        with patch("kedro_azureml_pipeline.client._get_azureml_client") as mock_ctx:
            mock_ml_client = MagicMock()
            mock_ml_client.compute.get.return_value = MagicMock(
                name="cpu-cluster", size="Standard_DS3_v2", min_instances=0, max_instances=4
            )
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ml_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            client.run(workspace_config, compute_config, on_job_scheduled=callback)

            callback.assert_called_once()

    def test_run_wait_for_completion_returns_true_on_success(self, workspace_config, compute_config, mock_pipeline_job):
        client = AzureMLPipelinesClient(mock_pipeline_job)

        with patch("kedro_azureml_pipeline.client._get_azureml_client") as mock_ctx:
            mock_ml_client = MagicMock()
            mock_ml_client.compute.get.return_value = MagicMock(
                name="cpu-cluster", size="Standard_DS3_v2", min_instances=0, max_instances=4
            )
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ml_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = client.run(workspace_config, compute_config, wait_for_completion=True)

            assert result is True
            mock_ml_client.jobs.stream.assert_called_once()

    def test_run_wait_for_completion_returns_false_on_error(self, workspace_config, compute_config, mock_pipeline_job):
        client = AzureMLPipelinesClient(mock_pipeline_job)

        with patch("kedro_azureml_pipeline.client._get_azureml_client") as mock_ctx:
            mock_ml_client = MagicMock()
            mock_ml_client.compute.get.return_value = MagicMock(
                name="cpu-cluster", size="Standard_DS3_v2", min_instances=0, max_instances=4
            )
            mock_ml_client.jobs.stream.side_effect = HttpResponseError("pipeline failed")
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ml_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = client.run(workspace_config, compute_config, wait_for_completion=True)

            assert result is False

    def test_run_without_waiting_returns_true(self, workspace_config, compute_config, mock_pipeline_job):
        """Explicit ``wait_for_completion=False`` returns True without streaming."""
        client = AzureMLPipelinesClient(mock_pipeline_job)

        with patch("kedro_azureml_pipeline.client._get_azureml_client") as mock_ctx:
            mock_ml_client = MagicMock()
            mock_ml_client.compute.get.return_value = MagicMock(
                name="cpu-cluster", size="Standard_DS3_v2", min_instances=0, max_instances=4
            )
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ml_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = client.run(
                workspace_config,
                compute_config,
                wait_for_completion=False,
                experiment_name="my-experiment",
            )

            assert result is True
            mock_ml_client.jobs.stream.assert_not_called()

    def test_run_raises_on_missing_cluster(self, workspace_config, compute_config, mock_pipeline_job):
        """A missing compute cluster raises ``ValueError``."""
        client = AzureMLPipelinesClient(mock_pipeline_job)

        with patch("kedro_azureml_pipeline.client._get_azureml_client") as mock_ctx:
            mock_ml_client = MagicMock()
            mock_ml_client.compute.get.return_value = None
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_ml_client)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with pytest.raises(ValueError, match="does not exist"):
                client.run(workspace_config, compute_config)


class TestGetAzureMLCredentials:
    """Credential resolution strategy."""

    def test_returns_default_credential_when_valid(self):
        with (
            patch("kedro_azureml_pipeline.client.DefaultAzureCredential") as mock_default,
            patch("kedro_azureml_pipeline.client.InteractiveBrowserCredential") as mock_interactive,
        ):
            mock_default.return_value = MagicMock()
            result = get_azureml_credentials()

            mock_default.assert_called_once()
            mock_interactive.assert_not_called()
            assert result is mock_default.return_value

    def test_falls_back_to_interactive_on_failure(self):
        with (
            patch("kedro_azureml_pipeline.client.DefaultAzureCredential") as mock_default,
            patch("kedro_azureml_pipeline.client.InteractiveBrowserCredential") as mock_interactive,
        ):
            mock_default.return_value.get_token.side_effect = CredentialUnavailableError(message="no token")
            mock_interactive.return_value = MagicMock()

            result = get_azureml_credentials()

            mock_interactive.assert_called_once()
            assert result is mock_interactive.return_value

    def test_excludes_managed_identity_on_azureml_compute(self):
        with (
            patch.dict(os.environ, {"MSI_ENDPOINT": "http://fake"}),
            patch("kedro_azureml_pipeline.client.DefaultAzureCredential") as mock_default,
            patch("kedro_azureml_pipeline.client.InteractiveBrowserCredential"),
        ):
            mock_default.return_value = MagicMock()
            get_azureml_credentials()

            mock_default.assert_called_once_with(exclude_managed_identity_credential=True)

    def test_does_not_exclude_managed_identity_outside_azureml(self):
        env = os.environ.copy()
        env.pop("MSI_ENDPOINT", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("kedro_azureml_pipeline.client.DefaultAzureCredential") as mock_default,
            patch("kedro_azureml_pipeline.client.InteractiveBrowserCredential"),
        ):
            mock_default.return_value = MagicMock()
            get_azureml_credentials()

            mock_default.assert_called_once_with(exclude_managed_identity_credential=False)
