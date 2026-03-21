import os
from pathlib import Path
from typing import List
from unittest import mock
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import yaml
from click.testing import CliRunner
from kedro.framework.startup import ProjectMetadata

from kedro_azureml import cli
from kedro_azureml.config import KedroAzureMLConfig
from kedro_azureml.generator import AzureMLPipelineGenerator
from kedro_azureml.runner import AzurePipelinesRunner
from kedro_azureml.utils import CliContext
from tests.utils import create_kedro_conf_dirs


@pytest.mark.parametrize(
    "aml_env_args",
    [
        ["--aml-env", f"{uuid4().hex}@latest"],
        ["--azureml-environment", f"{uuid4().hex}:v1"],
    ],
    ids=("with AML env", "with AML (long param name)"),
)
def test_can_initialize_basic_plugin_config(
    patched_kedro_package,
    cli_context,
    tmp_path: Path,
    aml_env_args: List[str],
):
    config_path = create_kedro_conf_dirs(tmp_path)
    unique_id = uuid4().hex
    with patch.object(Path, "cwd", return_value=tmp_path):
        runner = CliRunner()

        result = runner.invoke(
            cli.init,
            [
                f"subscription_id_{unique_id}",
                f"resource_group_{unique_id}",
                f"workspace_name_{unique_id}",
                f"cluster_name_{unique_id}",
            ]
            + aml_env_args,
            obj=cli_context,
        )

        assert result.exit_code == 0, result.exception

        azureml_config_path = config_path / "azureml.yml"
        assert (
            azureml_config_path.exists() and azureml_config_path.is_file()
        ), f"{azureml_config_path.absolute()} is not a valid file"

        config: KedroAzureMLConfig = KedroAzureMLConfig.model_validate(
            yaml.safe_load(azureml_config_path.read_text())
        )
        assert config.workspace.resolve().subscription_id == f"subscription_id_{unique_id}"
        assert config.workspace.resolve().resource_group == f"resource_group_{unique_id}"
        assert config.workspace.resolve().name == f"workspace_name_{unique_id}"
        assert (
            config.compute.root["__default__"].cluster_name
            == f"cluster_name_{unique_id}"
        )

        assert config.execution.environment == aml_env_args[1]


@pytest.mark.parametrize(
    "runtime_params",
    ("", '{"unit_test_param": 666.0}'),
    ids=("without params", "with runtime params"),
)
def test_can_compile_pipeline(
    patched_kedro_package,
    cli_context,
    dummy_pipeline,
    dummy_plugin_config,
    tmp_path: Path,
    runtime_params,
):
    from kedro_azureml.config import JobConfig, PipelineFilterOptions
    from kedro_azureml.manager import KedroContextManager

    dummy_plugin_config.jobs = {
        "test_job": JobConfig(
            pipeline=PipelineFilterOptions(pipeline_name="__default__"),
        ),
    }

    mock_mgr = MagicMock(spec=KedroContextManager)
    mock_mgr.plugin_config = dummy_plugin_config
    mock_mgr.context.params = {}
    mock_mgr.context.catalog = MagicMock()
    mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

    with patch.object(
        AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline
    ), patch.object(
        KedroContextManager, "__enter__", return_value=mock_mgr
    ), patch.object(
        KedroContextManager, "__exit__", return_value=False
    ), patch.object(
        Path, "cwd", return_value=tmp_path
    ):
        _ = create_kedro_conf_dirs(tmp_path)
        runner = CliRunner()
        output_path = tmp_path / "pipeline.yml"

        result = runner.invoke(
            cli.compile,
            [
                "-j", "test_job",
                "--output", str(output_path.absolute()),
                "--params", runtime_params,
            ],
            obj=cli_context,
        )
        assert result.exit_code == 0, result.output
        assert isinstance(p := yaml.safe_load(output_path.read_text()), dict) and all(
            k in p for k in ("display_name", "type", "jobs")
        )


