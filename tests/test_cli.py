import os
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest
import yaml
from azure.identity import CredentialUnavailableError
from click.testing import CliRunner
from kedro.framework.project import pipelines
from kedro.framework.startup import ProjectMetadata

import kedro_azureml_pipeline.cli.commands as cli
from kedro_azureml_pipeline.config import KedroAzureMLConfig
from kedro_azureml_pipeline.generator import AzureMLPipelineGenerator
from kedro_azureml_pipeline.runner import AzurePipelinesRunner
from kedro_azureml_pipeline.utils import CliContext
from tests.utils import create_kedro_conf_dirs


class TestInit:
    """Tests for the ``kedro azureml init`` CLI command."""

    def test_creates_valid_config(self, patched_kedro_package, cli_context, tmp_path: Path):
        config_path = create_kedro_conf_dirs(tmp_path)
        with patch.object(Path, "cwd", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli.init, [], obj=cli_context)

            assert result.exit_code == 0, result.exception

            azureml_config_path = config_path / "azureml.yml"
            assert azureml_config_path.exists() and azureml_config_path.is_file(), (
                f"{azureml_config_path.absolute()} is not a valid file"
            )

            config: KedroAzureMLConfig = KedroAzureMLConfig.model_validate(
                yaml.safe_load(azureml_config_path.read_text())
            )
            assert config.workspace.resolve().subscription_id == "<subscription_id>"
            assert config.workspace.resolve().resource_group == "<resource_group>"
            assert config.workspace.resolve().name == "<workspace_name>"
            assert config.compute.root["__default__"].cluster_name == "<cluster_name>"
            assert config.execution.environment == "<environment>"

    def test_creates_amlignore_when_missing(self, patched_kedro_package, cli_context, tmp_path: Path):
        """When ``.amlignore`` does not exist, ``init`` creates an empty one."""
        create_kedro_conf_dirs(tmp_path)
        with patch.object(Path, "cwd", return_value=tmp_path):
            aml_ignore = tmp_path / ".amlignore"
            assert not aml_ignore.exists()

            runner = CliRunner()
            result = runner.invoke(cli.init, [], obj=cli_context)

            assert result.exit_code == 0, result.exception
            assert aml_ignore.exists()
            assert aml_ignore.read_text() == ""

    def test_warns_when_amlignore_exists(self, patched_kedro_package, cli_context, tmp_path: Path):
        """When ``.amlignore`` already exists, ``init`` warns but does not overwrite."""
        create_kedro_conf_dirs(tmp_path)
        aml_ignore = tmp_path / ".amlignore"
        aml_ignore.write_text("*.pyc")
        with patch.object(Path, "cwd", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli.init, [], obj=cli_context)

            assert result.exit_code == 0, result.exception
            assert ".amlignore file already exist" in result.output
            assert aml_ignore.read_text() == "*.pyc"


