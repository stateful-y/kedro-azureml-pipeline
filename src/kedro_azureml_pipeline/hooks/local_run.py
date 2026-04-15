"""Kedro hooks for Azure ML dataset integration."""

import inspect
import logging

from kedro.framework.hooks import hook_impl

from kedro_azureml_pipeline.config import WorkspacesConfig
from kedro_azureml_pipeline.datasets.asset_dataset import AzureMLAssetDataset
from kedro_azureml_pipeline.runner import AzurePipelinesRunner

logger = logging.getLogger(__name__)


class AzureMLLocalRunHook:
    """Hook that configures Azure ML asset datasets for local and remote runs.

    See Also
    --------
    [AzureMLAssetDataset][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] : Dataset managed by this hook.
    [AzurePipelinesRunner][kedro_azureml_pipeline.runner.AzurePipelinesRunner] : Remote runner detected by the hook.
    [WorkspacesConfig][kedro_azureml_pipeline.config.WorkspacesConfig] : Workspace config injected into datasets.
    """

    @staticmethod
    def _patch_azureml_artifact_builder() -> None:
        """Re-register the ``azureml`` artifact builder with a ``**kwargs``-tolerant wrapper.

        MLflow 3.10+ passes ``tracking_uri`` and ``registry_uri`` keyword arguments
        to artifact repository builders, but ``azureml-mlflow``'s
        ``azureml_artifacts_builder`` does not accept them, causing a ``TypeError``.

        This method wraps the original builder so that extra keyword arguments are
        silently dropped.  The patch is a no-op when:

        * ``mlflow`` or ``azureml-mlflow`` is not installed.
        * The builder already accepts ``**kwargs`` (i.e. azureml-mlflow was updated).
        """
        try:
            from azureml.mlflow.entry_point_loaders import azureml_artifacts_builder
            from mlflow.store.artifact.artifact_repository_registry import _artifact_repository_registry
        except ImportError:
            return

        params = inspect.signature(azureml_artifacts_builder).parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            return

        original = azureml_artifacts_builder

        def _tolerant_builder(artifact_uri=None, **kwargs):  # noqa: ARG001
            """Wrap the original builder, forwarding only ``artifact_uri``."""
            return original(artifact_uri=artifact_uri)

        _artifact_repository_registry.register("azureml", _tolerant_builder)
        logger.info("kedro-azureml-pipeline: patched azureml artifact builder to accept extra kwargs")

    @hook_impl
    def after_context_created(self, context) -> None:
        """Register the ``azureml`` config pattern and resolve workspace config.

        Parameters
        ----------
        context : KedroContext
            Kedro project context.
        """
        self._patch_azureml_artifact_builder()
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
