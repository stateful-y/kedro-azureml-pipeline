from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from kedro.config import OmegaConfigLoader
from kedro.framework.context import KedroContext
from omegaconf import OmegaConf

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
            cl.__getitem__ = MagicMock(side_effect=KeyError("azureml"))
            with pytest.raises(
                ValueError,
                match=(
                    "You're using a custom config loader.*"
                    if as_custom_config_loader
                    else "Missing azureml.yml files.*"
                ),
            ):
                _ = mgr.plugin_config

    def test_context_access_before_enter_raises(self):
        """Accessing ``context`` without entering the manager raises RuntimeError."""
        mgr = KedroContextManager(env="base")
        with pytest.raises(RuntimeError, match="Session not initialized"):
            _ = mgr.context

    def test_ensure_obj_is_dict_converts_dictconfig(self, patched_kedro_package):
        """``_ensure_obj_is_dict`` converts OmegaConf DictConfig to plain dict."""
        mgr = KedroContextManager(env="base")
        dc = OmegaConf.create({"a": 1, "b": {"c": 2}})
        result = mgr._ensure_obj_is_dict(dc)
        assert isinstance(result, dict)
        assert result == {"a": 1, "b": {"c": 2}}

    def test_ensure_obj_is_dict_converts_nested_dictconfig(self, patched_kedro_package):
        """``_ensure_obj_is_dict`` converts nested DictConfig values in a plain dict."""
        mgr = KedroContextManager(env="base")
        nested = {"key": OmegaConf.create({"inner": 42}), "plain": "value"}
        result = mgr._ensure_obj_is_dict(nested)
        assert isinstance(result["key"], dict)
        assert result["key"] == {"inner": 42}
        assert result["plain"] == "value"

    def test_ensure_obj_is_dict_passes_plain_dict(self, patched_kedro_package):
        """``_ensure_obj_is_dict`` returns plain dicts unchanged."""
        mgr = KedroContextManager(env="base")
        plain = {"a": 1}
        result = mgr._ensure_obj_is_dict(plain)
        assert result == {"a": 1}