class TestCompile:
    """Tests for the ``kedro azureml compile`` CLI command."""

    @pytest.mark.parametrize(
        "runtime_params",
        ("", '{"unit_test_param": 666.0}'),
        ids=("without params", "with runtime params"),
    )
    def test_compile_pipeline(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
        runtime_params,
    ):
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

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

        with (
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            _ = create_kedro_conf_dirs(tmp_path)
            runner = CliRunner()
            output_path = tmp_path / "pipeline.yml"

            result = runner.invoke(
                cli.compile,
                [
                    "-j",
                    "test_job",
                    "--output",
                    str(output_path.absolute()),
                    "--params",
                    runtime_params,
                ],
                obj=cli_context,
            )
            assert result.exit_code == 0, result.output
            assert isinstance(p := yaml.safe_load(output_path.read_text()), dict) and all(
                k in p for k in ("display_name", "type", "jobs")
            )

    def test_compile_all_check_compiles_without_writing(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """``compile --all --check`` compiles every job in memory and writes nothing."""
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        dummy_plugin_config.jobs = {
            "test_job": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__")),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = MagicMock()
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            create_kedro_conf_dirs(tmp_path)
            runner = CliRunner()
            result = runner.invoke(cli.compile, ["--all", "--check"], obj=cli_context)

            assert result.exit_code == 0, result.output
            assert "compiled successfully" in result.output
            assert not (tmp_path / "pipeline.yaml").exists()

    def test_compile_requires_job_or_all(
        self,
        patched_kedro_package,
        cli_context,
    ):
        """``compile`` with neither -j nor --all is a usage error."""
        runner = CliRunner()
        result = runner.invoke(cli.compile, [], obj=cli_context)
        assert result.exit_code != 0
        assert "Provide -j/--job name(s) or --all." in result.output

    def test_compile_all_and_job_mutually_exclusive(
        self,
        patched_kedro_package,
        cli_context,
    ):
        """``compile --all`` combined with ``-j`` is a usage error."""
        runner = CliRunner()
        result = runner.invoke(cli.compile, ["--all", "-j", "test_job"], obj=cli_context)
        assert result.exit_code != 0
        assert "--all and -j/--job are mutually exclusive." in result.output

    def test_compile_check_reports_failures(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """``compile --check`` records a failing job and exits non-zero at the end."""
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        dummy_plugin_config.jobs = {
            "test_job": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__")),
        }

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = MagicMock()
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
            patch.object(AzureMLPipelineGenerator, "generate", side_effect=RuntimeError("boom")),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            create_kedro_conf_dirs(tmp_path)
            runner = CliRunner()
            result = runner.invoke(cli.compile, ["--check", "-j", "test_job"], obj=cli_context)

            assert result.exit_code != 0
            assert "failed to compile" in result.output
            assert "1 job(s) failed to compile" in result.output

    def test_compile_no_jobs_errors(
        self,
        patched_kedro_package,
        cli_context,
        tmp_path: Path,
    ):
        """Compiling when no jobs section exists should error."""
        from kedro_azureml_pipeline.manager import KedroContextManager

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = MagicMock()
        mock_mgr.plugin_config.jobs = {}

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            create_kedro_conf_dirs(tmp_path)
            runner = CliRunner()
            result = runner.invoke(
                cli.compile,
                ["-j", "nonexistent", "--output", str(tmp_path / "out.yml")],
                obj=cli_context,
            )
            assert result.exit_code != 0
            assert "No 'jobs' section" in result.output

    def test_compile_missing_job_name_errors(
        self,
        patched_kedro_package,
        cli_context,
        tmp_path: Path,
    ):
        """Compiling with a non-existent job name should error."""
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = MagicMock()
        mock_mgr.plugin_config.jobs = {
            "real_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
            ),
        }

        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            create_kedro_conf_dirs(tmp_path)
            runner = CliRunner()
            result = runner.invoke(
                cli.compile,
                ["-j", "ghost_job", "--output", str(tmp_path / "out.yml")],
                obj=cli_context,
            )
            assert result.exit_code != 0
            assert "not found" in result.output


class TestExecute:
    """Tests for the ``kedro azureml execute`` CLI command."""

    def test_invoke_execute(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        def load_registry():
            # kedro < 1.7 reads `_content` after loading, kedro >= 1.7 the return value
            pipelines._content = {"__default__": dummy_pipeline}
            return pipelines._content

        patched_azure_runner = AzurePipelinesRunner(data_paths={})
        create_kedro_conf_dirs(tmp_path)
        with (
            patch("kedro_azureml_pipeline.runner.AzurePipelinesRunner", new=patched_azure_runner),
            # Patch the loader, not the contents: kedro >= 1.7 empties the registry when
            # `session.run` narrows it to the requested pipeline, dropping a `patch.dict`.
            patch.object(pipelines, "_content", {}),
            patch.object(pipelines, "_load_data", side_effect=load_registry),
            patch(
                "kedro_azureml_pipeline.manager.KedroContextManager.plugin_config",
                new_callable=mock.PropertyMock,
                return_value=dummy_plugin_config,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli.execute,
                ["--node", "node1", "--az-output", "i2", str(tmp_path)],
                obj=cli_context,
            )
            assert result.exit_code == 0

    def test_execute_uses_the_supported_run_parameter(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """`pipeline_name` is deprecated; passing it logged a notice in every step.

        Asserted on the call rather than on the absence of a log line, so this
        still means something once Kedro removes the parameter and stops warning.
        """
        patched_azure_runner = AzurePipelinesRunner(data_paths={})
        create_kedro_conf_dirs(tmp_path)
        with (
            patch("kedro_azureml_pipeline.runner.AzurePipelinesRunner", new=patched_azure_runner),
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch(
                "kedro_azureml_pipeline.manager.KedroContextManager.plugin_config",
                new_callable=mock.PropertyMock,
                return_value=dummy_plugin_config,
            ),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch("kedro.framework.session.KedroSession.run") as mock_run,
        ):
            runner = CliRunner()
            runner.invoke(
                cli.execute,
                ["--node", "node1", "--az-output", "i2", str(tmp_path)],
                obj=cli_context,
            )

        assert mock_run.called, "the execute command did not run the session"
        assert mock_run.call_args.args == (), "the pipeline was passed positionally, which is `pipeline_name`"
        assert mock_run.call_args.kwargs["pipeline_names"] == ["__default__"]


class TestRun:
    """Tests for the ``kedro azureml run`` CLI command."""

    @staticmethod
    def _run_submit(
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path,
        *,
        aml_env="",
        use_default_credentials=True,
        amlignore="missing",
        gitignore="missing",
        extra_env=([], {}),
        wait_for_completion=False,
        workspace_name=None,
        extra_cli_args=(),
    ):
        """Invoke ``kedro azureml run`` with the given option overrides.

        Returns ``(result, ml_client_patched, default_credentials, interactive_credentials)``.
        """
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

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

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch("kedro_azureml_pipeline.client.MLClient") as ml_client_patched,
            patch("kedro_azureml_pipeline.client.DefaultAzureCredential") as default_credentials,
            patch("kedro_azureml_pipeline.client.InteractiveBrowserCredential") as interactive_credentials,
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=dummy_pipeline,
            ),
        ):
            if not use_default_credentials:
                default_credentials.side_effect = CredentialUnavailableError(message="Test: no default credentials")

            if amlignore != "missing":
                Path.cwd().joinpath(".amlignore").write_text("" if amlignore == "empty" else "unittest")

            if gitignore != "missing":
                Path.cwd().joinpath(".gitignore").write_text("" if gitignore == "empty" else "unittest")

            runner = CliRunner()
            result = runner.invoke(
                cli.run,
                ["-j", "test_job"]
                + (["--aml-env", aml_env] if aml_env else [])
                + (["--wait-for-completion"] if wait_for_completion else [])
                + (sum([["--env-var", k] for k in extra_env[0]], []))
                + (["--workspace", workspace_name] if workspace_name else [])
                + list(extra_cli_args),
                obj=cli_context,
            )
            return result, ml_client_patched, default_credentials, interactive_credentials

    def test_successful_submit(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """Basic happy-path: job is submitted and Azure ML APIs are called."""
        result, ml_client_patched, default_credentials, _ = self._run_submit(
            patched_kedro_package,
            cli_context,
            dummy_pipeline,
            dummy_plugin_config,
            tmp_path,
        )
        assert result.exit_code == 0, result.output
        ml_client_patched.assert_called_once()
        ml_client = ml_client_patched.return_value
        ml_client.jobs.create_or_update.assert_called_once()
        ml_client.compute.get.assert_called_once()
        default_credentials.assert_called_once()

    def test_aml_env_override(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """``--aml-env`` flag is accepted and the job succeeds."""
        result, ml_client_patched, _, _ = self._run_submit(
            patched_kedro_package,
            cli_context,
            dummy_pipeline,
            dummy_plugin_config,
            tmp_path,
            aml_env="unit_test_aml_env@latest",
        )
        assert result.exit_code == 0, result.output
        ml_client_patched.return_value.jobs.create_or_update.assert_called_once()

    @pytest.mark.parametrize(
        "use_default_credentials",
        (False, True),
        ids=("interactive credentials", "default credentials"),
    )
    def test_credential_fallback(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
        use_default_credentials: bool,
    ):
        """Credential resolution falls back to interactive when default fails."""
        result, _, default_credentials, interactive_credentials = self._run_submit(
            patched_kedro_package,
            cli_context,
            dummy_pipeline,
            dummy_plugin_config,
            tmp_path,
            use_default_credentials=use_default_credentials,
        )
        assert result.exit_code == 0, result.output
        default_credentials.assert_called_once()
        if not use_default_credentials:
            interactive_credentials.assert_called_once()
        else:
            interactive_credentials.assert_not_called()

    @pytest.mark.parametrize(
        "amlignore,gitignore",
        [
            pytest.param("filled", "missing", id="amlignore-filled"),
            pytest.param("empty", "missing", id="amlignore-empty"),
            pytest.param("missing", "filled", id="gitignore-filled"),
            pytest.param("missing", "empty", id="gitignore-empty"),
            pytest.param("missing", "missing", id="no-ignore-files"),
        ],
    )
    def test_ignore_file_variants(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
        amlignore: str,
        gitignore: str,
    ):
        """Various ignore-file states do not prevent job submission."""
        result, _, _, _ = self._run_submit(
            patched_kedro_package,
            cli_context,
            dummy_pipeline,
            dummy_plugin_config,
            tmp_path,
            amlignore=amlignore,
            gitignore=gitignore,
        )
        assert result.exit_code == 0, result.output

    @pytest.mark.parametrize(
        "extra_env",
        [
            pytest.param(([], {}), id="no-extra-env"),
            pytest.param((["A=B", "C="], {"A": "B", "C": ""}), id="multi-env-vars"),
            pytest.param((["A=CDE=F123"], {"A": "CDE=F123"}), id="value-with-equals"),
        ],
    )
    def test_extra_env_vars_propagated(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
        extra_env,
    ):
        """Extra ``--env-var`` entries appear in the generated pipeline node."""
        result, ml_client_patched, _, _ = self._run_submit(
            patched_kedro_package,
            cli_context,
            dummy_pipeline,
            dummy_plugin_config,
            tmp_path,
            extra_env=extra_env,
        )
        assert result.exit_code == 0, result.output
        ml_client = ml_client_patched.return_value
        created_pipeline = ml_client.jobs.create_or_update.call_args[0][0]
        populated_env_vars = list(created_pipeline.jobs.values())[0].environment_variables
        for key in list(populated_env_vars.keys()):
            if key.startswith("KEDRO_AZUREML_MLFLOW_"):
                del populated_env_vars[key]
        expected_env = {"KEDRO_ENV": "base", **extra_env[1]}
        assert populated_env_vars == expected_env

    @pytest.mark.parametrize(
        "wait_for_completion",
        (False, True),
        ids=("fire and forget", "wait for completion"),
    )
    def test_wait_for_completion_flag(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
        wait_for_completion: bool,
    ):
        """``--wait-for-completion`` flag is accepted."""
        result, _, _, _ = self._run_submit(
            patched_kedro_package,
            cli_context,
            dummy_pipeline,
            dummy_plugin_config,
            tmp_path,
            wait_for_completion=wait_for_completion,
        )
        assert result.exit_code == 0, result.output

    @pytest.mark.parametrize(
        "on_job_scheduled_arg",
        (
            None,
            "tests.helpers.on_job_scheduled_helper:existing_function",
        ),
        ids=("no callback", "with callback"),
    )
    def test_on_job_scheduled_callback(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
        on_job_scheduled_arg,
    ):
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

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

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=dummy_pipeline,
            ),
            patch("tests.helpers.on_job_scheduled_helper.existing_function") as mock_callback,
        ):
            runner = CliRunner()
            args = ["-j", "test_job"]
            if on_job_scheduled_arg:
                args += ["--on-job-scheduled", on_job_scheduled_arg]

            result = runner.invoke(cli.run, args, obj=cli_context)
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
    def test_invalid_on_job_scheduled_rejected(
        self,
        patched_kedro_package,
        cli_context,
        tmp_path: Path,
        on_job_scheduled_arg: str,
    ):
        create_kedro_conf_dirs(tmp_path)
        with patch.object(Path, "cwd", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(
                cli.run,
                ["-j", "any_job", "--on-job-scheduled", on_job_scheduled_arg],
                obj=cli_context,
            )
            assert result.exit_code != 0

    @pytest.mark.parametrize(
        "kedro_environment_name",
        ("empty", "non_existing", "gitkeep", "nested"),
    )
    @pytest.mark.parametrize("confirm", (True, False))
    def test_interrupted_on_empty_env(
        self,
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

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.dict(os.environ, {}),
            patch("click.confirm", return_value=confirm) as click_confirm,
        ):
            runner = CliRunner()
            result = runner.invoke(cli.run, ["-j", "any_job"], obj=cli_context)
            assert result.exit_code == (1 if confirm else 2), (
                "run should have exited with code: 1 if confirmed, 2 if stopped"
            )
            click_confirm.assert_called_once()

    def test_failed_pipeline_exits_with_error(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

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

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch("kedro_azureml_pipeline.client.MLClient") as ml_client_patched,
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(
                AzureMLPipelineGenerator,
                "get_kedro_pipeline",
                return_value=dummy_pipeline,
            ),
        ):
            ml_client = ml_client_patched.return_value
            ml_client.jobs.create_or_update.side_effect = ValueError("test failure")

            runner = CliRunner()
            result = runner.invoke(
                cli.commands,
                [
                    "azureml",
                    "-e",
                    "base",
                    "run",
                    "-j",
                    "test_job",
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
    def test_invalid_env_var_rejected(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        tmp_path: Path,
        env_var: str,
    ):
        create_kedro_conf_dirs(tmp_path)
        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch("kedro_azureml_pipeline.client.MLClient") as ml_client_patched,
        ):
            ml_client = ml_client_patched.return_value
            ml_client.jobs.stream.side_effect = ValueError()

            runner = CliRunner()
            result = runner.invoke(cli.run, ["-j", "any_job", "--env-var", env_var], obj=cli_context)
            assert result.exit_code == 1
            assert str(result.exception) == f"Invalid env-var: {env_var}, expected format: KEY=VALUE"

    def test_workspace_override_echo(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """``--workspace`` flag echoes the override message."""
        result, _, _, _ = self._run_submit(
            patched_kedro_package,
            cli_context,
            dummy_pipeline,
            dummy_plugin_config,
            tmp_path,
            workspace_name="__default__",
            extra_cli_args=("--dry-run",),
        )
        assert result.exit_code == 0, result.output
        assert "Overriding workspace to: __default__" in result.output

    def test_run_missing_job_name_errors(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """Requesting a non-existent job name should error."""
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)
        dummy_plugin_config.jobs = {
            "real_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
            ),
        }
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = MagicMock()
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
        ):
            runner = CliRunner()
            result = runner.invoke(cli.run, ["-j", "nonexistent"], obj=cli_context)
            assert result.exit_code != 0
            assert "not found" in result.output

    def test_run_job_exception_reports_failure(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """When ``az_client.run()`` raises, the job is marked as failed."""
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

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

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch("kedro_azureml_pipeline.client.MLClient") as ml_client_patched,
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
        ):
            ml_client = ml_client_patched.return_value
            ml_client.jobs.create_or_update.side_effect = RuntimeError("connection lost")

            runner = CliRunner()
            result = runner.invoke(cli.run, ["-j", "test_job"], obj=cli_context)
            assert result.exit_code == 1
            assert "Failed to run job" in result.output
            assert "0 succeeded" in result.output

    def test_run_job_returns_false_reports_failure(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """When ``az_client.run()`` returns False, the job is marked failed."""
        from kedro_azureml_pipeline.client import AzureMLPipelinesClient
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

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

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
            patch.object(AzureMLPipelinesClient, "run", return_value=False),
        ):
            runner = CliRunner()
            result = runner.invoke(cli.run, ["-j", "test_job"], obj=cli_context)
            assert result.exit_code == 1
            assert "0 succeeded" in result.output

    def test_run_aborts_remaining_jobs_after_failure(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """A failed job aborts the batch: later jobs are skipped, not submitted."""
        from kedro_azureml_pipeline.client import AzureMLPipelinesClient
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)
        dummy_plugin_config.jobs = {
            "job_a": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__")),
            "job_b": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__")),
        }
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = MagicMock()
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
            patch.object(AzureMLPipelinesClient, "run", return_value=False) as run_patched,
        ):
            runner = CliRunner()
            result = runner.invoke(cli.run, ["-j", "job_a", "-j", "job_b"], obj=cli_context)
            assert result.exit_code == 1
            # Only the first job is submitted; the second is skipped after the failure.
            assert run_patched.call_count == 1
            assert "skipping 1 remaining job(s): job_b" in result.output
            assert "1 skipped" in result.output

    def test_run_aborts_after_middle_failure_in_batch(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """In a 3-job batch, a mid-batch failure submits the prefix and skips the rest."""
        from kedro_azureml_pipeline.client import AzureMLPipelinesClient
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)
        dummy_plugin_config.jobs = {
            "job_a": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__")),
            "job_b": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__")),
            "job_c": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__")),
        }
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = MagicMock()
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
            # job_a succeeds, job_b fails; job_c must never be submitted.
            patch.object(AzureMLPipelinesClient, "run", side_effect=[True, False]) as run_patched,
        ):
            runner = CliRunner()
            result = runner.invoke(cli.run, ["-j", "job_a", "-j", "job_b", "-j", "job_c"], obj=cli_context)
            assert result.exit_code == 1
            assert run_patched.call_count == 2
            assert "skipping 1 remaining job(s): job_c" in result.output
            assert "1 succeeded, 1 failed, 1 skipped" in result.output

    def test_run_last_job_failure_does_not_abort(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """When the failing job is last, every job is submitted and no abort notice is printed."""
        from kedro_azureml_pipeline.client import AzureMLPipelinesClient
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)
        dummy_plugin_config.jobs = {
            "job_a": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__")),
            "job_b": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="__default__")),
        }
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = MagicMock()
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
            # job_a succeeds, job_b (last) fails: nothing left to skip.
            patch.object(AzureMLPipelinesClient, "run", side_effect=[True, False]) as run_patched,
        ):
            runner = CliRunner()
            result = runner.invoke(cli.run, ["-j", "job_a", "-j", "job_b"], obj=cli_context)
            assert result.exit_code == 1
            assert run_patched.call_count == 2
            assert "Aborting batch" not in result.output
            assert "skipped" not in result.output
            assert "1 succeeded, 1 failed" in result.output

    def test_run_display_name_assignment(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """When a job has ``display_name``, it is set on the generated pipeline job."""
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)
        dummy_plugin_config.jobs = {
            "test_job": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                display_name="My Custom Name",
            ),
        }
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = MagicMock()
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch("kedro_azureml_pipeline.client.MLClient") as ml_client_patched,
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
        ):
            ml_client = ml_client_patched.return_value
            ml_client.compute.get.return_value = MagicMock(
                name="cpu-cluster", size="Standard_DS3_v2", min_instances=0, max_instances=4
            )
            runner = CliRunner()
            result = runner.invoke(cli.run, ["-j", "test_job"], obj=cli_context)
            assert result.exit_code == 0, result.output

            # The created pipeline job should have the display_name
            job_arg = ml_client.jobs.create_or_update.call_args[0][0]
            assert job_arg.display_name == "My Custom Name"

    def test_run_all_jobs_when_no_filter(
        self,
        patched_kedro_package,
        cli_context,
        dummy_pipeline,
        dummy_plugin_config,
        tmp_path: Path,
    ):
        """When ``job_names`` is empty, all configured jobs run (covers job_names=[] branch)."""
        from kedro_azureml_pipeline.cli.functions import run_jobs
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        create_kedro_conf_dirs(tmp_path)
        dummy_plugin_config.jobs = {
            "job_a": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
            ),
            "job_b": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
            ),
        }
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        mock_mgr.context.params = {}
        mock_mgr.context.catalog = MagicMock()
        mock_mgr.context.config_loader.__getitem__ = MagicMock(side_effect=KeyError("mlflow"))

        with (
            patch.dict("kedro.framework.project.pipelines", {"__default__": dummy_pipeline}),
            patch.object(Path, "cwd", return_value=tmp_path),
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline),
        ):
            result = run_jobs(
                ctx=cli_context,
                aml_env=None,
                params="",
                extra_env={},
                load_versions={},
                job_names=None,
                dry_run=True,
            )
            assert result is True


