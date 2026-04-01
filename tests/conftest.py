import importlib.metadata as _ilmd
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import kedro.framework.session.session as _kedro_session_mod
import pandas as pd
import pytest
from kedro.framework import project as _kedro_project
from kedro.io import DataCatalog
from kedro.io.core import Version
from kedro.pipeline import Pipeline, node, pipeline
from kedro_datasets.pandas import CSVDataset, ParquetDataset

from kedro_azureml_pipeline.config import (
    _CONFIG_TEMPLATE,
    KedroAzureMLConfig,
)
from kedro_azureml_pipeline.datasets import AzureMLAssetDataset
from kedro_azureml_pipeline.utils import CliContext
from tests.scenarios.project_factory import KedroProjectOptions, build_kedro_project_scenario
from tests.utils import identity


@pytest.fixture(autouse=True)
def _disable_kedro_plugin_entrypoints(monkeypatch):
    """Prevent system-installed Kedro plugin hooks from loading during tests.

    Reads the project's ``ALLOWED_HOOK_PLUGINS`` setting to determine which
    plugin distributions (by name) are permitted. All others are filtered out.
    """
    _PLUGIN_HOOKS = "kedro.hooks"

    def _wrapped_register(*args, **kwargs):
        hook_manager = args[0] if args else kwargs.get("hook_manager")

        # Try reading from the Kedro project settings first; fall back to
        # the test-local settings module when the project is not fully
        # configured yet (e.g. when only PACKAGE_NAME is patched).
        proj_allowed = getattr(_kedro_project.settings, "ALLOWED_HOOK_PLUGINS", None)
        if proj_allowed is None:
            try:
                from tests.settings import ALLOWED_HOOK_PLUGINS

                proj_allowed = ALLOWED_HOOK_PLUGINS
            except (ImportError, AttributeError):
                proj_allowed = ()

        allowed_set = {str(p).strip() for p in proj_allowed if str(p).strip()}

        if not allowed_set:
            return hook_manager

        def _filtered_loader(group: str):
            try:
                all_entry_points = _ilmd.entry_points()
                if hasattr(all_entry_points, "select"):
                    entry_points = list(all_entry_points.select(group=group))
                else:
                    entry_points = list(all_entry_points.get(group, []))
            except Exception:
                entry_points = []

            for entry_point in entry_points:
                try:
                    dist_name = getattr(getattr(entry_point, "dist", None), "name", None)
                    if dist_name and dist_name in allowed_set:
                        plugin = entry_point.load()
                        hook_manager.register(plugin, name=getattr(entry_point, "name", None))
                except Exception:
                    continue

            return hook_manager

        hook_manager.load_setuptools_entrypoints = _filtered_loader
        _filtered_loader(_PLUGIN_HOOKS)

    monkeypatch.setattr(
        _kedro_session_mod,
        "_register_hooks_entry_points",
        _wrapped_register,
        raising=False,
    )


@pytest.fixture(scope="session")
def temp_directory(tmpdir_factory):
    """Session-scoped temporary directory for all test projects."""
    return tmpdir_factory.mktemp("session_temp_dir")


@pytest.fixture(scope="session")
def project_scenario_factory(temp_directory):
    """Return a callable that builds Kedro project variants in tmp dirs."""

    def _factory(kedro_project_options: KedroProjectOptions, project_name: str | None = None) -> KedroProjectOptions:
        return build_kedro_project_scenario(
            temp_directory=temp_directory, options=kedro_project_options, project_name=project_name
        )

    return _factory


@pytest.fixture()
def dummy_pipeline() -> Pipeline:
    """Three-node linear pipeline for basic tests."""
    return pipeline([
        node(identity, inputs="input_data", outputs="i2", name="node1"),
        node(identity, inputs="i2", outputs="i3", name="node2"),
        node(identity, inputs="i3", outputs="output_data", name="node3"),
    ])