def test_can_invoke_execute_cli(
    patched_kedro_package,
    cli_context,
    dummy_pipeline,
    dummy_plugin_config,
    tmp_path: Path,
):
    patched_azure_runner = AzurePipelinesRunner(data_paths={})
    create_kedro_conf_dirs(tmp_path)
    with patch(
        "kedro_azureml.runner.AzurePipelinesRunner", new=patched_azure_runner
    ), patch.dict(
        "kedro.framework.project.pipelines", {"__default__": dummy_pipeline}
    ), patch(
        "kedro_azureml.manager.KedroContextManager.plugin_config",
        new_callable=mock.PropertyMock,
        return_value=dummy_plugin_config,
    ), patch.object(
        Path, "cwd", return_value=tmp_path
    ):
        runner = CliRunner()
        result = runner.invoke(
            cli.execute,
            ["--node", "node1", "--az-output", "i2", str(tmp_path)],
            obj=cli_context,
        )
        assert result.exit_code == 0


@pytest.mark.parametrize(
    "aml_env",
    ("", "unit_test_aml_env@latest"),
    ids=("aml_env default", "aml_env overridden"),
)
@pytest.mark.parametrize(
    "use_default_credentials",
    (False, True),
    ids=("interactive credentials", "default_credentials"),
)
@pytest.mark.parametrize("amlignore", ("empty", "missing", "filled"))
@pytest.mark.parametrize("gitignore", ("empty", "missing", "filled"))
@pytest.mark.parametrize(
    "extra_env",
    (
        ([], {}),
        (["A=B", "C="], {"A": "B", "C": ""}),
        (["A=CDE=F123"], {"A": "CDE=F123"}),
    ),
)
@pytest.mark.parametrize(
    "wait_for_completion",
    (False, True),
    ids=("fire and forget", "wait for completion"),
)
def test_can_invoke_submit(
    patched_kedro_package,
    cli_context,
    dummy_pipeline,
    dummy_plugin_config,
    tmp_path: Path,
    aml_env: str,
    use_default_credentials: bool,
    amlignore: str,
    gitignore: str,
    extra_env: list,
    wait_for_completion: bool,
):
    from kedro_azureml.config import JobConfig, PipelineFilterOptions
    from kedro_azureml.manager import KedroContextManager

    create_kedro_conf_dirs(tmp_path)
    dummy_plugin_config.jobs = {
        "test_job": JobConfig(
            pipeline=PipelineFilterOptions(pipeline_name="__default__"),
        ),
    }

    mock_mgr = MagicMock(spec=KedroContextManager)
    mock_mgr.plugin_config = dummy_plugin_config
    mock_mgr.context.params = {}
    mock_mgr.context.catalog = MagicMock()
    mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

    with patch.dict(
        "kedro.framework.project.pipelines", {"__default__": dummy_pipeline}
    ), patch.object(Path, "cwd", return_value=tmp_path), patch(
        "kedro_azureml.client.MLClient"
    ) as ml_client_patched, patch(
        "kedro_azureml.auth.utils.DefaultAzureCredential"
    ) as default_credentials, patch(
        "kedro_azureml.auth.utils.InteractiveBrowserCredential"
    ) as interactive_credentials, patch.object(
        KedroContextManager, "__enter__", return_value=mock_mgr
    ), patch.object(
        KedroContextManager, "__exit__", return_value=False
    ), patch.object(
        AzureMLPipelineGenerator,
        "get_kedro_pipeline",
        return_value=dummy_pipeline,
    ):
        if not use_default_credentials:
            default_credentials.side_effect = ValueError()

        if amlignore != "missing":
            Path.cwd().joinpath(".amlignore").write_text(
                "" if amlignore == "empty" else "unittest"
            )

        if gitignore != "missing":
            Path.cwd().joinpath(".gitignore").write_text(
                "" if gitignore == "empty" else "unittest"
            )

        runner = CliRunner()
        result = runner.invoke(
            cli.submit,
            ["--once", "-j", "test_job"]
            + (["--aml-env", aml_env] if aml_env else [])
            + (["--wait-for-completion"] if wait_for_completion else [])
            + (sum([["--env-var", k] for k in extra_env[0]], [])),
            obj=cli_context,
        )
        assert result.exit_code == 0, result.output
        ml_client_patched.from_config.assert_called_once()
        ml_client = ml_client_patched.from_config()
        ml_client.jobs.create_or_update.assert_called_once()
        ml_client.compute.get.assert_called_once()

        default_credentials.assert_called_once()

        if not use_default_credentials:
            interactive_credentials.assert_called_once()
        else:
            interactive_credentials.assert_not_called()

        created_pipeline = ml_client.jobs.create_or_update.call_args[0][0]
        populated_env_vars = list(created_pipeline.jobs.values())[
            0
        ].environment_variables
        # Remove MLflow env vars for assertion (tested separately)
        for key in list(populated_env_vars.keys()):
            if key.startswith("KEDRO_AZUREML_MLFLOW_"):
                del populated_env_vars[key]
        expected_env = {"KEDRO_ENV": "base", **extra_env[1]}
        assert populated_env_vars == expected_env