class TestPatterns:
    """Tests for ``kedro azureml resolve-patterns`` and ``list-patterns``."""

    def _mgr(self, dummy_plugin_config):
        from kedro_azureml_pipeline.config import JobConfig, PipelineFilterOptions
        from kedro_azureml_pipeline.manager import KedroContextManager

        dummy_plugin_config.jobs = {
            "{product}-{group}-{variant}-inference": JobConfig(
                pipeline=PipelineFilterOptions(
                    pipeline_name="inference", node_namespaces=["{product}.{group}.{variant}"]
                ),
                schedule="da-vintages",
            ),
            "snapshot": JobConfig(pipeline=PipelineFilterOptions(pipeline_name="snapshot")),
        }
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        return mock_mgr, KedroContextManager

    def _fake_pipelines(self):
        from types import SimpleNamespace

        node = SimpleNamespace(namespace="da_energy.hub.champion")
        return {"inference": SimpleNamespace(nodes=[node])}

    def test_resolve_patterns_lists_derived_and_literal_jobs(
        self, patched_kedro_package, cli_context, dummy_plugin_config
    ):
        mock_mgr, KedroContextManager = self._mgr(dummy_plugin_config)
        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch("kedro.framework.project.pipelines", self._fake_pipelines()),
        ):
            result = CliRunner().invoke(cli.resolve_patterns_command, [], obj=cli_context)
        assert result.exit_code == 0, result.output
        assert "da_energy-hub-champion-inference" in result.output  # derived
        assert "snapshot" in result.output  # literal included

    def test_resolve_patterns_formats_schedules(self, patched_kedro_package, cli_context, dummy_plugin_config):
        """A list schedule renders as a compact summary (named ref, cron, recurrence)."""
        from kedro_azureml_pipeline.config import (
            CronScheduleConfig,
            JobConfig,
            PipelineFilterOptions,
            RecurrenceScheduleConfig,
            ScheduleConfig,
        )
        from kedro_azureml_pipeline.manager import KedroContextManager

        dummy_plugin_config.jobs = {
            "multi": JobConfig(
                pipeline=PipelineFilterOptions(pipeline_name="__default__"),
                schedule=[
                    "da-vintages",
                    ScheduleConfig(cron=CronScheduleConfig(expression="30 9 * * *")),
                    ScheduleConfig(recurrence=RecurrenceScheduleConfig(frequency="day", interval=1)),
                ],
            ),
        }
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch("kedro.framework.project.pipelines", {}),
        ):
            result = CliRunner().invoke(cli.resolve_patterns_command, [], obj=cli_context)
        assert result.exit_code == 0, result.output
        assert "schedule=da-vintages, cron:30 9 * * *, recurrence:every 1 day(s)" in result.output

    def test_list_patterns_lists_factory_keys_only(self, patched_kedro_package, cli_context, dummy_plugin_config):
        mock_mgr, KedroContextManager = self._mgr(dummy_plugin_config)
        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
        ):
            result = CliRunner().invoke(cli.list_patterns_command, [], obj=cli_context)
        assert result.exit_code == 0, result.output
        assert "{product}-{group}-{variant}-inference" in result.output
        assert "snapshot" not in result.output  # literal jobs are not patterns

    def test_resolve_patterns_empty(self, patched_kedro_package, cli_context, dummy_plugin_config):
        from kedro_azureml_pipeline.manager import KedroContextManager

        dummy_plugin_config.jobs = {}
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
            patch("kedro.framework.project.pipelines", {}),
        ):
            result = CliRunner().invoke(cli.resolve_patterns_command, [], obj=cli_context)
        assert result.exit_code == 0, result.output
        assert "No jobs resolved" in result.output

    def test_list_patterns_empty(self, patched_kedro_package, cli_context, dummy_plugin_config):
        from kedro_azureml_pipeline.manager import KedroContextManager

        dummy_plugin_config.jobs = {}
        mock_mgr = MagicMock(spec=KedroContextManager)
        mock_mgr.plugin_config = dummy_plugin_config
        with (
            patch.object(KedroContextManager, "__enter__", return_value=mock_mgr),
            patch.object(KedroContextManager, "__exit__", return_value=False),
        ):
            result = CliRunner().invoke(cli.list_patterns_command, [], obj=cli_context)
        assert result.exit_code == 0, result.output
        assert "No job factory patterns" in result.output
