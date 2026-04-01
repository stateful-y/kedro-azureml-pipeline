"""Kedro session and configuration management for Azure ML."""

import logging
import os
from functools import cached_property

from kedro.config import (
    AbstractConfigLoader,
    MissingConfigException,
    OmegaConfigLoader,
)
from kedro.framework.session import KedroSession
from omegaconf import DictConfig, OmegaConf

from kedro_azureml_pipeline.config import KedroAzureMLConfig

logger = logging.getLogger(__name__)


class KedroContextManager:
    """Context manager that wraps a ``KedroSession`` and exposes plugin config.

    Parameters
    ----------
    env : str
        Kedro environment name.
    project_path : str or None
        Path to the Kedro project root.
    runtime_params : dict or None
        Runtime parameter overrides.

    See Also
    --------
    [KedroAzureMLConfig][kedro_azureml_pipeline.config.KedroAzureMLConfig] : Configuration loaded via ``plugin_config``.
    """

    def __init__(
        self,
        env: str,
        project_path: str | None = None,
        runtime_params: dict | None = None,
    ):
        self.runtime_params = runtime_params
        self.env = env
        self.project_path = project_path
        self.session: KedroSession | None = None

    @cached_property
    def context(self):
        """Return the loaded Kedro context.

        Returns
        -------
        KedroContext
            The Kedro context loaded from the session.
        """
        if self.session is None:
            raise RuntimeError("Session not initialized yet")
        return self.session.load_context()

    def _ensure_obj_is_dict(self, obj):
        """Convert OmegaConf containers to plain dicts.

        Parameters
        ----------
        obj : Any
            Object to convert.

        Returns
        -------
        Any
            Plain dict if *obj* was a ``DictConfig``, otherwise unchanged.
        """
        if isinstance(obj, DictConfig):
            obj = OmegaConf.to_container(obj)
        elif isinstance(obj, dict) and any(isinstance(v, DictConfig) for v in obj.values()):
            obj = {k: (OmegaConf.to_container(v) if isinstance(v, DictConfig) else v) for k, v in obj.items()}
        return obj

    @cached_property
    def plugin_config(self) -> KedroAzureMLConfig:
        """Load and validate the plugin configuration from ``azureml.yml``.

        Returns
        -------
        KedroAzureMLConfig
            Validated plugin configuration.

        Raises
        ------
        ValueError
            If ``azureml.yml`` is missing or the config loader is not
            recognized.
        """
        cl: AbstractConfigLoader = self.context.config_loader
        try:
            obj = self.context.config_loader["azureml"]
        except (KeyError, MissingConfigException):
            obj = None

        if obj is None:
            try:
                obj = self._ensure_obj_is_dict(self.context.config_loader["azureml"])
            except (KeyError, MissingConfigException):
                obj = None

        if obj is None:
            if not isinstance(cl, OmegaConfigLoader):
                raise ValueError(
                    f"You're using a custom config loader: {cl.__class__.__qualname__}{os.linesep}"
                    f"you need to add the azureml config to it.{os.linesep}"
                    "Make sure you add azureml* to config_pattern in CONFIG_LOADER_ARGS "
                    f"in the settings.py file.{os.linesep}".strip()
                )
            else:
                raise ValueError(
                    "Missing azureml.yml files in configuration. Make sure that you configure your project first"
                )
        return KedroAzureMLConfig.model_validate(obj)

    def __enter__(self):
        """Create a ``KedroSession`` and return this manager.

        Returns
        -------
        KedroContextManager
            This instance with an active session.
        """
        logger.info("Creating KedroSession (env=%s, project_path=%s)", self.env, self.project_path)
        self.session = KedroSession.create(self.project_path, env=self.env, runtime_params=self.runtime_params)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close the underlying ``KedroSession``.

        Parameters
        ----------
        exc_type : type or None
            Exception type.
        exc_val : BaseException or None
            Exception value.
        exc_tb : TracebackType or None
            Traceback.
        """
        self.session.__exit__(exc_type, exc_val, exc_tb)
