"""Azure ML pipeline client for job submission."""

import json
import logging
import os
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from azure.ai.ml import MLClient
from azure.ai.ml.entities import Job
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ServiceRequestError
from azure.identity import CredentialUnavailableError, DefaultAzureCredential, InteractiveBrowserCredential

from kedro_azureml_pipeline.config import WorkspaceConfig

if TYPE_CHECKING:
    from azure.core.credentials import TokenCredential

logger = logging.getLogger(__name__)


def get_azureml_credentials() -> "TokenCredential":
    """Obtain Azure credentials for Azure ML access.

    Tries ``DefaultAzureCredential`` first (excluding managed identity
    on AzureML compute instances). Falls back to
    ``InteractiveBrowserCredential`` on failure.

    Returns
    -------
    TokenCredential
        Azure credential object.

    See Also
    --------
    [AzureMLPipelinesClient][kedro_azureml_pipeline.client.AzureMLPipelinesClient] : Uses credentials for job submission.
    [AzureMLScheduleClient][kedro_azureml_pipeline.scheduler.AzureMLScheduleClient] : Uses credentials for schedule management.
    """
    try:
        # On a AzureML compute instance, the managed identity will take precedence,
        # while it does not have enough permissions.
        # So, if we are on an AzureML compute instance, we disable the managed identity.
        is_azureml_managed_identity = "MSI_ENDPOINT" in os.environ
        credential = DefaultAzureCredential(exclude_managed_identity_credential=is_azureml_managed_identity)
        # Check if given credential can get token successfully.
        credential.get_token("https://management.azure.com/.default")
    except (ClientAuthenticationError, CredentialUnavailableError):
        # Fall back to InteractiveBrowserCredential in case DefaultAzureCredential not work
        credential = InteractiveBrowserCredential()
    return credential


@contextmanager
def _get_azureml_client(config: WorkspaceConfig):
    """Create a temporary ``MLClient`` scoped to *config*.

    Parameters
    ----------
    config : WorkspaceConfig
        Workspace connection details.

    Yields
    ------
    MLClient
        Authenticated Azure ML client.
    """
    client_config = {
        "subscription_id": config.subscription_id,
        "resource_group": config.resource_group,
        "workspace_name": config.name,
    }

    credential = get_azureml_credentials()

    with TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / "config.json"
        config_path.write_text(json.dumps(client_config))
        ml_client = MLClient.from_config(credential=credential, path=str(config_path.absolute()))
        yield ml_client


class AzureMLPipelinesClient:
    """Client wrapper for submitting Azure ML pipeline jobs.

    Parameters
    ----------
    azure_pipeline : Job
        Compiled Azure ML pipeline job.

    See Also
    --------
    [AzureMLPipelineGenerator][kedro_azureml_pipeline.generator.AzureMLPipelineGenerator] : Generates the pipeline job.
    [AzureMLScheduleClient][kedro_azureml_pipeline.scheduler.AzureMLScheduleClient] : Schedule-based submission.
    [WorkspaceConfig][kedro_azureml_pipeline.config.WorkspaceConfig] : Workspace config used by ``run``.
    """

    def __init__(self, azure_pipeline: Job):
        self.azure_pipeline = azure_pipeline

    def run(
        self,
        config: WorkspaceConfig,
        compute_config,
        wait_for_completion=False,
        on_job_scheduled: Callable[[Job], None] | None = None,
        display_name: str | None = None,
        compute_name: str | None = None,
        experiment_name: str | None = None,
    ) -> bool:
        """Submit the pipeline job to Azure ML.

        Parameters
        ----------
        config : WorkspaceConfig
            Workspace connection details.
        compute_config : ComputeConfig
            Compute cluster definitions.
        wait_for_completion : bool
            If ``True``, block until the run finishes.
        on_job_scheduled : callable or None
            Callback invoked with the ``Job`` after scheduling.
        display_name : str or None
            Override display name in the Azure ML portal.
        compute_name : str or None
            Override compute cluster name.
        experiment_name : str or None
            Azure ML experiment name.

        Returns
        -------
        bool
            ``True`` if the job completed or was submitted successfully.

        Raises
        ------
        ValueError
            If the compute cluster does not exist.
        """
        if not experiment_name:
            logger.warning(
                "No experiment_name provided. Set it in mlflow.yml "
                "(tracking.experiment.name) or pass --experiment-name on the CLI. "
                "Azure ML will use a default experiment name."
            )
        with _get_azureml_client(config) as ml_client:
            effective_cluster_name = compute_name or compute_config.root["__default__"].cluster_name
            cluster = ml_client.compute.get(effective_cluster_name)
            if not cluster:
                raise ValueError(f"Cluster {effective_cluster_name} does not exist")

            logger.info(
                f"Creating job on cluster {cluster.name} ({cluster.size}, min instances: {cluster.min_instances}, "
                f"max instances: {cluster.max_instances})"
            )

            if display_name:
                self.azure_pipeline.display_name = display_name

            pipeline_job = ml_client.jobs.create_or_update(
                self.azure_pipeline,
                experiment_name=experiment_name,
                compute=cluster,
            )

            if on_job_scheduled:
                on_job_scheduled(pipeline_job)

            if wait_for_completion:
                try:
                    ml_client.jobs.stream(pipeline_job.name)
                    return True
                except (HttpResponseError, ServiceRequestError):
                    logger.exception("Error while running the pipeline", exc_info=True)
                    return False
            else:
                return True
