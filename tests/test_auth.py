"""Tests for Azure credential helpers."""

import os
from unittest.mock import MagicMock, patch

from kedro_azureml_pipeline.auth.utils import get_azureml_credentials


class TestGetAzureMLCredentials:
    """Credential resolution strategy."""

    def test_returns_default_credential_when_valid(self):
        with (
            patch("kedro_azureml_pipeline.auth.utils.DefaultAzureCredential") as mock_default,
            patch("kedro_azureml_pipeline.auth.utils.InteractiveBrowserCredential") as mock_interactive,
        ):
            mock_default.return_value = MagicMock()
            result = get_azureml_credentials()

            mock_default.assert_called_once()
            mock_interactive.assert_not_called()
            assert result is mock_default.return_value

    def test_falls_back_to_interactive_on_failure(self):
        with (
            patch("kedro_azureml_pipeline.auth.utils.DefaultAzureCredential") as mock_default,
            patch("kedro_azureml_pipeline.auth.utils.InteractiveBrowserCredential") as mock_interactive,
        ):
            mock_default.return_value.get_token.side_effect = ValueError("no token")
            mock_interactive.return_value = MagicMock()

            result = get_azureml_credentials()

            mock_interactive.assert_called_once()
            assert result is mock_interactive.return_value

    def test_excludes_managed_identity_on_azureml_compute(self):
        with (
            patch.dict(os.environ, {"MSI_ENDPOINT": "http://fake"}),
            patch("kedro_azureml_pipeline.auth.utils.DefaultAzureCredential") as mock_default,
            patch("kedro_azureml_pipeline.auth.utils.InteractiveBrowserCredential"),
        ):
            mock_default.return_value = MagicMock()
            get_azureml_credentials()

            mock_default.assert_called_once_with(exclude_managed_identity_credential=True)

    def test_does_not_exclude_managed_identity_outside_azureml(self):
        env = os.environ.copy()
        env.pop("MSI_ENDPOINT", None)
        with (
            patch.dict(os.environ, env, clear=True),
            patch("kedro_azureml_pipeline.auth.utils.DefaultAzureCredential") as mock_default,
            patch("kedro_azureml_pipeline.auth.utils.InteractiveBrowserCredential"),
        ):
            mock_default.return_value = MagicMock()
            get_azureml_credentials()

            mock_default.assert_called_once_with(exclude_managed_identity_credential=False)
