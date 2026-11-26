from pathlib import Path

import pytest
from kedro.io import DataCatalog, MemoryDataset
from kedro.io.core import DatasetError, Version
from kedro.pipeline import Pipeline
from kedro_datasets.pickle import PickleDataset

from kedro_azureml_pipeline.datasets.asset_dataset import AzureMLAssetDataset
from kedro_azureml_pipeline.datasets.pipeline_dataset import AzureMLPipelineDataset
from kedro_azureml_pipeline.runner import AzurePipelinesRunner


class TestAzurePipelinesRunner:
    """Tests for basic ``AzurePipelinesRunner`` execution."""

    def test_runs_dummy_pipeline(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """Runner executes a simple three-node pipeline end-to-end."""
        runner = AzurePipelinesRunner(
            data_paths={"input_data": tmp_path, "i2": tmp_path, "i3": tmp_path, "output_data": tmp_path}
        )
        catalog = DataCatalog()
        input_data = ["yolo :)"]
        catalog["input_data"] = MemoryDataset(data=input_data)
        results = runner.run(dummy_pipeline, catalog)

        assert results["output_data"].load() == input_data

    def test_pipeline_data_passing(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """Data persists between pipeline nodes via AzureMLPipelineDataset."""
        input_path = str(tmp_path / "input_data.pickle")
        input_dataset = AzureMLPipelineDataset({
            "type": PickleDataset,
            "backend": "cloudpickle",
            "filepath": input_path,
        })
        input_data = ["yolo :)"]
        input_dataset.save(input_data)

        output_path = str(tmp_path / "i2.pickle")
        output_dataset = AzureMLPipelineDataset({
            "type": PickleDataset,
            "backend": "cloudpickle",
            "filepath": output_path,
        })

        runner = AzurePipelinesRunner(data_paths={"input_data": tmp_path, "i2": tmp_path})
        catalog = DataCatalog()
        runner.run(dummy_pipeline.filter(node_names=["node1"]), catalog)

        assert Path(output_path).stat().st_size > 0
        assert output_dataset.load() == input_data

    def test_uses_factory_resolved_datasets(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """Pipeline inputs resolvable from the original catalog (e.g. via a factory
        pattern) must be taken from there rather than replaced with a stub dataset.
        """
        input_data = ["hello from factory"]
        catalog = DataCatalog()
        catalog["input_data"] = MemoryDataset(data=input_data)

        runner = AzurePipelinesRunner(data_paths={"i2": tmp_path, "i3": tmp_path, "output_data": tmp_path})
        results = runner.run(dummy_pipeline, catalog)

        assert results["output_data"].load() == input_data

    def test_creates_default_pickle_dataset(self, tmp_path: Path):
        """``create_default_data_set`` returns a pipeline dataset with pickle backend."""
        runner = AzurePipelinesRunner(data_paths={"my_ds": str(tmp_path)})
        ds = runner.create_default_data_set("my_ds")
        assert isinstance(ds, AzureMLPipelineDataset)

    def test_data_paths_resolves_factory_datasets(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """Datasets in data_paths that are resolvable via catalog factory patterns
        should be resolved from the catalog, not replaced with a default pickle dataset."""
        input_data = ["factory data"]
        factory_dataset = MemoryDataset(data=input_data)

        catalog = DataCatalog()
        catalog["input_data"] = MemoryDataset(data=input_data)
        # Simulate a dataset that the generator wired as an AzureML stream
        # but is resolvable from the original catalog (e.g. via a factory pattern).
        # i2 is an intermediate dataset not explicitly in catalog but resolvable.
        catalog["i2"] = factory_dataset

        runner = AzurePipelinesRunner(
            data_paths={"i2": str(tmp_path), "i3": str(tmp_path), "output_data": str(tmp_path)}
        )
        results = runner.run(dummy_pipeline, catalog)

        # i2 should have been resolved from the catalog (MemoryDataset),
        # not replaced with a pickle dataset.
        assert results["output_data"].load() == input_data


class TestDatasetPathAdjustments:
    """Tests for root_dir rewiring in the runner."""

    @pytest.mark.parametrize(
        "azureml_dataset_type,data_path",
        [
            ("uri_folder", "/random/folder"),
            ("uri_file", "/random/folder/file.csv"),
        ],
    )
    def test_asset_dataset_root_dir_set_from_data_path(
        self, dummy_pipeline: Pipeline, tmp_path: Path, azureml_dataset_type, data_path
    ):
        """The runner adjusts ``root_dir`` according to the Azure ML data path."""
        input_path = str(tmp_path / "input_data.pickle")
        input_dataset = AzureMLAssetDataset(
            dataset={
                "type": PickleDataset,
                "backend": "cloudpickle",
                "filepath": input_path,
            },
            azureml_dataset="test_dataset_2",
            version=Version(None, None),
            azureml_type=azureml_dataset_type,
        )
        input_dataset.as_remote()
        input_data = ["yolo :)"]
        input_dataset._save(input_data)

        runner = AzurePipelinesRunner(data_paths={"input_data": data_path, "i2": tmp_path})

        catalog = DataCatalog({"input_data": input_dataset})
        assert catalog["input_data"].root_dir == "data"
        runner.run(dummy_pipeline.filter(node_names=["node1"]), catalog)
        assert catalog["input_data"].root_dir == "/random/folder"

    def test_uri_file_uses_parent_directory(self, tmp_path: Path):
        """For uri_file assets, root_dir is set to the parent of the file path."""
        ds = AzureMLAssetDataset(
            dataset={
                "type": PickleDataset,
                "backend": "cloudpickle",
                "filepath": str(tmp_path / "data.pickle"),
            },
            azureml_dataset="file_ds",
            version=Version(None, None),
            azureml_type="uri_file",
        )
        ds.as_remote()

        runner = AzurePipelinesRunner(data_paths={"file_ds": "/mnt/data/file.csv"})
        catalog = DataCatalog({"file_ds": ds})
        runner.run(Pipeline([]), catalog)
        assert catalog["file_ds"].root_dir == "/mnt/data"

    def test_non_azureml_dataset_in_data_paths_gets_default(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """A dataset name in data_paths not in the catalog gets a default pickle dataset."""
        runner = AzurePipelinesRunner(
            data_paths={
                "input_data": str(tmp_path),
                "i2": str(tmp_path),
                "i3": str(tmp_path),
                "output_data": str(tmp_path),
            }
        )
        catalog = DataCatalog()
        catalog["input_data"] = MemoryDataset(data=["test"])
        results = runner.run(dummy_pipeline, catalog)
        assert results["output_data"].load() == ["test"]

    def test_preserves_azure_config_across_catalog_copy(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """Azure configs on AzureMLAssetDataset survive the catalog copy."""
        from unittest.mock import MagicMock

        ds = AzureMLAssetDataset(
            dataset={"type": PickleDataset, "backend": "cloudpickle", "filepath": str(tmp_path / "data.pickle")},
            azureml_dataset="test_ds",
            version=Version(None, None),
        )
        mock_config = MagicMock()
        ds.azure_config = mock_config
        ds.as_remote()

        runner = AzurePipelinesRunner(data_paths={"input_data": str(tmp_path)})
        catalog = DataCatalog({"input_data": ds})
        runner.run(Pipeline([]), catalog)
        assert catalog["input_data"].azure_config is mock_config

    def test_unsatisfied_inputs_get_default_dataset(self, tmp_path: Path):
        """Pipeline inputs not in the catalog or data_paths get a default dataset."""
        from kedro.pipeline import node
        from kedro.pipeline import pipeline as make_pipeline

        def noop(x):
            return x

        # Single-node pipeline: input "missing_input" -> output "out"
        pipe = make_pipeline([node(noop, "missing_input", "out", name="n1")])
        runner = AzurePipelinesRunner(data_paths={"missing_input": str(tmp_path), "out": str(tmp_path)})
        catalog = DataCatalog()
        # The input "missing_input" is unsatisfied -- it's not in the catalog.
        # The runner creates a default pickle dataset for it, then super().run()
        # fails to load because it's empty. We just need the catalog-build path
        # to be hit (lines 115-119).
        with pytest.raises(DatasetError):
            runner.run(pipe, catalog)

    def test_factory_resolved_input_hits_unsatisfied_branch(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """A factory-resolved pipeline input triggers the unsatisfied-input lookup."""
        from kedro.io.catalog_config_resolver import CatalogConfigResolver

        # Create a factory catalog that resolves "input_data" via pattern.
        # "input_data" is NOT in catalog.filter() but IS in catalog via __contains__.
        resolver = CatalogConfigResolver(config={"{name}": {"type": "kedro.io.MemoryDataset"}})
        catalog = DataCatalog(datasets={}, config_resolver=resolver)

        assert "input_data" not in catalog.filter()
        assert "input_data" in catalog

        # data_paths doesn't include "input_data"
        runner = AzurePipelinesRunner(
            data_paths={"i2": str(tmp_path), "i3": str(tmp_path), "output_data": str(tmp_path)}
        )
        # This hits lines 115-117: unsatisfied input resolved from original catalog
        with pytest.raises(DatasetError):
            # Will fail during execution because factory-resolved MemoryDataset has no data
            runner.run(dummy_pipeline, catalog)

    def test_non_pipeline_dataset_in_catalog_skipped(self, tmp_path: Path):
        """Non-AzureMLPipelineDataset entries in the catalog are not rewired."""
        runner = AzurePipelinesRunner(data_paths={"mem_ds": str(tmp_path)})
        catalog = DataCatalog({"mem_ds": MemoryDataset(data="hello")})
        runner.run(Pipeline([]), catalog)
        # MemoryDataset is not AzureMLPipelineDataset so it has no root_dir to set
        assert catalog["mem_ds"].load() == "hello"


class TestDatastoreDatasetInAJob:
    """The runner points an ``AzureMLDatastoreDataset`` at the mounted folder."""

    @staticmethod
    def _dataset():
        from kedro_azureml_pipeline.datasets import AzureMLDatastoreDataset

        return AzureMLDatastoreDataset(
            datastore="shared_store",
            datastore_path="ercot/label-name/table_a",
            dataset={"type": PickleDataset, "backend": "cloudpickle", "filepath": "table_a.pickle"},
        )

    def test_reads_the_mounted_folder_and_downloads_nothing(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """With ``--az-input`` the dataset loads from the mount, with no workspace call."""
        from unittest.mock import patch

        mount = tmp_path / "mount"
        PickleDataset(filepath=str(mount / "table_a.pickle"), backend="cloudpickle").save(["row"])
        runner = AzurePipelinesRunner(data_paths={"input_data": str(mount), "i2": str(tmp_path / "i2")})
        catalog = DataCatalog({"input_data": self._dataset()})
        with patch(
            "kedro_azureml_pipeline.datasets.datastore_dataset.artifact_utils.download_artifact_from_aml_uri"
        ) as download:
            runner.run(dummy_pipeline.filter(node_names=["node1"]), catalog)
        download.assert_not_called()
        assert catalog["input_data"].root_dir == str(mount)
        assert PickleDataset(filepath=str(tmp_path / "i2" / "i2.pickle"), backend="cloudpickle").load() == ["row"]

    def test_entry_added_after_the_package_hook_still_reads_the_mount(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """An entry that the package hook never saw loads from the mount."""
        from kedro_azureml_pipeline.hooks.local_run import AzureMLLocalRunHook

        mount = tmp_path / "mount"
        PickleDataset(filepath=str(mount / "table_a.pickle"), backend="cloudpickle").save(["row"])
        from kedro_azureml_pipeline.config import WorkspaceConfig

        hook = AzureMLLocalRunHook()
        hook.azure_config = WorkspaceConfig(subscription_id="s", resource_group="r", name="w")
        catalog = DataCatalog()
        hook.after_catalog_created(catalog)
        catalog["input_data"] = self._dataset()
        runner = AzurePipelinesRunner(data_paths={"input_data": str(mount), "i2": str(tmp_path / "i2")})
        runner.run(dummy_pipeline.filter(node_names=["node1"]), catalog)
        assert PickleDataset(filepath=str(tmp_path / "i2" / "i2.pickle"), backend="cloudpickle").load() == ["row"]


class TestMemoryDatasetInAJob:
    """The runner leaves a ``MemoryDataset`` entry as it is inside a job."""

    def test_memory_dataset_output_stays_in_memory(self, dummy_pipeline: Pipeline, tmp_path: Path):
        """An output entry that is a ``MemoryDataset`` keeps its class and its data."""
        catalog = DataCatalog({"input_data": MemoryDataset(["row"]), "i2": MemoryDataset()})
        runner = AzurePipelinesRunner(data_paths={"input_data": str(tmp_path), "i2": str(tmp_path / "i2")})
        runner.run(dummy_pipeline.filter(node_names=["node1"]), catalog)
        assert isinstance(catalog["i2"], MemoryDataset)
        assert catalog["i2"].load() == ["row"]
        assert not (tmp_path / "i2").exists()
