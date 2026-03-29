from unittest.mock import MagicMock, Mock

import pytest
from kedro.io.core import Version
from kedro.runner import SequentialRunner

from kedro_azureml_pipeline.datasets.asset_dataset import AzureMLAssetDataset
from kedro_azureml_pipeline.hooks import AzureMLLocalRunHook, azureml_local_run_hook
from kedro_azureml_pipeline.runner import AzurePipelinesRunner


class TestAzureMLLocalRunHook:
    """Tests for ``AzureMLLocalRunHook`` lifecycle."""

    @pytest.mark.parametrize(
        "config_patterns",
        [
            {"azureml": ["azureml*", "azureml*/**", "**/azureml*"]},
            {},
        ],
    )
    @pytest.mark.parametrize(
        "runner",
        [AzurePipelinesRunner.__name__, SequentialRunner.__name__],
    )
    def test_full_lifecycle_configures_datasets(
        self, mock_azureml_config, dummy_pipeline, multi_catalog, runner, config_patterns
    ):
        """Hook registers config pattern, injects workspace, and toggles dataset mode."""
        hook = AzureMLLocalRunHook()
        context_mock = Mock(
            config_loader=MagicMock(
                __getitem__=Mock(return_value={"workspace": {"__default__": mock_azureml_config.to_dict()}})
            )
        )
        context_mock.config_loader.config_patterns.keys.return_value = config_patterns.keys()

        # after_context_created
        hook.after_context_created(context_mock)
        assert hook.azure_config.subscription_id == "123"
        assert hook.azure_config.name == "best"

        # after_catalog_created
        hook.after_catalog_created(multi_catalog)
        for dataset_name in multi_catalog.filter():
            dataset = multi_catalog[dataset_name]
            if isinstance(dataset, AzureMLAssetDataset):
                assert dataset._download is True
                assert dataset._local_run is True
                assert dataset._azureml_config is not None

        # before_pipeline_run
        run_params = {"runner": runner}
        hook.before_pipeline_run(run_params, dummy_pipeline, multi_catalog)

        if runner == SequentialRunner.__name__:
            assert multi_catalog["input_data"]._download is True
            assert multi_catalog["input_data"]._local_run is True
            assert multi_catalog["input_data"]._azureml_config == hook.azure_config
            assert multi_catalog["i2"]._download is False
            assert multi_catalog["i2"]._local_run is True
            assert multi_catalog["i2"]._version == Version("local", "local")
        else:
            assert multi_catalog["input_data"]._download is False
            assert multi_catalog["input_data"]._local_run is False
            assert multi_catalog["input_data"]._azureml_config is not None
            assert multi_catalog["i2"]._download is False
            assert multi_catalog["i2"]._local_run is False
            assert multi_catalog["i2"]._version is None

    def test_registers_config_pattern_when_missing(self, mock_azureml_config):
        """If ``azureml`` pattern is absent the hook adds it."""
        hook = AzureMLLocalRunHook()
        config_patterns = {}
        context_mock = Mock(
            config_loader=MagicMock(
                __getitem__=Mock(return_value={"workspace": {"__default__": mock_azureml_config.to_dict()}}),
                config_patterns=config_patterns,
            )
        )
        hook.after_context_created(context_mock)
        assert "azureml" in config_patterns

    def test_skips_non_asset_datasets_in_catalog(self, mock_azureml_config):
        """Non-AzureMLAssetDataset entries in the catalog are left untouched."""
        from kedro.io import DataCatalog, MemoryDataset

        hook = AzureMLLocalRunHook()
        catalog = DataCatalog(datasets={"mem": MemoryDataset(data=42)})
        hook.azure_config = mock_azureml_config
        hook.after_catalog_created(catalog)
        assert catalog["mem"].load() == 42

    def test_module_level_singleton_exists(self):
        """The module exports a ready-to-use hook instance."""
        assert isinstance(azureml_local_run_hook, AzureMLLocalRunHook)
