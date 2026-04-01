"""Pipeline dataset for passing data between Azure ML nodes."""

import contextlib
import logging
from pathlib import Path
from typing import Any

from kedro.io.core import (
    VERSION_KEY,
    VERSIONED_FLAG_KEY,
    AbstractDataset,
    DatasetError,
    parse_dataset_definition,
)

from kedro_azureml_pipeline.distributed.utils import (
    is_distributed_environment,
    is_distributed_master_node,
)

logger = logging.getLogger(__name__)


class AzureMLPipelineDataset(AbstractDataset):
    """Dataset for passing data between Azure ML pipeline nodes.

    Wraps an underlying Kedro dataset and rewrites its file path to
    point at Azure ML compute mount paths during remote execution.

    Parameters
    ----------
    dataset : str or type or dict
        Underlying dataset definition. Accepts a class that inherits
        from ``AbstractDataset``, a fully qualified class name string,
        or a dict with a ``type`` key.
    root_dir : str
        Folder prepended to the underlying dataset filepath.
    filepath_arg : str
        Argument name on the wrapped dataset that controls the filepath.
    metadata : dict or None
        Arbitrary metadata ignored by Kedro.

    See Also
    --------
    [AzureMLAssetDataset][kedro_azureml_pipeline.datasets.AzureMLAssetDataset] : Versioned Data Asset extension.
    [AzurePipelinesRunner][kedro_azureml_pipeline.runner.AzurePipelinesRunner] : Rewires dataset paths at runtime.
    """

    def __init__(
        self,
        dataset: str | type[AbstractDataset] | dict[str, Any],
        root_dir: str = "data",
        filepath_arg: str = "filepath",
        metadata: dict[str, Any] = None,
    ):
        dataset = dataset if isinstance(dataset, dict) else {"type": dataset}
        self._dataset_type, self._dataset_config = parse_dataset_definition(dataset)

        self.root_dir = root_dir
        self._filepath_arg = filepath_arg
        self.metadata = metadata
        with contextlib.suppress(ValueError):
            # Convert filepath to relative path
            self._dataset_config[self._filepath_arg] = str(
                Path(self._dataset_config[self._filepath_arg]).relative_to(Path.cwd())
            )

        if VERSION_KEY in self._dataset_config:
            raise DatasetError(
                f"'{self.__class__.__name__}' does not support versioning of the "
                f"underlying dataset. Please remove '{VERSIONED_FLAG_KEY}' flag from "
                f"the dataset definition."
            )

    @property
    def path(self) -> str:
        """Return the full path to the underlying dataset file.

        Returns
        -------
        Path
            Combined ``root_dir`` and underlying filepath.
        """
        return Path(self.root_dir) / Path(self._dataset_config[self._filepath_arg])

    @property
    def _filepath(self) -> str:
        """Return path for kedro-mlflow compatibility.

        Returns
        -------
        Path
            Same as ``path``.
        """
        return self.path

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

    def _load(self) -> Any:
        """Load data from the underlying dataset.

        Returns
        -------
        Any
            Loaded data.
        """
        return self._construct_dataset().load()

    def _save(self, data: Any) -> None:
        """Save data through the underlying dataset.

        Skips saving on non-master distributed nodes.

        Parameters
        ----------
        data : Any
            Data to save.
        """
        if is_distributed_environment() and not is_distributed_master_node():
            logger.warning(f"Dataset {self} will not be saved on a distributed node")
        else:
            self._construct_dataset().save(data)

    def _describe(self) -> dict[str, Any]:
        """Return a description dict for logging.

        Returns
        -------
        dict of str to Any
            Dataset type, config, root dir, and filepath arg.
        """
        return {
            "dataset_type": self._dataset_type.__name__,
            "dataset_config": self._dataset_config,
            "root_dir": self.root_dir,
            "filepath_arg": self._filepath_arg,
        }

    def _exists(self) -> bool:
        """Check whether the underlying dataset file exists.

        Returns
        -------
        bool
            ``True`` if the underlying dataset exists.
        """
        return self._construct_dataset().exists()
