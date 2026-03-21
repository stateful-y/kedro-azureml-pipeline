from pathlib import Path

import pandas as pd
import pytest
from kedro.io.core import VERSIONED_FLAG_KEY, DatasetError, Version
from kedro_datasets.pandas import ParquetDataset
from kedro_datasets.pickle import PickleDataset

from kedro_azureml.datasets import (
    AzureMLAssetDataset,
    AzureMLPipelineDataset,
)


@pytest.mark.parametrize(
    "dataset_type,path_in_aml,path_locally,download_path,local_run,download,mock_azureml_client",
    [
        (
            PickleDataset,
            "test.pickle",
            "data/test.pickle",
            "data",
            False,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_file/test.pickle"
                ),
                "type": "uri_file",
            },
        ),
        (
            PickleDataset,
            "test.pickle",
            "data/test_dataset/1/test.pickle",
            "data/test_dataset/1",
            True,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_file/test.pickle"
                ),
                "type": "uri_file",
            },
        ),
        (
            PickleDataset,
            "test.pickle",
            "data/test_dataset/1/test.pickle",
            "data/test_dataset/1",
            True,
            True,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_file/test.pickle"
                ),
                "type": "uri_file",
            },
        ),
        (
            PickleDataset,
            "random/subfolder/test.pickle",
            "data/random/subfolder/test.pickle",
            "data/random/subfolder",
            False,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/random/subfolder/test.pickle"
                ),
                "type": "uri_file",
            },
        ),
        (
            PickleDataset,
            "random/subfolder/test.pickle",
            "data/test_dataset/1/random/subfolder/test.pickle",
            "data/test_dataset/1/random/subfolder",
            True,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/random/subfolder/test.pickle"
                ),
                "type": "uri_file",
            },
        ),
        (
            PickleDataset,
            "random/subfolder/test.pickle",
            "data/test_dataset/1/random/subfolder/test.pickle",
            "data/test_dataset/1/random/subfolder",
            True,
            True,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_file/random/subfolder/test.pickle"
                ),
                "type": "uri_file",
            },
        ),
        (
            ParquetDataset,
            ".",
            "data/",
            "data",
            False,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder/"
                ),
                "type": "uri_file",
            },
        ),
        (
            ParquetDataset,
            ".",
            "data/test_dataset/1/",
            "data/test_dataset/1",
            True,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            ParquetDataset,
            ".",
            "data/test_dataset/1/",
            "data/test_dataset/1",
            True,
            True,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            ParquetDataset,
            "random/subfolder/",
            "data/random/subfolder/",
            "data/random/subfolder",
            False,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder_nested/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            ParquetDataset,
            "random/subfolder/",
            "data/test_dataset/1/random/subfolder/",
            "data/test_dataset/1/random/subfolder",
            True,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder_nested/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            ParquetDataset,
            "random/subfolder/",
            "data/test_dataset/1/random/subfolder/",
            "data/test_dataset/1/random/subfolder",
            True,
            True,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder_nested/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            PickleDataset,
            "test.pickle",
            "data/test.pickle",
            "data",
            False,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder_file/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            PickleDataset,
            "test.pickle",
            "data/test_dataset/1/test.pickle",
            "data/test_dataset/1",
            True,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder_file/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            PickleDataset,
            "test.pickle",
            "data/test_dataset/1/test.pickle",
            "data/test_dataset/1",
            True,
            True,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder_file/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            PickleDataset,
            "random/subfolder/test.pickle",
            "data/random/subfolder/test.pickle",
            "data/random/subfolder",
            False,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder_nested_file/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            PickleDataset,
            "random/subfolder/test.pickle",
            "data/test_dataset/1/random/subfolder/test.pickle",
            "data/test_dataset/1/random/subfolder",
            True,
            False,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder_nested_file/"
                ),
                "type": "uri_folder",
            },
        ),
        (
            PickleDataset,
            "random/subfolder/test.pickle",
            "data/test_dataset/1/random/subfolder/test.pickle",
            "data/test_dataset/1/random/subfolder",
            True,
            True,
            {
                "path": (
                    "azureml://subscriptions/1234/resourcegroups/dummy_rg/workspaces"
                    "/dummy_ws/datastores/some_datastore/paths/test_folder_nested_file/"
                ),
                "type": "uri_folder",
            },
        ),
    ],
    indirect=["mock_azureml_client"],
)
@pytest.mark.usefixtures("in_temp_dir", "mock_azureml_fs")
def test_azureml_asset_dataset(
    mock_azureml_client,
    mock_azureml_config,
    dataset_type,
    path_in_aml,
    path_locally,
    download_path,
    local_run,
    download,
):
    ds = AzureMLAssetDataset(
        dataset={
            "type": dataset_type,
            "filepath": path_in_aml,
        },
        azureml_dataset="test_dataset",
        version=Version(None, None),
    )
    ds._local_run = local_run
    ds._download = download
    ds._azureml_config = Path(mock_azureml_config)
    assert ds.path == Path(path_locally)
    assert ds.download_path == download_path
    df = pd.DataFrame({"data": [1, 2, 3], "partition_idx": [1, 2, 3]})
    if download:
        assert (ds._load()["data"] == df["data"]).all()
        if dataset_type is not ParquetDataset:
            ds.path.unlink()
            assert not ds.path.exists()
            ds._save(df)
            assert ds.path.exists()
    else:
        ds._save(df)
        assert (ds._load()["data"] == df["data"]).all()