@pytest.mark.parametrize(
    "on_job_scheduled_arg",
    (
        None,
        "tests.helpers.on_job_scheduled_helper:existing_function",
    ),
    ids=("no callback", "with callback"),
)
def test_can_invoke_submit_with_on_job_scheduled(
    patched_kedro_package,
    cli_context,
    dummy_pipeline,
    dummy_plugin_config,
    tmp_path: Path,
    on_job_scheduled_arg,
):
    from kedro_azureml.config import JobConfig, PipelineFilterOptions
    from kedro_azureml.manager import KedroContextManager

    create_kedro_conf_dirs(tmp_path)
    dummy_plugin_config.jobs = {
        "test_job": JobConfig(
            pipeline=PipelineFilterOptions(pipeline_name="__default__"),
        ),
    }

    mock_mgr = MagicMock(spec=KedroContextManager)
    mock_mgr.plugin_config = dummy_plugin_config
    mock_mgr.context.params = {}
    mock_mgr.context.catalog = MagicMock()
    mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

    with patch.dict(
        "kedro.framework.project.pipelines", {"__default__": dummy_pipeline}
    ), patch.object(Path, "cwd", return_value=tmp_path), patch(
        "kedro_azureml.client.MLClient"
    ), patch(
        "kedro_azureml.auth.utils.DefaultAzureCredential"
    ), patch.object(
        KedroContextManager, "__enter__", return_value=mock_mgr
    ), patch.object(
        KedroContextManager, "__exit__", return_value=False
    ), patch.object(
        AzureMLPipelineGenerator,
        "get_kedro_pipeline",
        return_value=dummy_pipeline,
    ), patch(
        "tests.helpers.on_job_scheduled_helper.existing_function"
    ) as mock_callback:
        runner = CliRunner()
        args = ["-j", "test_job", "--once"]
        if on_job_scheduled_arg:
            args += ["--on-job-scheduled", on_job_scheduled_arg]

        result = runner.invoke(cli.submit, args, obj=cli_context)
        assert result.exit_code == 0, result.output

        if on_job_scheduled_arg:
            mock_callback.assert_called_once()


@pytest.mark.parametrize(
    "on_job_scheduled_arg",
    (
        "invalid_format_no_colon",
        "nonexistent.module:func",
    ),
    ids=("bad format", "nonexistent module"),
)
def test_fail_if_invalid_on_job_scheduled_provided_in_submit(
    patched_kedro_package,
    cli_context,
    tmp_path: Path,
    on_job_scheduled_arg: str,
):
    create_kedro_conf_dirs(tmp_path)
    with patch.object(Path, "cwd", return_value=tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            cli.submit,
            ["-j", "any_job", "--on-job-scheduled", on_job_scheduled_arg],
            obj=cli_context,
        )
        assert result.exit_code != 0


