"""Custom Kedro runner for executing pipelines inside Azure ML."""

import logging
from pathlib import Path
from typing import Any

from kedro.io import AbstractDataset, DataCatalog
from kedro.pipeline import Pipeline
from kedro.runner import SequentialRunner
from kedro_datasets.pickle import PickleDataset
from pluggy import PluginManager

from kedro_azure_ml.datasets import AzureMLPipelineDataset
from kedro_azure_ml.datasets.asset_dataset import AzureMLAssetDataset

logger = logging.getLogger(__name__)


class AzurePipelinesRunner(SequentialRunner):
    """Sequential runner that rewires dataset paths for Azure ML.

    Parameters
    ----------
    is_async : bool
        Whether to run nodes asynchronously.
    data_paths : dict of str to str or None
        Mapping of dataset name to Azure ML mount/download path.

    See Also
    --------
    `kedro_azure_ml.datasets.AzureMLPipelineDataset` : Dataset whose paths are rewired.
    `kedro_azure_ml.datasets.AzureMLAssetDataset` : Versioned asset dataset.
    `kedro_azure_ml.hooks.AzureMLLocalRunHook` : Hook that detects this runner.
    """

    def __init__(
        self,
        is_async: bool = False,
        data_paths: dict[str, str] | None = None,
    ):
        super().__init__(is_async)
        self.data_paths = data_paths if data_paths is not None else {}

    def run(
        self,
        pipeline: Pipeline,
        catalog: DataCatalog,
        hook_manager: PluginManager = None,
        only_missing_outputs: bool = False,
        run_id: str = None,
    ) -> dict[str, Any]:
        """Execute the pipeline with Azure ML dataset path rewiring.

        Parameters
        ----------
        pipeline : Pipeline
            Kedro pipeline to run.
        catalog : DataCatalog
            Data catalog.
        hook_manager : PluginManager or None
            Pluggy hook manager.
        only_missing_outputs : bool
            If ``True``, only run nodes whose outputs are missing.
        run_id : str or None
            Unique run identifier.

        Returns
        -------
        dict of str to Any
            Mapping of output dataset names to their values.
        """
        # Preserve Azure configs from existing datasets before copying
        azure_configs = {}
        for ds_name in catalog.filter():
            ds = catalog[ds_name]
            if isinstance(ds, AzureMLAssetDataset) and hasattr(ds, "azure_config"):
                azure_configs[ds_name] = ds.azure_config

        # Use Kedro 1.0 copy mechanism instead of shallow_copy
        # For now, create a new catalog with the same datasets
        updated_catalog = DataCatalog()

        # Copy all existing datasets to the new catalog
        for ds_name in catalog.filter():
            ds = catalog[ds_name]
            updated_catalog[ds_name] = ds

        # Restore Azure configs after copying
        for ds_name, azure_config in azure_configs.items():
            if ds_name in updated_catalog.filter():
                ds = updated_catalog[ds_name]
                if isinstance(ds, AzureMLAssetDataset):
                    ds.azure_config = azure_config

        catalog_set = set(updated_catalog.filter())

        # Loop over datasets in arguments to set their paths
        for ds_name, azure_dataset_path in self.data_paths.items():
            if ds_name in catalog_set:
                ds = updated_catalog[ds_name]
                if isinstance(ds, AzureMLPipelineDataset):
                    if isinstance(ds, AzureMLAssetDataset) and ds._azureml_type == "uri_file":
                        ds.root_dir = Path(azure_dataset_path).parent.as_posix()
                    else:
                        ds.root_dir = azure_dataset_path
                    updated_catalog[ds_name] = ds
            else:
                updated_catalog[ds_name] = self.create_default_data_set(ds_name)

        # Loop over remaining input datasets to add them to the catalog
        unsatisfied = pipeline.inputs() - set(updated_catalog.filter())
        for ds_name in unsatisfied:
            if ds_name in catalog:
                # Dataset is resolvable including as a factory dataset
                updated_catalog[ds_name] = catalog[ds_name]
            else:
                updated_catalog[ds_name] = self.create_default_data_set(ds_name)

        return super().run(
            pipeline=pipeline,
            catalog=updated_catalog,
            hook_manager=hook_manager,
            only_missing_outputs=only_missing_outputs,
            run_id=run_id,
        )

    def create_default_data_set(self, ds_name: str) -> AbstractDataset:
        """Create a default pickle dataset for an intermediate output.

        Parameters
        ----------
        ds_name : str
            Dataset name to create.

        Returns
        -------
        AbstractDataset
            A ``AzureMLPipelineDataset`` wrapping a pickle backend.
        """
        return AzureMLPipelineDataset(
            {
                "type": PickleDataset,
                "backend": "cloudpickle",
                "filepath": f"{ds_name}.pickle",
            },
            root_dir=self.data_paths[ds_name],
        )