@pytest.fixture()
def dummy_pipeline_compute_tag() -> Pipeline:
    """Three-node pipeline where node1 has a ``compute-2`` tag."""
    return pipeline([
        node(
            identity,
            inputs="input_data",
            outputs="i2",
            name="node1",
            tags=["compute-2"],
        ),
        node(identity, inputs="i2", outputs="i3", name="node2"),
        node(identity, inputs="i3", outputs="output_data", name="node3"),
    ])


@pytest.fixture()
def dummy_pipeline_deterministic_tag() -> Pipeline:
    """Three-node pipeline where node1 has a ``deterministic`` tag."""
    return pipeline([
        node(
            identity,
            inputs="input_data",
            outputs="i2",
            name="node1",
            tags=["deterministic"],
        ),
        node(identity, inputs="i2", outputs="i3", name="node2"),
        node(identity, inputs="i3", outputs="output_data", name="node3"),
    ])


@pytest.fixture()
def dummy_plugin_config() -> KedroAzureMLConfig:
    """Deep copy of the default plugin config template."""
    return _CONFIG_TEMPLATE.model_copy(deep=True)


@pytest.fixture()
def patched_kedro_package():
    """Patch ``PACKAGE_NAME`` to ``'tests'`` for the Kedro project discovery."""
    with patch("kedro.framework.project.PACKAGE_NAME", "tests") as patched_package:
        yield patched_package


@pytest.fixture()
def cli_context() -> CliContext:
    """Minimal CLI context with ``env='base'``."""
    metadata = MagicMock()
    metadata.package_name = "tests"
    return CliContext("base", metadata)


class ExtendedMagicMock(MagicMock):
    def to_dict(self):
        return {
            "subscription_id": self.subscription_id,
            "resource_group": self.resource_group,
            "name": self.name,
        }


@pytest.fixture
def mock_azureml_config():
    """Mock Azure ML workspace config with test subscription/resource values."""
    mock_config = ExtendedMagicMock()
    mock_config.subscription_id = "123"
    mock_config.resource_group = "456"
    mock_config.name = "best"
    return mock_config


@pytest.fixture
def simulated_azureml_dataset(tmp_path):
    """Temporary directory tree mimicking Azure ML data asset layouts."""
    df = pd.DataFrame({"data": [1, 2, 3], "partition_idx": [1, 2, 3]})

    test_data_file = tmp_path / "test_file"
    test_data_file.mkdir(parents=True)
    df.to_pickle(test_data_file / "test.pickle")

    test_data_nested = test_data_file / "random" / "subfolder"
    test_data_nested.mkdir(parents=True)

    df.to_pickle(test_data_nested / "test.pickle")

    test_data_folder_nested_file = tmp_path / "test_folder_nested_file" / "random" / "subfolder"
    test_data_folder_nested_file.mkdir(parents=True)
    df.to_pickle(test_data_folder_nested_file / "test.pickle")

    test_data_folder_root_file = tmp_path / "test_folder_file"
    test_data_folder_root_file.mkdir(parents=True)
    df.to_pickle(test_data_folder_root_file / "test.pickle")

    test_data_folder_root = tmp_path / "test_folder"

    test_data_folder_nested = tmp_path / "test_folder_nested" / "random" / "subfolder"
    test_data_folder_nested.mkdir(parents=True)
    test_data_folder_root.mkdir(parents=True)

    for _, sub_df in df.groupby("partition_idx"):
        filename = test_data_folder_nested / f"partition_{_}.parquet"
        filename2 = test_data_folder_root / f"partition_{_}.parquet"
        sub_df.to_parquet(filename)
        sub_df.to_parquet(filename2)

    return tmp_path