@pytest.mark.parametrize(
    "kedro_environment_name",
    ("empty", "non_existing", "gitkeep", "nested"),
)
@pytest.mark.parametrize("confirm", (True, False))
def test_submit_is_interrupted_if_used_on_empty_env(
    confirm,
    patched_kedro_package,
    cli_context,
    dummy_pipeline,
    tmp_path: Path,
    kedro_environment_name: str,
):
    metadata = MagicMock()
    metadata.package_name = "tests"
    cli_context = CliContext(env=kedro_environment_name, metadata=metadata)

    create_kedro_conf_dirs(tmp_path)  # for base env

    # setup Kedro env to handle test case
    cfg_path = tmp_path / "conf" / kedro_environment_name
    if kedro_environment_name == "empty":
        cfg_path.mkdir(parents=True)
    elif kedro_environment_name == "gitkeep":
        cfg_path.mkdir(parents=True)
        (cfg_path / ".gitkeep").touch()
    elif kedro_environment_name == "nested":
        (cfg_path / "nested2").mkdir(parents=True)
    else:
        pass  # nothing to do for non_existing environment, do not remove this empty block

    with patch.dict(
        "kedro.framework.project.pipelines", {"__default__": dummy_pipeline}
    ), patch.object(Path, "cwd", return_value=tmp_path), patch.dict(
        os.environ, {}
    ), patch(
        "kedro_azureml.auth.utils.DefaultAzureCredential"
    ), patch(
        "click.confirm", return_value=confirm
    ) as click_confirm:
        runner = CliRunner()
        result = runner.invoke(
            cli.submit, ["-j", "any_job"], obj=cli_context
        )
        assert result.exit_code == (
            1 if confirm else 2
        ), "submit should have exited with code: 1 if confirmed, 2 if stopped"
        click_confirm.assert_called_once()


def test_can_invoke_submit_with_failed_pipeline(
    patched_kedro_package,
    cli_context,
    dummy_pipeline,
    dummy_plugin_config,
    tmp_path: Path,
):
    from kedro_azureml.config import JobConfig, PipelineFilterOptions
    from kedro_azureml.manager import KedroContextManager

    create_kedro_conf_dirs(tmp_path)
    dummy_plugin_config.jobs = {
        "test_job": JobConfig(
            pipeline=PipelineFilterOptions(pipeline_name="__default__"),
        ),
    }

    mock_mgr = MagicMock(spec=KedroContextManager)
    mock_mgr.plugin_config = dummy_plugin_config
    mock_mgr.context.params = {}
    mock_mgr.context.catalog = MagicMock()
    mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

    with patch.dict(
        "kedro.framework.project.pipelines", {"__default__": dummy_pipeline}
    ), patch.object(Path, "cwd", return_value=tmp_path), patch(
        "kedro_azureml.client.MLClient"
    ) as ml_client_patched, patch(
        "kedro_azureml.auth.utils.DefaultAzureCredential"
    ), patch.object(
        KedroContextManager, "__enter__", return_value=mock_mgr
    ), patch.object(
        KedroContextManager, "__exit__", return_value=False
    ), patch.object(
        AzureMLPipelineGenerator,
        "get_kedro_pipeline",
        return_value=dummy_pipeline,
    ):
        ml_client = ml_client_patched.from_config()
        ml_client.jobs.create_or_update.side_effect = ValueError("test failure")

        runner = CliRunner()
        result = runner.invoke(
            cli.commands,
            [
                "azureml",
                "-e",
                "base",
                "submit",
                "-j",
                "test_job",
                "--once",
            ],
            obj=ProjectMetadata(
                tmp_path,
                "tests",
                "project",
                tmp_path,
                "1.0",
                Path.cwd(),
                "0.18.5",
                example_pipeline="__default__",
            ),
        )
        assert result.exit_code == 1


@pytest.mark.parametrize("env_var", ("INVALID", "2+2=4"))
def test_fail_if_invalid_env_provided_in_submit(
    patched_kedro_package,
    cli_context,
    dummy_pipeline,
    tmp_path: Path,
    env_var: str,
):
    create_kedro_conf_dirs(tmp_path)
    with patch.dict(
        "kedro.framework.project.pipelines", {"__default__": dummy_pipeline}
    ), patch.object(Path, "cwd", return_value=tmp_path), patch(
        "kedro_azureml.client.MLClient"
    ) as ml_client_patched, patch(
        "kedro_azureml.auth.utils.DefaultAzureCredential"
    ):
        ml_client = ml_client_patched.from_config()
        ml_client.jobs.stream.side_effect = ValueError()

        runner = CliRunner()
        result = runner.invoke(
            cli.submit, ["-j", "any_job", "--env-var", env_var], obj=cli_context
        )
        assert result.exit_code == 1
        assert (
            str(result.exception)
            == f"Invalid env-var: {env_var}, expected format: KEY=VALUE"
        )
