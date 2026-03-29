from pathlib import Path

import pandas as pd
import pytest
from kedro.io.core import VERSIONED_FLAG_KEY, DatasetError, Version
from kedro_datasets.pandas import ParquetDataset
from kedro_datasets.pickle import PickleDataset

from kedro_azureml_pipeline.datasets import (
    AzureMLAssetDataset,
    AzureMLPipelineDataset,
)


class TestAzureMLAssetDataset:
    """Tests for ``AzureMLAssetDataset`` load, save, versioning, and validation."""

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
    def test_load_save_with_various_paths(
        self,
        mock_azureml_client,
        mock_azureml_config,
        dataset_type,
        path_in_aml,
        path_locally,
        download_path,
        local_run,
        download,
    ):
        """Dataset resolves paths and round-trips data correctly."""
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

    def test_raises_on_invalid_azureml_type(self):
        """``mltable`` is not a valid azureml_type."""
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

    def test_raises_when_wrapped_dataset_is_versioned(self):
        """The underlying dataset must not set its own ``versioned`` flag."""
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
    def test_version_resolution(
        self,
        mock_azureml_client,
        mock_azureml_config,
        azureml_version,
        expected_version,
    ):
        """Explicit ``azureml_version`` is used or latest is fetched."""
        ds = AzureMLAssetDataset(
            dataset={
                "type": PickleDataset,
                "filepath": "test.pickle",
            },
            azureml_dataset="test_dataset",
            azureml_version=azureml_version,
        )
        ds._azureml_config = Path(mock_azureml_config)

        assert ds._resolve_azureml_version() == expected_version
        assert ds._azureml_version == azureml_version

        ds._local_run = True
        expected_path = Path("data") / "test_dataset" / expected_version / "test.pickle"
        assert ds.path == expected_path

    def test_as_local_intermediate_sets_flags(self):
        """``as_local_intermediate`` disables download and marks local run."""
        ds = AzureMLAssetDataset(
            dataset={"type": PickleDataset, "filepath": "test.pickle"},
            azureml_dataset="test_ds",
            version=Version(None, None),
        )
        ds.as_local_intermediate()
        assert ds._download is False
        assert ds._local_run is True

    def test_as_remote_sets_flags(self):
        """``as_remote`` disables both download and local run."""
        ds = AzureMLAssetDataset(
            dataset={"type": PickleDataset, "filepath": "test.pickle"},
            azureml_dataset="test_ds",
            version=Version(None, None),
        )
        ds.as_remote()
        assert ds._download is False
        assert ds._local_run is False


class TestAzureMLPipelineDataset:
    """Tests for ``AzureMLPipelineDataset`` save and load."""

    def test_path_matches_underlying_filepath(self, tmp_path: Path):
        """The ``path`` property returns the underlying dataset filepath."""
        original_path = str(tmp_path / "test.pickle")
        ds = AzureMLPipelineDataset({
            "type": PickleDataset,
            "backend": "cloudpickle",
            "filepath": original_path,
        })
        assert str(ds.path) == original_path

    def test_save_and_load_round_trip(self, tmp_path: Path):
        """Data round-trips through save and load."""
        ds = AzureMLPipelineDataset({
            "type": PickleDataset,
            "backend": "cloudpickle",
            "filepath": str(tmp_path / "round_trip.pickle"),
        })
        data = {"key": "value"}
        ds.save(data)
        assert ds.load() == data

    def test_describe_returns_dict(self, tmp_path: Path):
        """``_describe`` returns a dictionary."""
        ds = AzureMLPipelineDataset({
            "type": PickleDataset,
            "backend": "cloudpickle",
            "filepath": str(tmp_path / "desc.pickle"),
        })
        desc = ds._describe()
        assert isinstance(desc, dict)

    def test_exists_reflects_file_state(self, tmp_path: Path):
        """``_exists`` returns whether the underlying file is present."""
        ds = AzureMLPipelineDataset({
            "type": PickleDataset,
            "backend": "cloudpickle",
            "filepath": str(tmp_path / "exists.pickle"),
        })
        assert not ds._exists()
        ds.save("data")
        assert ds._exists()

    def test_root_dir_changes_save_path(self, tmp_path: Path):
        """Setting ``root_dir`` redirects the save/load location."""
        ds = AzureMLPipelineDataset({
            "type": PickleDataset,
            "backend": "cloudpickle",
            "filepath": "test.pickle",
        })
        ds.root_dir = str(tmp_path)
        modified_path = tmp_path / "test.pickle"
        assert ds.path == modified_path, "Path should be modified to the supplied value"

        ds.save("test")
        assert modified_path.stat().st_size > 0, "File does not seem to be saved"
        assert ds.load() == "test", "Objects are not the same after deserialization"
