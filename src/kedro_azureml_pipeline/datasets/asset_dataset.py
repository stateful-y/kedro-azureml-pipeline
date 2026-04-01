"""Azure ML Data Asset dataset for file and folder assets."""

import logging
from functools import partial
from operator import attrgetter
from pathlib import Path
from typing import Any, Literal, get_args

import azure.ai.ml._artifacts._artifact_utilities as artifact_utils
from azure.core.exceptions import ResourceNotFoundError
from cachetools import Cache, cachedmethod
from cachetools.keys import hashkey
from kedro.io.core import (
    VERSION_KEY,
    VERSIONED_FLAG_KEY,
    AbstractDataset,
    AbstractVersionedDataset,
    DatasetError,
    DatasetNotFoundError,
    Version,
    VersionNotFoundError,
)

from kedro_azureml_pipeline.client import _get_azureml_client
from kedro_azureml_pipeline.config import WorkspaceConfig
from kedro_azureml_pipeline.datasets.pipeline_dataset import AzureMLPipelineDataset

AzureMLDataAssetType = Literal["uri_file", "uri_folder"]
logger = logging.getLogger(__name__)


class AzureMLAssetDataset(AzureMLPipelineDataset, AbstractVersionedDataset):
    """Kedro dataset backed by an Azure ML Data Asset.

    Supports both ``uri_folder`` and ``uri_file`` asset types and handles
    automatic download during local execution.

    Parameters
    ----------
    azureml_dataset : str
        Name of the Azure ML Data Asset.
    dataset : str or type or dict
        Underlying Kedro dataset definition.
    root_dir : str
        Local folder for dataset storage during local runs.
    filepath_arg : str
        Argument name that sets the filepath on the wrapped dataset.
    azureml_type : {"uri_folder", "uri_file"}
        Azure ML asset type.
    version : Version or None
        Kedro version object (deprecated, use *azureml_version*).
    azureml_version : str or None
        Explicit Azure ML dataset version.
    metadata : dict or None
        Arbitrary metadata ignored by Kedro.

    See Also
    --------
    [AzureMLPipelineDataset][kedro_azureml_pipeline.datasets.AzureMLPipelineDataset] : Base class for pipeline data passing.
    [AzureMLLocalRunHook][kedro_azureml_pipeline.hooks.AzureMLLocalRunHook] : Configures this dataset for local runs.
    [AzurePipelinesRunner][kedro_azureml_pipeline.runner.AzurePipelinesRunner] : Rewires paths during remote runs.
    """

    versioned = True

    def __init__(
        self,
        azureml_dataset: str,
        dataset: str | type[AbstractDataset] | dict[str, Any],
        root_dir: str = "data",
        filepath_arg: str = "filepath",
        azureml_type: AzureMLDataAssetType = "uri_folder",
        version: Version | None = None,
        azureml_version: str | None = None,
        metadata: dict[str, Any] = None,
    ):
        super().__init__(
            dataset=dataset,
            root_dir=root_dir,
            filepath_arg=filepath_arg,
            metadata=metadata,
        )

        self._azureml_dataset = azureml_dataset
        self._version = version
        self._azureml_version = azureml_version
        # 1 entry for load version, 1 for save version
        self._version_cache = Cache(maxsize=2)  # type: Cache
        # Execution-context flags, toggled by ``as_local_intermediate`` and
        # ``as_remote``.  ``_download`` controls whether ``_load`` fetches
        # the asset from Azure ML; ``_local_run`` controls whether path
        # resolution includes the dataset name and version prefix.
        self._download = True
        self._local_run = True
        self._azureml_config = None
        self._azureml_type = azureml_type
        if self._azureml_type not in get_args(AzureMLDataAssetType):
            raise DatasetError(
                f"Invalid azureml_type '{self._azureml_type}' in dataset definition. "
                f"Valid values are: {get_args(AzureMLDataAssetType)}"
            )

        # Versioning is handled by Azure ML Data Asset versions, not Kedro's
        # built-in versioning mechanism.
        if VERSION_KEY in self._dataset_config:  # pragma: no cover – parent __init__ raises first
            raise DatasetError(
                f"'{self.__class__.__name__}' does not support versioning of the "
                f"underlying dataset. Please remove '{VERSIONED_FLAG_KEY}' flag from "
                f"the dataset definition."
            )

    @property
    def azure_config(self) -> WorkspaceConfig:
        """Return the Azure ML workspace configuration.

        Returns
        -------
        WorkspaceConfig
            Current workspace configuration.
        """
        return self._azureml_config

    @azure_config.setter
    def azure_config(self, azure_config: WorkspaceConfig) -> None:
        """Set the Azure ML workspace configuration.

        Parameters
        ----------
        azure_config : WorkspaceConfig
            Workspace configuration to use.
        """
        self._azureml_config = azure_config

    @property
    def path(self) -> str:
        """Return the full path to the underlying dataset file.

        Returns
        -------
        Path
            Versioned path for local runs, plain path for remote.
        """
        # For local runs we want to replicate the folder structure of the remote dataset.
        # Otherwise kedros versioning would version at the file/folder level and not the
        # AzureML dataset level
        if self._local_run:
            return (
                Path(self.root_dir)
                / self._azureml_dataset
                / self._resolve_azureml_version()
                / Path(self._dataset_config[self._filepath_arg])
            )
        else:
            return Path(self.root_dir) / Path(self._dataset_config[self._filepath_arg])

    @property
    def download_path(self) -> str:
        """Return the target download directory path.

        Returns
        -------
        str
            Parent directory for files, or the path itself for folders.
        """
        # Because `is_dir` and `is_file` don't work if the path does not
        # exist, we use this heuristic to identify paths vs folders.
        if self.path.suffix != "":
            return self.path.parent.as_posix()
        else:
            return self.path.as_posix()

    def _construct_dataset(self) -> AbstractDataset:
        """Build the underlying dataset with the resolved filepath.

        Returns
        -------
        AbstractDataset
            Instantiated underlying dataset.
        """
        dataset_config = self._dataset_config.copy()
        dataset_config[self._filepath_arg] = str(self.path)
        return self._dataset_type(**dataset_config)

    def _get_latest_version(self) -> str:
        """Fetch the latest Data Asset version from Azure ML.

        Returns
        -------
        str
            Latest version string.

        Raises
        ------
        DatasetNotFoundError
            If the Data Asset does not exist.
        """
        try:
            with _get_azureml_client(config=self._azureml_config) as ml_client:
                return ml_client.data.get(self._azureml_dataset, label="latest").version
        except ResourceNotFoundError as exc:
            raise DatasetNotFoundError(f"Did not find Azure ML Data Asset for {self}") from exc

    @cachedmethod(cache=attrgetter("_version_cache"), key=partial(hashkey, "load"))
    def _fetch_latest_load_version(self) -> str:  # pragma: no cover – called by Kedro internals
        """Return the latest load version, cached after first call.

        Returns
        -------
        str
            Latest version string.
        """
        return self._get_latest_version()

    def _resolve_azureml_version(self) -> str:
        """Resolve the Azure ML dataset version to use.

        Returns the explicit ``azureml_version`` if provided, otherwise
        fetches the latest version.

        Returns
        -------
        str
            Version string.
        """
        if self._azureml_version is not None:
            return str(self._azureml_version)
        return self._get_latest_version()

    def _get_azureml_dataset(self):
        """Retrieve the Azure ML Data Asset object.

        Returns
        -------
        Data
            Azure ML Data Asset.
        """
        with _get_azureml_client(config=self._azureml_config) as ml_client:
            return ml_client.data.get(self._azureml_dataset, version=self._resolve_azureml_version())

    def _load(self) -> Any:
        """Load data, downloading the asset from Azure ML if needed.

        Returns
        -------
        Any
            Loaded data.

        Raises
        ------
        VersionNotFoundError
            If the specified version does not exist.
        """
        if self._download:
            try:
                azureml_ds = self._get_azureml_dataset()
            except ResourceNotFoundError as exc:
                raise VersionNotFoundError(
                    f"Did not find version {self._resolve_azureml_version()} for {self}"
                ) from exc

            # Use Azure ML SDK native download functionality
            # This avoids the ARM64 compatibility issues with azureml-fsspec
            with _get_azureml_client(config=self._azureml_config) as ml_client:
                logger.info(
                    f"Downloading dataset {self._azureml_dataset} version "
                    f"{self._resolve_azureml_version()} for local execution"
                )
                artifact_utils.download_artifact_from_aml_uri(
                    uri=azureml_ds.path,
                    destination=self.download_path,
                    datastore_operation=ml_client.datastores,
                )
        return self._construct_dataset().load()

    def _save(self, data: Any) -> None:
        """Save data through the underlying dataset.

        Parameters
        ----------
        data : Any
            Data to save.
        """
        self._construct_dataset().save(data)

    def as_local_intermediate(self):
        """Configure the dataset to skip Azure ML download for local intermediates."""
        self._download = False
        # for local runs we want the data to be saved as a "local version"
        self._version = Version("local", "local")

    def as_remote(self):
        """Configure the dataset for remote execution on Azure ML."""
        self._version = None
        self._local_run = False
        self._download = False
