from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from kedro.config import OmegaConfigLoader
from kedro.framework.context import KedroContext

from kedro_azureml_pipeline.config import KedroAzureMLConfig
from kedro_azureml_pipeline.manager import KedroContextManager


class TestKedroContextManager:
    """Tests for ``KedroContextManager`` lifecycle."""

    def test_creates_valid_context(self, patched_kedro_package):
        """Manager returns a valid context with plugin config."""
        with KedroContextManager(project_path="tests", env="base") as mgr:
            assert isinstance(mgr, KedroContextManager)
            assert isinstance(mgr.context, KedroContext)
            assert isinstance(mgr.plugin_config, KedroAzureMLConfig)

    def test_loads_config_with_omegaconf(self, patched_kedro_package):
        """Manager works with OmegaConfigLoader."""
        with KedroContextManager(project_path="tests", env="local") as mgr, patch.object(mgr, "context") as context:
            context.mock_add_spec(KedroContext)
            context.config_loader = OmegaConfigLoader(
                str(Path.cwd() / "tests" / "conf"),
                config_patterns={"azureml": ["azureml*"]},
                default_run_env="local",
            )
            assert isinstance(mgr.context, KedroContext)
            assert isinstance(mgr.plugin_config, KedroAzureMLConfig)

    @pytest.mark.parametrize("as_custom_config_loader", [True, False])
    def test_raises_on_missing_config(self, patched_kedro_package, as_custom_config_loader):
        """A ``ValueError`` is raised when azureml.yml is missing."""
        with KedroContextManager(project_path="tests", env="local") as mgr, patch.object(mgr, "context") as context:
            context.mock_add_spec(KedroContext)
            context.config_loader = (cl := MagicMock())
            if not as_custom_config_loader:
                cl.mock_add_spec(OmegaConfigLoader)
            cl.get = lambda *_: None
            cl.__getitem__ = lambda *_: None
            with pytest.raises(
                ValueError,
                match=(
                    "You're using a custom config loader.*"
                    if as_custom_config_loader
                    else "Missing azureml.yml files.*"
                ),
            ):
                _ = mgr.plugin_config
