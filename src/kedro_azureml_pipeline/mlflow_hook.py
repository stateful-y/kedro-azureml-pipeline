"""Hook that coordinates kedro-mlflow behavior when running inside Azure ML.

This hook fires **before** kedro-mlflow's own hook (via ``tryfirst=True``)
and sets environment variables / MLflow run metadata so that kedro-mlflow
logs to the correct experiment and tags each child run with node context.

The hook is completely inactive unless the ``KEDRO_AZUREML_MLFLOW_ENABLED``
environment variable is set to ``"1"`` (injected by the pipeline generator).
"""

import logging
import os

from kedro.framework.hooks import hook_impl

from kedro_azureml_pipeline.constants import (
    KEDRO_AZUREML_MLFLOW_ENABLED,
    KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME,
    KEDRO_AZUREML_MLFLOW_NODE_NAME,
    KEDRO_AZUREML_MLFLOW_RUN_NAME,
)

logger = logging.getLogger(__name__)


def _is_mlflow_integration_active() -> bool:
    """Check whether the Azure ML MLflow integration is enabled.

    Returns
    -------
    bool
        ``True`` if ``KEDRO_AZUREML_MLFLOW_ENABLED`` equals ``"1"``.
    """
    return os.environ.get(KEDRO_AZUREML_MLFLOW_ENABLED) == "1"


class MlflowAzureMLHook:
    """Coordinates kedro-mlflow inside Azure ML pipeline component jobs.

    Lifecycle
    ---------
    1. ``after_context_created`` (``tryfirst``): pre-sets
       ``MLFLOW_EXPERIMENT_NAME`` so kedro-mlflow picks it up.
    2. ``before_pipeline_run``: tags the active MLflow child run with
       node name, pipeline name, and kedro environment.
    3. ``on_pipeline_error``: tags the run with error information.

    See Also
    --------
    `kedro_azureml_pipeline.generator.AzureMLPipelineGenerator` : Injects MLflow env vars.
    `kedro_azureml_pipeline.hooks.AzureMLLocalRunHook` : Companion hook for dataset config.
    """

    @hook_impl(tryfirst=True)
    def after_context_created(self, context) -> None:
        """Pre-set ``MLFLOW_EXPERIMENT_NAME`` for kedro-mlflow.

        Parameters
        ----------
        context : KedroContext
            Kedro project context.
        """
        if not _is_mlflow_integration_active():
            return

        experiment_name = os.environ.get(KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME)
        if experiment_name:
            os.environ["MLFLOW_EXPERIMENT_NAME"] = experiment_name
            logger.info("kedro-azureml-pipeline: set MLFLOW_EXPERIMENT_NAME=%s", experiment_name)

    @hook_impl(tryfirst=True)
    def before_pipeline_run(self, run_params, pipeline, catalog) -> None:
        """Tag the active MLflow run with Kedro metadata.

        Parameters
        ----------
        run_params : dict
            Parameters passed to the run command.
        pipeline : Pipeline
            Pipeline about to be run.
        catalog : DataCatalog
            Data catalog.
        """
        if not _is_mlflow_integration_active():
            return

        try:
            import mlflow
        except ImportError:
            logger.warning("kedro-azureml-pipeline: mlflow is not installed, skipping run tagging")
            return

        # Ensure the correct experiment is active before kedro-mlflow's hook
        # fires.  Without this, kedro-mlflow would resolve the experiment from
        # mlflow.yml (which may differ from the AzureML job experiment) and
        # pass a mismatched experiment_id to start_run(), causing an
        # MlflowException when MLFLOW_RUN_ID is set by AzureML.
        experiment_name = os.environ.get(KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME)
        if experiment_name and mlflow.active_run() is None:
            mlflow.set_experiment(experiment_name)
            run_id = os.environ.get("MLFLOW_RUN_ID")
            if run_id:
                mlflow.start_run(run_id=run_id)
                logger.info(
                    "kedro-azureml-pipeline: resumed MLflow run %s in experiment '%s'",
                    run_id,
                    experiment_name,
                )

        active_run = mlflow.active_run()
        if active_run is None:
            return

        node_name = os.environ.get(KEDRO_AZUREML_MLFLOW_NODE_NAME, "")
        run_name = os.environ.get(KEDRO_AZUREML_MLFLOW_RUN_NAME, "")
        kedro_env = os.environ.get("KEDRO_ENV", "")

        tags = {}
        if node_name:
            tags["kedro.node_name"] = node_name
        if run_name:
            tags["kedro.pipeline_run_name"] = run_name
        if kedro_env:
            tags["kedro.env"] = kedro_env
        if run_params.get("pipeline_name"):
            tags["kedro.pipeline_name"] = run_params["pipeline_name"]

        if tags:
            mlflow.set_tags(tags)
            logger.info("kedro-azureml-pipeline: tagged MLflow run with %s", tags)

        # Set the child run name to include the node name for clarity
        if node_name:
            child_run_name = f"{run_name} :: {node_name}" if run_name else node_name
            mlflow.MlflowClient().set_tag(active_run.info.run_id, "mlflow.runName", child_run_name)

    @hook_impl
    def on_pipeline_error(self, error, run_params, pipeline, catalog) -> None:
        """Tag the MLflow run with error details.

        Parameters
        ----------
        error : Exception
            The error that occurred.
        run_params : dict
            Parameters passed to the run command.
        pipeline : Pipeline
            Pipeline that failed.
        catalog : DataCatalog
            Data catalog.
        """
        if not _is_mlflow_integration_active():
            return

        try:
            import mlflow
        except ImportError:
            return

        active_run = mlflow.active_run()
        if active_run is None:
            return

        error_msg = str(error)[:250]
        mlflow.set_tag("kedro.error", error_msg)
        node_name = os.environ.get(KEDRO_AZUREML_MLFLOW_NODE_NAME, "")
        if node_name:
            mlflow.set_tag("kedro.failed_node", node_name)


mlflow_azureml_hook = MlflowAzureMLHook()
