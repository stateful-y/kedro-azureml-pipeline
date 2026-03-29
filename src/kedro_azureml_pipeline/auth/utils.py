"""Azure credential helpers."""

import os

from azure.identity import DefaultAzureCredential, InteractiveBrowserCredential


def get_azureml_credentials():
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
    `kedro_azureml_pipeline.client.AzureMLPipelinesClient` : Uses credentials for job submission.
    `kedro_azureml_pipeline.scheduler.AzureMLScheduleClient` : Uses credentials for schedule management.
    """
    try:
        # On a AzureML compute instance, the managed identity will take precedence,
        # while it does not have enough permissions.
        # So, if we are on an AzureML compute instance, we disable the managed identity.
        is_azureml_managed_identity = "MSI_ENDPOINT" in os.environ
        credential = DefaultAzureCredential(exclude_managed_identity_credential=is_azureml_managed_identity)
        # Check if given credential can get token successfully.
        credential.get_token("https://management.azure.com/.default")
    except Exception:
        # Fall back to InteractiveBrowserCredential in case DefaultAzureCredential not work
        credential = InteractiveBrowserCredential()
    return credential
