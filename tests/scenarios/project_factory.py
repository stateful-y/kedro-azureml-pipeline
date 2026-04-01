"""Factory for building isolated Kedro project directories for testing."""

from __future__ import annotations

import importlib
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from click.testing import CliRunner
from kedro.framework.cli.starters import create_cli as kedro_cli


@dataclass
class KedroProjectOptions:
    """Options to build a fake Kedro project scenario for testing.

    Attributes
    ----------
    project_name : str | None
        Name of the Kedro project.
    project_path : Path | None
        Path where the project is created (populated by factory).
    package_name : str | None
        Python package name for the Kedro project (populated by factory).
    env : str
        Kedro environment to write configs to (e.g., "base", "local").
    catalog : dict
        Content for catalog.yml under conf/<env>/.
    azureml : dict | None
        Content for azureml.yml under conf/<env>/.
    parameters : dict | None
        Content for parameters file under conf/<env>/.
    parameters_filename : str
        Name for the parameters file (default: "parameters.yml").
    pipeline_registry_py : str | None
        Custom pipeline_registry.py content to inject.
    plugins : list[str]
        Plugin distribution names allowed to load hooks during tests.
    """

    project_name: str | None = None
    project_path: Path | None = None
    package_name: str | None = None
    env: str = "base"
    catalog: dict[str, Any] = field(default_factory=dict)
    azureml: dict[str, Any] | None = None
    parameters: dict[str, Any] | None = None
    parameters_filename: str = "parameters.yml"
    pipeline_registry_py: str | None = None
    plugins: list[str] = field(default_factory=list)


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict to a YAML file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            sort_keys=True,
            allow_unicode=True,
            default_flow_style=False,
            indent=2,
        )


def build_kedro_project_scenario(
    temp_directory: Path,
    options: KedroProjectOptions,
    project_name: str,
) -> KedroProjectOptions:
    """Create a fresh Kedro project in a temp dir and inject scenario configs.

    Parameters
    ----------
    temp_directory : Path
        Temporary base directory for project creation.
    options : KedroProjectOptions
        Scenario options including env, catalog, azureml config, etc.
    project_name : str
        Name for the new project directory.

    Returns
    -------
    KedroProjectOptions
        The options object with project_name, project_path, and package_name populated.
    """
    os.chdir(temp_directory)

    package_name = project_name.replace("-", "_")
    project_path: Path = Path(temp_directory) / project_name
    if project_path.exists():
        shutil.rmtree(project_path)

    cli_runner = CliRunner()
    cli_runner.invoke(
        kedro_cli,
        ["new", "-v", "--name", project_name, "--tools", "none", "--example", "no"],
    )

    # Write ALLOWED_HOOK_PLUGINS to settings.py
    settings_file = project_path / "src" / package_name / "settings.py"
    settings_text = settings_file.read_text(encoding="utf-8")
    allowed_tuple = ", ".join([f"'{p}'" for p in options.plugins])
    settings_text += f"\n\n# Allowed third-party plugin hooks for tests\nALLOWED_HOOK_PLUGINS = ({allowed_tuple})\n"
    settings_file.write_text(settings_text, encoding="utf-8")

    # Inject configuration files
    conf_env_dir = project_path / "conf" / options.env
    conf_env_dir.mkdir(parents=True, exist_ok=True)

    if options.catalog:
        _write_yaml(conf_env_dir / "catalog.yml", options.catalog)

    if options.azureml:
        _write_yaml(conf_env_dir / "azureml.yml", options.azureml)

    if options.parameters is not None:
        filename = options.parameters_filename or "parameters.yml"
        _write_yaml(conf_env_dir / filename, options.parameters)

    # Inject custom pipeline registry if provided
    src_dir = project_path / "src"
    package_dirs = [p for p in src_dir.iterdir() if p.is_dir() and p.name != "__pycache__"]
    if not package_dirs:
        msg = f"No package directory found under {src_dir}"
        raise RuntimeError(msg)

    if package_dirs:
        package_name = package_dirs[0].name
        if options.pipeline_registry_py is not None:
            pipeline_registry_file = package_dirs[0] / "pipeline_registry.py"
            pipeline_registry_file.write_text(options.pipeline_registry_py, encoding="utf-8")

        # Clear cached modules so pipeline registry updates are picked up
        sys.modules.pop("kedro.framework.project", None)
        sys.modules.pop(f"{package_name}.pipeline_registry", None)
        for modname in list(sys.modules.keys()):
            if modname == f"{package_name}.pipelines" or modname.startswith(f"{package_name}.pipelines."):
                sys.modules.pop(modname, None)

    # Configure the Kedro project
    configure_project = importlib.import_module("kedro.framework.project").configure_project
    configure_project(package_name)

    options.project_name = project_name
    options.project_path = project_path
    options.package_name = package_name

    return options
