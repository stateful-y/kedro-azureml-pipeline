"""Kedro hooks for Azure ML dataset integration."""

from kedro.framework.hooks import hook_impl

from kedro_azureml_pipeline.config import WorkspacesConfig
from kedro_azureml_pipeline.datasets.asset_dataset import AzureMLAssetDataset
from kedro_azureml_pipeline.runner import AzurePipelinesRunner


class AzureMLLocalRunHook:
    """Hook that configures Azure ML asset datasets for local and remote runs.

    See Also
    --------
    `kedro_azureml_pipeline.datasets.AzureMLAssetDataset` : Dataset managed by this hook.
    `kedro_azureml_pipeline.runner.AzurePipelinesRunner` : Remote runner detected by the hook.
    `kedro_azureml_pipeline.config.WorkspacesConfig` : Workspace config injected into datasets.
    """

    @hook_impl
    def after_context_created(self, context) -> None:
        """Register the ``azureml`` config pattern and resolve workspace config.

        Parameters
        ----------
        context : KedroContext
            Kedro project context.
        """
        if "azureml" not in context.config_loader.config_patterns:
            context.config_loader.config_patterns.update({"azureml": ["azureml*", "azureml*/**", "**/azureml*"]})
        self.azure_config = WorkspacesConfig.model_validate(context.config_loader["azureml"]["workspace"]).resolve()

    @hook_impl
    def after_catalog_created(self, catalog):
        """Inject workspace config into all ``AzureMLAssetDataset`` entries.

        Parameters
        ----------
        catalog : DataCatalog
            Created data catalog.
        """
        for dataset_name in catalog.filter():
            dataset = catalog[dataset_name]
            if isinstance(dataset, AzureMLAssetDataset):
                dataset.azure_config = self.azure_config
                catalog[dataset_name] = dataset

    @hook_impl
    def before_pipeline_run(self, run_params, pipeline, catalog):
        """Switch asset datasets between local-intermediate and remote mode.

        Parameters
        ----------
        run_params : dict
            Parameters passed to the run command.
        pipeline : Pipeline
            Pipeline about to be run.
        catalog : DataCatalog
            Data catalog.
        """
        for dataset_name in catalog.filter():
            dataset = catalog[dataset_name]
            if isinstance(dataset, AzureMLAssetDataset):
                if AzurePipelinesRunner.__name__ not in run_params["runner"]:
                    # when running locally using an AzureMLAssetDataset
                    # as an intermediate dataset we don't want download
                    # but still set to run local with a local version.
                    if dataset_name not in pipeline.inputs():
                        dataset.as_local_intermediate()
                # when running remotely we still want to provide information
                # from the azureml config for getting the dataset version during
                # remote runs
                else:
                    dataset.as_remote()

                catalog[dataset_name] = dataset


azureml_local_run_hook = AzureMLLocalRunHook()