def mock_download_artifact_from_aml_uri_with_dataset(uri, destination, datastore_operation, simulated_dataset_path):
    """Mock function to simulate downloading Azure ML artifacts locally"""
    import shutil

    # Create destination directory if it doesn't exist
    dest_path = Path(destination)
    dest_path.mkdir(parents=True, exist_ok=True)

    # Map Azure ML URIs to local test directories within the simulated dataset
    prefix = "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces/dummy_ws/datastores/some_datastore/paths"
    uri_to_source_map = {
        f"{prefix}/test_file/": "test_file",
        f"{prefix}/test_folder_file/": "test_folder_file",
        f"{prefix}/test_folder_nested_file/": "test_folder_nested_file",
        f"{prefix}/test_folder/": "test_folder",
        f"{prefix}/test_folder_nested/": "test_folder_nested",
    }

    # Find the source directory based on URI
    source_folder = None
    for test_uri, folder_name in uri_to_source_map.items():
        if test_uri in uri:  # Use 'in' instead of 'startswith' to handle both folder and file URIs
            source_folder = simulated_dataset_path / folder_name
            break

    # Copy all files from source folder to destination
    if source_folder and source_folder.exists():
        # Special handling for test_folder_nested_file - copy only from the nested subfolder
        if "test_folder_nested_file" in str(source_folder) and (source_folder / "random" / "subfolder").exists():
            nested_source = source_folder / "random" / "subfolder"
            for item in nested_source.rglob("*"):
                if item.is_file():
                    # Copy directly to destination without preserving nested structure
                    dest_file = dest_path / item.name
                    shutil.copy2(item, dest_file)
        else:
            # Normal copy preserving relative structure
            for item in source_folder.rglob("*"):
                if item.is_file():
                    relative_path = item.relative_to(source_folder)
                    dest_file = dest_path / relative_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest_file)


@pytest.fixture
def mock_azureml_fs(simulated_azureml_dataset):
    """Patch ``download_artifact_from_aml_uri`` to copy from test fixtures."""

    def mock_with_dataset(uri, destination, datastore_operation):
        return mock_download_artifact_from_aml_uri_with_dataset(
            uri, destination, datastore_operation, simulated_azureml_dataset
        )

    with patch(
        "kedro_azureml_pipeline.datasets.asset_dataset.artifact_utils.download_artifact_from_aml_uri",
        side_effect=mock_with_dataset,
    ):
        yield


@pytest.fixture
def mock_azureml_client(request):
    """Parametrized mock for ``_get_azureml_client`` returning a data asset."""
    mock_data_asset = MagicMock()
    mock_data_asset.version = "1"
    mock_data_asset.path = request.param["path"]
    mock_data_asset.type = request.param["type"]

    with patch("kedro_azureml_pipeline.datasets.asset_dataset._get_azureml_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.data.get.return_value = mock_data_asset

        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_client
        mock_context_manager.__exit__.return_value = None

        mock_get_client.return_value = mock_context_manager

        yield mock_get_client


@pytest.fixture
def in_temp_dir(tmp_path):
    """Change working directory to a temporary path for the test duration."""
    original_cwd = os.getcwd()

    os.chdir(tmp_path)

    yield

    os.chdir(original_cwd)


@pytest.fixture
def multi_catalog():
    """Catalog with CSV and Parquet ``AzureMLAssetDataset`` entries."""
    csv = AzureMLAssetDataset(
        dataset={
            "type": CSVDataset,
            "filepath": "abc.csv",
        },
        azureml_dataset="test_dataset",
        version=Version(None, None),
    )
    parq = AzureMLAssetDataset(
        dataset={
            "type": ParquetDataset,
            "filepath": "xyz.parq",
        },
        azureml_dataset="test_dataset_2",
        version=Version(None, None),
    )
    return DataCatalog({"input_data": csv, "i2": parq})


@pytest.fixture
def factory_catalog():
    """Catalog with a dataset factory pattern and an explicit AzureMLAssetDataset.

    ``input_data`` resolves via the ``{name}`` factory pattern to a MemoryDataset
    so it is NOT in ``catalog.filter()``.  ``i2`` is an explicit AzureMLAssetDataset.
    """
    from kedro.io.catalog_config_resolver import CatalogConfigResolver

    parq = AzureMLAssetDataset(
        dataset={
            "type": ParquetDataset,
            "filepath": "xyz.parq",
        },
        azureml_dataset="test_dataset_2",
        version=Version(None, None),
    )
    resolver = CatalogConfigResolver(config={"{name}": {"type": "kedro.io.MemoryDataset"}})
    catalog = DataCatalog(datasets={"i2": parq}, config_resolver=resolver)
    return catalog
