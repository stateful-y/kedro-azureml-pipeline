from unittest.mock import MagicMock, Mock, patch

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

    def test_preserves_existing_azureml_pattern(self, mock_azureml_config):
        """If ``azureml`` pattern already exists the hook does not overwrite it."""
        hook = AzureMLLocalRunHook()
        existing_patterns = {"azureml": ["custom*"]}
        context_mock = Mock(
            config_loader=MagicMock(
                __getitem__=Mock(return_value={"workspace": {"__default__": mock_azureml_config.to_dict()}}),
                config_patterns=existing_patterns,
            )
        )
        hook.after_context_created(context_mock)
        assert existing_patterns["azureml"] == ["custom*"]

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


class TestPatchAzuremlArtifactBuilder:
    """Tests for ``AzureMLLocalRunHook._patch_azureml_artifact_builder``."""

    def test_wraps_builder_that_lacks_var_keyword(self):
        """The wrapper forwards ``artifact_uri`` and drops extra kwargs."""
        mock_registry = MagicMock()
        sentinel = object()

        def fake_builder(artifact_uri=None):
            return sentinel

        with (
            patch.dict(
                "sys.modules",
                {
                    "mlflow": MagicMock(),
                    "mlflow.store": MagicMock(),
                    "mlflow.store.artifact": MagicMock(),
                    "mlflow.store.artifact.artifact_repository_registry": MagicMock(
                        _artifact_repository_registry=mock_registry,
                    ),
                    "azureml": MagicMock(),
                    "azureml.mlflow": MagicMock(),
                    "azureml.mlflow.entry_point_loaders": MagicMock(
                        azureml_artifacts_builder=fake_builder,
                    ),
                },
            ),
        ):
            AzureMLLocalRunHook._patch_azureml_artifact_builder()

        mock_registry.register.assert_called_once()
        scheme, wrapper = mock_registry.register.call_args[0]
        assert scheme == "azureml"

        result = wrapper(artifact_uri="azureml://foo", tracking_uri="http://t", registry_uri="http://r")
        assert result is sentinel

    def test_noop_when_builder_already_accepts_kwargs(self):
        """Patch is skipped when the builder already accepts ``**kwargs``."""
        mock_registry = MagicMock()

        def compatible_builder(artifact_uri=None, **kwargs):
            pass

        with (
            patch.dict(
                "sys.modules",
                {
                    "mlflow": MagicMock(),
                    "mlflow.store": MagicMock(),
                    "mlflow.store.artifact": MagicMock(),
                    "mlflow.store.artifact.artifact_repository_registry": MagicMock(
                        _artifact_repository_registry=mock_registry,
                    ),
                    "azureml": MagicMock(),
                    "azureml.mlflow": MagicMock(),
                    "azureml.mlflow.entry_point_loaders": MagicMock(
                        azureml_artifacts_builder=compatible_builder,
                    ),
                },
            ),
        ):
            AzureMLLocalRunHook._patch_azureml_artifact_builder()

        mock_registry.register.assert_not_called()

    def test_noop_when_mlflow_not_installed(self):
        """Patch is a silent no-op when mlflow is not importable."""
        with patch.dict("sys.modules", {"mlflow": None}):
            AzureMLLocalRunHook._patch_azureml_artifact_builder()

    def test_noop_when_azureml_mlflow_not_installed(self):
        """Patch is a silent no-op when azureml-mlflow is not importable."""
        with patch.dict("sys.modules", {"azureml": None, "azureml.mlflow": None}):
            AzureMLLocalRunHook._patch_azureml_artifact_builder()

    def test_called_during_after_context_created(self, mock_azureml_config):
        """``after_context_created`` invokes the patch."""
        hook = AzureMLLocalRunHook()
        context_mock = Mock(
            config_loader=MagicMock(
                __getitem__=Mock(return_value={"workspace": {"__default__": mock_azureml_config.to_dict()}}),
                config_patterns={},
            )
        )
        with patch.object(AzureMLLocalRunHook, "_patch_azureml_artifact_builder") as mock_patch:
            hook.after_context_created(context_mock)
            mock_patch.assert_called_once()
