"""Azure ML dataset that reads a folder of a datastore by its path."""

import logging
from pathlib import Path
from typing import Any

import azure.ai.ml._artifacts._artifact_utilities as artifact_utils
from kedro.io.core import AbstractDataset, DatasetError

from kedro_azureml_pipeline.client import _get_azureml_client
from kedro_azureml_pipeline.config import WorkspaceConfig
from kedro_azureml_pipeline.datasets.pipeline_dataset import AzureMLPipelineDataset

logger = logging.getLogger(__name__)


class AzureMLDatastoreDataset(AzureMLPipelineDataset):
    """Read a folder of an Azure ML datastore, named by the datastore and a path inside it.

    The dataset is an input only. In a pipeline job, the generator passes
    ``azureml://datastores/<datastore>/paths/<path>`` as the input of the step, and the
    runner points the dataset at the mounted folder. Outside a job, the first load
    downloads the folder to ``root_dir`` with the workspace given in ``workspace``.
    No hook of this package is needed, so a catalog entry added after the hooks ran
    works the same way.

    Parameters
    ----------
    datastore : str
        Name of the datastore in the workspace.
    datastore_path : str
        Path of the folder inside the datastore, without a leading slash.
    dataset : str or type or dict
        Underlying dataset definition. Its filepath is relative to the folder.
    workspace : WorkspaceConfig or dict or None, default: None
        Workspace of the datastore. Needed only for a load outside a job.
    root_dir : str, default: "data"
        Local folder of the download. The runner replaces it with the mounted folder.
    filepath_arg : str, default: "filepath"
        Argument name on the wrapped dataset that controls the filepath.
    metadata : dict or None, default: None
        Arbitrary metadata ignored by Kedro.

    See Also
    --------
    [AzureMLAssetDataset][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] : Input or output by data asset.
    [AzurePipelinesRunner][kedro_azureml_pipeline.runner.AzurePipelinesRunner] : Sets the mounted folder in a job.
    """

    def __init__(
        self,
        datastore: str,
        datastore_path: str,
        dataset: str | type[AbstractDataset] | dict[str, Any],
        workspace: WorkspaceConfig | dict[str, str] | None = None,
        root_dir: str = "data",
        filepath_arg: str = "filepath",
        metadata: dict[str, Any] | None = None,
    ):
        super().__init__(dataset=dataset, root_dir=root_dir, filepath_arg=filepath_arg, metadata=metadata)
        if not datastore or not datastore_path.strip("/"):
            raise DatasetError(f"'{self.__class__.__name__}' needs a datastore name and a path inside it")
        self.datastore = datastore
        self.datastore_path = datastore_path.strip("/")
        self.workspace = WorkspaceConfig.model_validate(workspace) if isinstance(workspace, dict) else workspace
        self._local_root_dir = root_dir

    @property
    def uri(self) -> str:
        """The folder as an Azure ML datastore URI.

        Returns
        -------
        str
            ``azureml://datastores/<datastore>/paths/<path>``.
        """
        return f"azureml://datastores/{self.datastore}/paths/{self.datastore_path}"

    def _is_mounted(self) -> bool:
        """Return whether the runner replaced ``root_dir`` with a mounted folder.

        Returns
        -------
        bool
            ``True`` when ``root_dir`` differs from the local folder given at creation.
        """
        return str(self.root_dir) != str(self._local_root_dir)

    def _download(self) -> None:
        """Download the folder to ``root_dir``.

        Raises
        ------
        DatasetError
            If no workspace is set.
        """
        if self.workspace is None:
            raise DatasetError(f"Dataset {self} reads {self.uri} outside a job and has no workspace")
        logger.info("Downloading %s to %s", self.uri, self.root_dir)
        with _get_azureml_client(config=self.workspace) as ml_client:
            artifact_utils.download_artifact_from_aml_uri(
                uri=self.uri,
                destination=str(self.root_dir),
                datastore_operation=ml_client.datastores,
            )

    def _load(self) -> Any:
        """Load from the mounted folder, or download the folder first outside a job.

        Returns
        -------
        Any
            Loaded data.
        """
        if not self._is_mounted() and not Path(self.path).exists():
            self._download()
        return self._construct_dataset().load()

    def _save(self, data: Any) -> None:  # noqa: ARG002 -- the signature of AbstractDataset._save
        """Refuse to save: the dataset is an input only.

        Parameters
        ----------
        data : Any
            Unused.

        Raises
        ------
        DatasetError
            Always.
        """
        raise DatasetError(f"'{self.__class__.__name__}' is an input only and cannot be saved")

    def _describe(self) -> dict[str, Any]:
        """Return the datastore, the path and the underlying dataset.

        Returns
        -------
        dict of str to Any
            Dataset description.
        """
        return {**super()._describe(), "datastore": self.datastore, "datastore_path": self.datastore_path}