def test_azureml_assetdataset_raises_DatasetError_azureml_type():
    with pytest.raises(DatasetError, match="mltable"):
        AzureMLAssetDataset(
            dataset={
                "type": PickleDataset,
                "filepath": "some/random/path/test.pickle",
            },
            azureml_dataset="test_dataset",
            version=Version(None, None),
            azureml_type="mltable",
        )


def test_azureml_assetdataset_raises_DatasetError_wrapped_dataset_versioned():
    with pytest.raises(DatasetError, match=VERSIONED_FLAG_KEY):
        AzureMLAssetDataset(
            dataset={
                "type": PickleDataset,
                "filepath": "some/random/path/test.pickle",
                "versioned": True,
            },
            azureml_dataset="test_dataset",
            version=Version(None, None),
        )


@pytest.mark.parametrize(
    "azureml_version,expected_version,mock_azureml_client",
    [
        ("100", "100", {"path": "azfs://test/path", "type": "uri_folder"}),
        (100, "100", {"path": "azfs://test/path", "type": "uri_folder"}),
        (None, "1", {"path": "azfs://test/path", "type": "uri_folder"}),
    ],
    indirect=["mock_azureml_client"],
)
@pytest.mark.usefixtures("in_temp_dir")
def test_azureml_asset_dataset_with_azureml_version(
    mock_azureml_client,
    mock_azureml_config,
    azureml_version,
    expected_version,
):
    """Test that azureml_version parameter correctly overrides version resolution."""
    ds = AzureMLAssetDataset(
        dataset={
            "type": PickleDataset,
            "filepath": "test.pickle",
        },
        azureml_dataset="test_dataset",
        azureml_version=azureml_version,
    )
    ds._azureml_config = Path(mock_azureml_config)

    # Test that _resolve_azureml_version returns the expected version
    assert ds._resolve_azureml_version() == expected_version

    # Test that the dataset can be constructed with azureml_version
    assert ds._azureml_version == azureml_version

    # Test that path includes the resolved version for local runs
    ds._local_run = True
    expected_path = Path("data") / "test_dataset" / expected_version / "test.pickle"
    assert ds.path == expected_path


def test_azureml_pipeline_dataset(tmp_path: Path):
    ds = AzureMLPipelineDataset(
        {
            "type": PickleDataset,
            "backend": "cloudpickle",
            "filepath": (original_path := str(tmp_path / "test.pickle")),
        }
    )
    assert (
        str(ds.path) == original_path
    ), "Path should be set to the underlying filepath"

    ds.root_dir = (modified_path := str(tmp_path))
    modified_path = Path(modified_path) / "test.pickle"
    assert ds.path == modified_path, "Path should be modified to the supplied value"

    ds.save("test")
    assert Path(modified_path).stat().st_size > 0, "File does not seem to be saved"
    assert ds.load() == "test", "Objects are not the same after deserialization"


