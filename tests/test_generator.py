import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from azure.ai.ml.entities import Environment, Job
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from kedro.pipeline import node, pipeline

from kedro_azureml_pipeline.config import ClusterConfig, LimitsConfig, NotificationConfig
from kedro_azureml_pipeline.constants import (
    KEDRO_AZUREML_MLFLOW_ENABLED,
    KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME,
    KEDRO_AZUREML_MLFLOW_NODE_NAME,
    KEDRO_AZUREML_MLFLOW_RUN_NAME,
    KEDRO_AZUREML_NOTIFY,
    KEDRO_AZUREML_NOTIFY_OUTCOME,
    KEDRO_AZUREML_NOTIFY_SIBLINGS,
    KEDRO_AZUREML_NOTIFY_START,
)
from kedro_azureml_pipeline.generator import (
    EXIT_CLASSIFICATION_SUFFIX,
    AzureMLPipelineGenerator,
    ConfigException,
    NotificationRoles,
)
from tests.utils import identity


class TestPipelineGeneration:
    """Core pipeline generation and Kedro integration."""

    @pytest.mark.parametrize(
        "pipeline_fixture",
        ["dummy_pipeline", "dummy_pipeline_compute_tag"],
    )
    def test_can_generate_azure_pipeline(
        self,
        pipeline_fixture,
        dummy_plugin_config,
        multi_catalog,
        request,
    ):
        pipeline = request.getfixturevalue(pipeline_fixture)
        aml_env = "unit_test/aml_env@latest"
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=pipeline):
            env_name = "unit_test_env"
            generator = AzureMLPipelineGenerator(
                pipeline_fixture,
                env_name,
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env=aml_env,
            )

            az_pipeline = generator.generate()
            assert isinstance(az_pipeline, Job) and az_pipeline.display_name == pipeline_fixture, (
                "Invalid basic pipeline data"
            )
            assert all(f"kedro azureml -e {env_name} execute" in node.command for node in az_pipeline.jobs.values()), (
                "Commands seems invalid"
            )

            assert all(node.environment == aml_env for node in az_pipeline.jobs.values()), (
                "Invalid Azure ML Environment name set on commands"
            )

    def test_can_get_pipeline_from_kedro(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        pipeline_name = "unit_test_pipeline"
        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(pipeline_name, "local", dummy_plugin_config, {}, catalog=multi_catalog)
            p = generator.get_kedro_pipeline()
            assert p == dummy_pipeline

    def test_deterministic_node_tag(self, dummy_pipeline_deterministic_tag, dummy_plugin_config, multi_catalog):
        """Nodes tagged 'deterministic' propagate the flag to the generated Azure pipeline."""
        with patch.object(
            AzureMLPipelineGenerator,
            "get_kedro_pipeline",
            return_value=dummy_pipeline_deterministic_tag,
        ):
            generator = AzureMLPipelineGenerator(
                "dummy_pipeline_deterministic_tag",
                "unit_test_env",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="unit_test/aml_env@latest",
            )

            az_pipeline = generator.generate()
            for node in dummy_pipeline_deterministic_tag.nodes:
                assert az_pipeline.jobs[node.name].component.is_deterministic == ("deterministic" in node.tags), (
                    "is_deterministic property does not match node tag"
                )


#: The suffix-execution tests need a POSIX shell. On Windows runners ``bash``
#: resolves to the WSL stub, which exits 1 for every invocation; the generated
#: command only ever runs in Azure ML Linux containers, so there is nothing to
#: exercise there.
requires_posix_shell = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the generated command runs in Azure ML Linux containers; Windows has no POSIX shell to run it with",
)


class TestExitClassification:
    """A step that dies of a signal names it in stderr instead of a bare exit code.

    Azure ML reports a signal death as a nonzero exit with no signal name, so the
    failure page cannot distinguish a native crash from an ordinary exception.
    The classification runs in the shell because nothing inside the Python
    process survives a SIGSEGV or SIGKILL to report it.
    """

    def test_every_command_carries_the_suffix(self, dummy_pipeline, dummy_plugin_config, multi_catalog):
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline):
            generator = AzureMLPipelineGenerator(
                "dummy_pipeline",
                "unit_test_env",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="unit_test/aml_env@latest",
            )
            az_pipeline = generator.generate()

        for job in az_pipeline.jobs.values():
            assert job.command.endswith(EXIT_CLASSIFICATION_SUFFIX)

    @requires_posix_shell
    def test_a_segfault_is_named_in_stderr(self):
        proc = subprocess.run(
            ["bash", "-c", "sh -c 'kill -SEGV $$'" + EXIT_CLASSIFICATION_SUFFIX],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 128 + 11
        assert "killed by signal 11 (SIGSEGV)" in proc.stderr

    @requires_posix_shell
    def test_a_clean_exit_adds_nothing(self):
        proc = subprocess.run(
            ["bash", "-c", "true" + EXIT_CLASSIFICATION_SUFFIX],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0
        assert proc.stderr == ""

    @requires_posix_shell
    def test_an_ordinary_failure_keeps_its_code_unclassified(self):
        """A Python exception exits with a small code and its own traceback; the
        suffix must neither relabel it nor swallow the code."""
        proc = subprocess.run(
            ["bash", "-c", "sh -c 'exit 3'" + EXIT_CLASSIFICATION_SUFFIX],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 3
        assert proc.stderr == ""


class TestComputeResources:
    """Compute-tag routing and multi-compute error handling."""

    def test_different_compute_per_node(self, dummy_pipeline_compute_tag, dummy_plugin_config, multi_catalog):
        """A node tagged with a compute tag is routed to the matching cluster."""
        dummy_plugin_config.compute.root["compute-2"] = ClusterConfig(cluster_name="cpu-cluster-2")
        with patch.object(
            AzureMLPipelineGenerator,
            "get_kedro_pipeline",
            return_value=dummy_pipeline_compute_tag,
        ):
            generator = AzureMLPipelineGenerator(
                "dummy_pipeline_compute_tag",
                "unit_test_env",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="unit_test/aml_env@latest",
            )

            az_pipeline = generator.generate()
            for node in dummy_pipeline_compute_tag.nodes:
                if node.tags:
                    assert all(
                        dummy_plugin_config.compute.root[tag].cluster_name == az_pipeline.jobs[node.name]["compute"]
                        for tag in node.tags
                    ), "compute settings don't match"

    def test_instance_type_reaches_every_step_and_the_payload(
        self, dummy_pipeline_compute_tag, dummy_plugin_config, multi_catalog
    ):
        """A configured instance type reaches each routed step's serialized payload.

        Asserting a Python attribute alone would pass whether or not the SDK
        recognises the field, so this asserts the value in the REST payload and
        that validation reports no ``Unknown field`` warning for it.
        """
        dummy_plugin_config.compute.root["__default__"].instance_type = "cpu-small"
        dummy_plugin_config.compute.root["compute-2"] = ClusterConfig(instance_type="gpu-large")
        with patch.object(
            AzureMLPipelineGenerator,
            "get_kedro_pipeline",
            return_value=dummy_pipeline_compute_tag,
        ):
            generator = AzureMLPipelineGenerator(
                "dummy_pipeline_compute_tag",
                "unit_test_env",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="unit_test/aml_env@latest",
            )
            az_pipeline = generator.generate()

            az_pipeline.settings.default_compute = "cpu"
            validation = az_pipeline._validate()
            warnings = [str(w) for w in (validation._warnings or [])]
            assert not any("instance_type" in w for w in warnings), warnings

            payload = az_pipeline._to_rest_object().as_dict()
            jobs = payload["properties"]["jobs"]
            assert jobs["node1"]["resources"]["instance_type"] == "gpu-large", jobs["node1"]
            for name in ("node2", "node3"):
                assert jobs[name]["resources"]["instance_type"] == "cpu-small", jobs[name]

    def test_no_instance_type_by_default(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        """Without instance_type, no step payload carries one (current-behavior guard)."""
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline):
            generator = AzureMLPipelineGenerator(
                "test_no_instance_type",
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="test@latest",
            )
            az_pipeline = generator.generate()

            payload = az_pipeline._to_rest_object().as_dict()
            for job_node in payload["properties"]["jobs"].values():
                assert "instance_type" not in (job_node.get("resources") or {}), job_node

    def test_multiple_compute_tags_raises(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        """A node with more than one compute tag causes a ConfigException."""
        pipeline_name = "unit_test_pipeline"
        node = MagicMock()
        node.tags = ["compute-2", "compute-3"]
        for t in node.tags:
            dummy_plugin_config.compute.root[t] = ClusterConfig(cluster_name=t)
        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(pipeline_name, "local", dummy_plugin_config, {}, catalog=multi_catalog)
            with pytest.raises(ConfigException):
                generator.get_target_resource_from_node_tags(node)


class TestEnvironmentVariables:
    """Custom and auto-injected environment variables on generated nodes."""

    def test_custom_env_vars_propagated(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        pipeline_name = "unit_test_pipeline"
        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(
                pipeline_name,
                "local",
                dummy_plugin_config,
                {},
                extra_env={"ABC": "def"},
                catalog=multi_catalog,
            )

            for node in generator.generate().jobs.values():
                assert node.environment_variables["ABC"] == "def"

    def test_no_retry_settings_on_any_step(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        """Command steps carry no retry settings, and the SDK accepts the result.

        Azure ML honours ``retry_settings`` on parallel and sweep jobs, not on the
        command steps this plugin emits. Asserting only that the attribute is absent
        would pass even if it were reintroduced under another name, so this also
        asserts the SDK raises no ``Unknown field`` warning for the generated job.
        """
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline):
            generator = AzureMLPipelineGenerator(
                "test_no_retry",
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="test@latest",
            )
            az_pipeline = generator.generate()

            for step in az_pipeline.jobs.values():
                assert not getattr(step, "retry_settings", None)

            az_pipeline.settings.default_compute = "cpu"
            validation = az_pipeline._validate()
            warnings = [str(w) for w in (validation._warnings or [])]
            assert not any("retry_settings" in w for w in warnings), warnings

    def test_limits_reach_every_step_and_the_payload(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        """A configured timeout reaches every step and survives serialization.

        Asserting ``step.limits.timeout == 1800`` alone would pass whether or not
        the SDK recognises the field, which is the flaw that let the old retry
        setting look functional for months. So this also asserts the value reaches
        the serialized payload and that validation reports no ``Unknown field``.
        """
        limits = LimitsConfig(timeout=1800)
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline):
            generator = AzureMLPipelineGenerator(
                "test_limits",
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="test@latest",
                limits_config=limits,
            )
            az_pipeline = generator.generate()

            assert az_pipeline.jobs
            for step in az_pipeline.jobs.values():
                assert step.limits is not None
                assert step.limits.timeout == 1800

            az_pipeline.settings.default_compute = "cpu"

            validation = az_pipeline._validate()
            warnings = [str(w) for w in (validation._warnings or [])]
            assert not any("limits" in w for w in warnings), warnings

            payload = az_pipeline._to_rest_object().as_dict()
            for node in payload["properties"]["jobs"].values():
                assert "limits" in node, sorted(node)
                # Seconds become an ISO 8601 duration only if a schema serializer
                # handled the value; a passed-through object would not convert.
                assert node["limits"]["timeout"] == "PT30M", node["limits"]

    def test_no_limits_by_default(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        """Without limits_config, steps run uncapped."""
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline):
            generator = AzureMLPipelineGenerator(
                "test_no_limits",
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                aml_env="test@latest",
            )
            az_pipeline = generator.generate()
            for step in az_pipeline.jobs.values():
                assert not getattr(step, "limits", None)

    def test_auto_sets_kedro_env(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        pipeline_name = "unit_test_pipeline"
        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(
                pipeline_name,
                "dev",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
            )

            for node in generator.generate().jobs.values():
                assert node.environment_variables["KEDRO_ENV"] == "dev"

    def test_explicit_kedro_env_overrides_auto(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        pipeline_name = "unit_test_pipeline"
        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(
                pipeline_name,
                "dev",
                dummy_plugin_config,
                {},
                extra_env={"KEDRO_ENV": "staging"},
                catalog=multi_catalog,
            )

            for node in generator.generate().jobs.values():
                assert node.environment_variables["KEDRO_ENV"] == "staging"


class TestFactoryPatternHandling:
    """Catalog factory-resolved inputs are treated as plain string parameters."""

    def test_factory_resolved_input_is_string_type(self, dummy_pipeline, dummy_plugin_config, factory_catalog):
        """A pipeline input resolved via a catalog factory pattern (not in catalog.filter())
        must be treated as a non-AzureML string input, not as a uri_folder."""
        pipeline_name = "unit_test_pipeline"
        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(
                pipeline_name,
                "local",
                dummy_plugin_config,
                {},
                catalog=factory_catalog,
                aml_env="unit_test/aml_env@latest",
            )
            assert "input_data" not in factory_catalog.filter()
            assert "input_data" in factory_catalog  # factory resolves it
            assert generator._is_param_or_root_non_azureml_asset_dataset("input_data", dummy_pipeline), (
                "Factory-resolved pipeline input should be treated as a non-AzureML string input"
            )
            inp = generator._get_input("input_data", dummy_pipeline)
            assert inp.type == "string", (
                f"Expected 'string' input type for factory-resolved pipeline input, got '{inp.type}'"
            )


class TestUriFileRestrictions:
    """``uri_file`` assets have input-only and no-output constraints."""

    def test_uri_file_non_input_raises(self, dummy_pipeline, dummy_plugin_config):
        """A ``uri_file`` used as intermediate data (not a pipeline input) should raise."""
        from kedro.io import DataCatalog
        from kedro.io.core import Version
        from kedro_datasets.pickle import PickleDataset

        from kedro_azureml_pipeline.datasets import AzureMLAssetDataset

        # i2 is an intermediate dataset (not in pipeline.inputs())
        uri_file_ds = AzureMLAssetDataset(
            dataset={"type": PickleDataset, "filepath": "test.pickle"},
            azureml_dataset="test_ds",
            version=Version(None, None),
            azureml_type="uri_file",
        )
        catalog = DataCatalog({"input_data": MagicMock(), "i2": uri_file_ds})

        generator = AzureMLPipelineGenerator(
            "test",
            "local",
            dummy_plugin_config,
            {},
            catalog=catalog,
        )
        with pytest.raises(ValueError, match="uri_file.*can only be used as pipeline inputs"):
            generator._get_input("i2", dummy_pipeline)

    def test_uri_file_output_raises(self, dummy_plugin_config):
        """A ``uri_file`` used as output should raise."""
        from kedro.io import DataCatalog
        from kedro.io.core import Version
        from kedro_datasets.pickle import PickleDataset

        from kedro_azureml_pipeline.datasets import AzureMLAssetDataset

        uri_file_ds = AzureMLAssetDataset(
            dataset={"type": PickleDataset, "filepath": "test.pickle"},
            azureml_dataset="test_ds",
            version=Version(None, None),
            azureml_type="uri_file",
        )
        catalog = DataCatalog({"output_data": uri_file_ds})

        generator = AzureMLPipelineGenerator(
            "test",
            "local",
            dummy_plugin_config,
            {},
            catalog=catalog,
        )
        with pytest.raises(ValueError, match="uri_file.*cannot be used as outputs"):
            generator._get_output("output_data")


class TestMlflowEnvVarInjection:
    """Test that the generator injects MLflow env vars into each node."""

    def test_mlflow_env_vars_injected_when_enabled(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        pipeline_name = "unit_test_pipeline"

        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(
                pipeline_name,
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                mlflow_run_name="my-run",
                experiment_name="my-experiment",
            )
            az_pipeline = generator.generate()

        for node_name, node_job in az_pipeline.jobs.items():
            env = node_job.environment_variables
            assert env[KEDRO_AZUREML_MLFLOW_ENABLED] == "1"
            assert env[KEDRO_AZUREML_MLFLOW_RUN_NAME] == "my-run"
            assert env[KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME] == "my-experiment"
            assert env[KEDRO_AZUREML_MLFLOW_NODE_NAME] == node_name

    def test_mlflow_env_vars_absent_when_no_experiment(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        pipeline_name = "unit_test_pipeline"

        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(
                pipeline_name,
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
            )
            az_pipeline = generator.generate()

        for node_job in az_pipeline.jobs.values():
            env = node_job.environment_variables
            assert KEDRO_AZUREML_MLFLOW_ENABLED not in env
            assert KEDRO_AZUREML_MLFLOW_RUN_NAME not in env

    def test_mlflow_empty_experiment_name_skips_experiment_env(
        self, dummy_plugin_config, dummy_pipeline, multi_catalog
    ):
        """When ``experiment_name=""`` (falsy but not None), MLFLOW_EXPERIMENT_NAME is omitted."""
        pipeline_name = "unit_test_pipeline"

        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(
                pipeline_name,
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                experiment_name="",
            )
            az_pipeline = generator.generate()

        for node_job in az_pipeline.jobs.values():
            env = node_job.environment_variables
            assert env[KEDRO_AZUREML_MLFLOW_ENABLED] == "1"
            assert KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME not in env

    def test_mlflow_node_name_unique_per_node(self, dummy_plugin_config, dummy_pipeline, multi_catalog):
        pipeline_name = "unit_test_pipeline"

        with patch.dict("kedro.framework.project.pipelines", {pipeline_name: dummy_pipeline}):
            generator = AzureMLPipelineGenerator(
                pipeline_name,
                "local",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                experiment_name="my-experiment",
            )
            az_pipeline = generator.generate()

        node_names = {
            node_job.environment_variables[KEDRO_AZUREML_MLFLOW_NODE_NAME] for node_job in az_pipeline.jobs.values()
        }
        assert len(node_names) == len(az_pipeline.jobs), "Each node should have a unique MLFLOW_NODE_NAME"


class TestSanitizeFunctions:
    """Property-based tests for name sanitisation functions."""

    @given(name=st.text(min_size=1, max_size=50))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_sanitize_param_name_always_lowercase_alphanumeric(self, name, dummy_plugin_config, multi_catalog):
        """_sanitize_param_name always produces lowercase alphanumeric + underscore."""
        generator = AzureMLPipelineGenerator(
            "test",
            "env",
            dummy_plugin_config,
            {},
            catalog=multi_catalog,
        )
        result = generator._sanitize_param_name(name)
        assert result == result.lower()
        assert all(c.isalnum() or c == "_" for c in result)
        assert len(result) == len(name)

    @given(name=st.text(min_size=1, max_size=50))
    @settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_sanitize_azure_name_always_lowercase(self, name, dummy_plugin_config, multi_catalog):
        """_sanitize_azure_name always produces a lowercase string with no dots."""
        generator = AzureMLPipelineGenerator(
            "test",
            "env",
            dummy_plugin_config,
            {},
            catalog=multi_catalog,
        )
        result = generator._sanitize_azure_name(name)
        assert result == result.lower()
        assert "." not in result


class TestGetKedroParam:
    """_get_kedro_param resolves dot-separated paths through dicts and objects.

    Kedro 1.3+ allows Pydantic models as parameter values. The generator must
    traverse both dicts (plain YAML) and objects (Pydantic) when resolving
    ``params:`` references used in ``@distributed_job`` decorators.
    """

    def _make_generator(self, kedro_params, dummy_plugin_config, multi_catalog):
        return AzureMLPipelineGenerator(
            "test",
            "local",
            dummy_plugin_config,
            kedro_params,
            catalog=multi_catalog,
        )

    def test_flat_dict_lookup(self, dummy_plugin_config, multi_catalog):
        gen = self._make_generator({"num_nodes": 4}, dummy_plugin_config, multi_catalog)
        assert gen._get_kedro_param("num_nodes") == 4

    def test_nested_dict_lookup(self, dummy_plugin_config, multi_catalog):
        params = {"a": {"b": {"c": 42}}}
        gen = self._make_generator(params, dummy_plugin_config, multi_catalog)
        assert gen._get_kedro_param("a.b.c") == 42

    def test_pydantic_model_lookup(self, dummy_plugin_config, multi_catalog):
        """Traverses a Pydantic BaseModel via attribute access."""
        from pydantic import BaseModel

        class Inner(BaseModel):
            num_nodes: int = 3

        class Outer(BaseModel):
            tuning: Inner = Inner()

        params = {"spec": Outer()}
        gen = self._make_generator(params, dummy_plugin_config, multi_catalog)
        assert gen._get_kedro_param("spec.tuning.num_nodes") == 3

    def test_mixed_dict_and_pydantic(self, dummy_plugin_config, multi_catalog):
        """Dict at the top level, Pydantic model nested inside."""
        from pydantic import BaseModel

        class Config(BaseModel):
            value: int = 7

        params = {"product": {"group": {"variant": {"spec": Config()}}}}
        gen = self._make_generator(params, dummy_plugin_config, multi_catalog)
        assert gen._get_kedro_param("product.group.variant.spec.value") == 7

    def test_explicit_params_arg(self, dummy_plugin_config, multi_catalog):
        """Passing an explicit params dict overrides kedro_params."""
        gen = self._make_generator({"x": 1}, dummy_plugin_config, multi_catalog)
        assert gen._get_kedro_param("y", params={"y": 99}) == 99

    def test_missing_key_raises(self, dummy_plugin_config, multi_catalog):
        gen = self._make_generator({}, dummy_plugin_config, multi_catalog)
        with pytest.raises(KeyError):
            gen._get_kedro_param("missing")

    def test_missing_attr_on_object_raises(self, dummy_plugin_config, multi_catalog):
        from pydantic import BaseModel

        class Spec(BaseModel):
            x: int = 1

        gen = self._make_generator({"spec": Spec()}, dummy_plugin_config, multi_catalog)
        with pytest.raises(AttributeError):
            gen._get_kedro_param("spec.nonexistent")

    def test_single_level_pydantic_attr(self, dummy_plugin_config, multi_catalog):
        """Flat lookup on a Pydantic model passed via explicit params."""
        from pydantic import BaseModel

        class Cfg(BaseModel):
            n: int = 5

        gen = self._make_generator({}, dummy_plugin_config, multi_catalog)
        assert gen._get_kedro_param("n", params=Cfg()) == 5

    def test_dataclass_attr_lookup(self, dummy_plugin_config, multi_catalog):
        """Supports plain dataclasses (not only Pydantic)."""
        from dataclasses import dataclass

        @dataclass
        class Settings:
            num_nodes: int = 10

        params = {"settings": Settings()}
        gen = self._make_generator(params, dummy_plugin_config, multi_catalog)
        assert gen._get_kedro_param("settings.num_nodes") == 10

    def test_deeply_nested_pydantic(self, dummy_plugin_config, multi_catalog):
        """Four levels of Pydantic nesting."""
        from pydantic import BaseModel

        class D(BaseModel):
            val: int = 99

        class C(BaseModel):
            d: D = D()

        class B(BaseModel):
            c: C = C()

        class A(BaseModel):
            b: B = B()

        gen = self._make_generator({"a": A()}, dummy_plugin_config, multi_catalog)
        assert gen._get_kedro_param("a.b.c.d.val") == 99


class TestFromParamsOrValue:
    """_from_params_or_value resolves params: references or returns literals."""

    def _make_generator(self, kedro_params, dummy_plugin_config, multi_catalog):
        return AzureMLPipelineGenerator(
            "test",
            "local",
            dummy_plugin_config,
            kedro_params,
            catalog=multi_catalog,
        )

    def test_literal_int(self, dummy_plugin_config, multi_catalog):
        gen = self._make_generator({}, dummy_plugin_config, multi_catalog)
        assert gen._from_params_or_value(None, 5, hint="num_nodes") == 5

    def test_params_reference_no_namespace(self, dummy_plugin_config, multi_catalog):
        gen = self._make_generator({"num_nodes": 8}, dummy_plugin_config, multi_catalog)
        assert gen._from_params_or_value(None, "params:num_nodes", hint="num_nodes") == 8

    def test_params_reference_with_namespace(self, dummy_plugin_config, multi_catalog):
        params = {"product": {"group": {"variant": {"spec": {"tuning": {"num_nodes": 3}}}}}}
        gen = self._make_generator(params, dummy_plugin_config, multi_catalog)
        result = gen._from_params_or_value(
            "product.group.variant",
            "params:spec.tuning.num_nodes",
            hint="num_nodes",
        )
        assert result == 3

    def test_params_reference_with_pydantic_namespace(self, dummy_plugin_config, multi_catalog):
        """Namespace traversal through Pydantic models (Kedro 1.3 params)."""
        from pydantic import BaseModel

        class TuningConfig(BaseModel):
            num_nodes: int = 2

        class VariantSpec(BaseModel):
            tuning: TuningConfig = TuningConfig()

        params = {"product": {"group": {"variant": {"spec": VariantSpec()}}}}
        gen = self._make_generator(params, dummy_plugin_config, multi_catalog)
        result = gen._from_params_or_value(
            "product.group.variant",
            "params:spec.tuning.num_nodes",
            hint="num_nodes",
        )
        assert result == 2

    def test_wrong_type_raises(self, dummy_plugin_config, multi_catalog):
        gen = self._make_generator({}, dummy_plugin_config, multi_catalog)
        with pytest.raises(ValueError, match="Expected either"):
            gen._from_params_or_value(None, 3.14, hint="num_nodes")

    def test_bool_is_not_int(self, dummy_plugin_config, multi_catalog):
        """bool is rejected when expected_value_type is int (strict type() check)."""
        gen = self._make_generator({}, dummy_plugin_config, multi_catalog)
        with pytest.raises(ValueError, match="Expected either"):
            gen._from_params_or_value(None, True, hint="num_nodes")

    def test_params_ref_mixed_pydantic_and_dict(self, dummy_plugin_config, multi_catalog):
        """Dict at top, Pydantic in middle, dict at bottom."""
        from pydantic import BaseModel

        class Middle(BaseModel):
            inner: dict = {"count": 6}

        params = {"ns": {"spec": Middle()}}
        gen = self._make_generator(params, dummy_plugin_config, multi_catalog)
        result = gen._from_params_or_value("ns", "params:spec.inner.count", hint="count")
        assert result == 6


class TestResolveAzureEnvironment:
    """Docker image URI detection in _resolve_azure_environment."""

    @pytest.mark.parametrize(
        "env_value",
        [
            "myregistry.azurecr.io/my-image:latest",
            "evolta.azurecr.io/evolta-forecast:abc123def",
            "registry.example.com/org/image",
            "docker.io/library/python:3.13",
            "ghcr.io/owner/repo:sha256",
        ],
    )
    def test_docker_uri_wrapped_in_environment(self, env_value, dummy_plugin_config, multi_catalog):
        gen = AzureMLPipelineGenerator(
            "test", "local", dummy_plugin_config, {}, catalog=multi_catalog, aml_env=env_value
        )
        result = gen._resolve_azure_environment()
        assert isinstance(result, Environment)
        assert result.image == env_value

    @pytest.mark.parametrize(
        "env_value",
        [
            "my-env@latest",
            "unit_test/aml_env@latest",
            "evolta-forecast-base@latest",
            "my-environment",
            "my-env:1",
        ],
    )
    def test_named_environment_passed_through(self, env_value, dummy_plugin_config, multi_catalog):
        gen = AzureMLPipelineGenerator(
            "test", "local", dummy_plugin_config, {}, catalog=multi_catalog, aml_env=env_value
        )
        result = gen._resolve_azure_environment()
        assert result == env_value
        assert isinstance(result, str)

    def test_none_when_no_environment(self, dummy_plugin_config, multi_catalog):
        dummy_plugin_config.execution.environment = None
        gen = AzureMLPipelineGenerator("test", "local", dummy_plugin_config, {}, catalog=multi_catalog)
        assert gen._resolve_azure_environment() is None

    def test_config_fallback_docker_uri(self, dummy_plugin_config, multi_catalog):
        dummy_plugin_config.execution.environment = "myacr.azurecr.io/image:v1"
        gen = AzureMLPipelineGenerator("test", "local", dummy_plugin_config, {}, catalog=multi_catalog)
        result = gen._resolve_azure_environment()
        assert isinstance(result, Environment)
        assert result.image == "myacr.azurecr.io/image:v1"

    def test_aml_env_overrides_config(self, dummy_plugin_config, multi_catalog):
        dummy_plugin_config.execution.environment = "config-env@latest"
        gen = AzureMLPipelineGenerator(
            "test", "local", dummy_plugin_config, {}, catalog=multi_catalog, aml_env="override-env@latest"
        )
        assert gen._resolve_azure_environment() == "override-env@latest"


class TestCodeReference:
    """Every step carries the code reference when one is given, else the configured directory."""

    CODE_ID = (
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.MachineLearningServices"
        "/workspaces/ws/codes/pkg-snapshot/versions/3"
    )

    def _generate(self, dummy_pipeline, dummy_plugin_config, multi_catalog, **kwargs):
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline):
            return AzureMLPipelineGenerator(
                "dummy_pipeline", "unit_test_env", dummy_plugin_config, {}, catalog=multi_catalog, **kwargs
            ).generate()

    def test_reference_on_every_step_with_unchanged_commands(self, dummy_pipeline, dummy_plugin_config, multi_catalog):
        with_ref = self._generate(dummy_pipeline, dummy_plugin_config, multi_catalog, code=self.CODE_ID)
        without = self._generate(dummy_pipeline, dummy_plugin_config, multi_catalog)
        assert with_ref.jobs.keys() == without.jobs.keys()
        for name, step in with_ref.jobs.items():
            assert step.component.code == self.CODE_ID
            assert step.command == without.jobs[name].command

    def test_no_reference_keeps_the_configured_directory(self, dummy_pipeline, dummy_plugin_config, multi_catalog):
        dummy_plugin_config.execution.code_directory = "app"
        az_pipeline = self._generate(dummy_pipeline, dummy_plugin_config, multi_catalog)
        assert all(step.component.code == "app" for step in az_pipeline.jobs.values())

    def test_no_code_directory_means_no_code(self, dummy_pipeline, dummy_plugin_config, multi_catalog):
        dummy_plugin_config.execution.code_directory = None
        az_pipeline = self._generate(dummy_pipeline, dummy_plugin_config, multi_catalog)
        assert all(step.component.code is None for step in az_pipeline.jobs.values())


def _notified_generator(kedro_pipeline, config, catalog, events, experiment_name="exp"):
    """Generator for *kedro_pipeline* with a notification definition on job ``job-a``."""
    with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=kedro_pipeline):
        generator = AzureMLPipelineGenerator(
            "p",
            "unit_test_env",
            config,
            {},
            catalog=catalog,
            experiment_name=experiment_name,
            notification_config=NotificationConfig(webhook_env="HOOK_URL", events=list(events), wait_timeout=120),
            job_name="job-a",
            display_name="Job A",
        )
        return generator, generator.generate()


def _three_leaf_pipeline():
    """One root fanning out to three leaves."""
    return pipeline([
        node(identity, inputs="input_data", outputs="i2", name="root"),
        node(identity, inputs="i2", outputs="leaf_b_out", name="leaf_b"),
        node(identity, inputs="i2", outputs="leaf_a_out", name="leaf_a"),
        node(identity, inputs="i2", outputs="leaf_c_out", name="leaf_c"),
    ])


class TestNotificationStamping:
    """Announcer and poster designation and the stamped environment."""

    def test_single_leaf_pipeline(self, dummy_pipeline, dummy_plugin_config, multi_catalog):
        generator, job = _notified_generator(dummy_pipeline, dummy_plugin_config, multi_catalog, ["start", "success"])
        assert generator.notification_roles(dummy_pipeline) == NotificationRoles("node1", "node3", ())
        steps = job.jobs
        for step in steps.values():
            definition = json.loads(step.environment_variables[KEDRO_AZUREML_NOTIFY])
            assert definition["job_name"] == "job-a"
            assert definition["display_name"] == "Job A"
            assert definition["pipeline_name"] == "p"
            assert definition["events"] == ["start", "success"]
            assert definition["webhook_env"] == "HOOK_URL"
            assert definition["wait_timeout"] == 120
        assert steps["node1"].environment_variables[KEDRO_AZUREML_NOTIFY_START] == "1"
        assert KEDRO_AZUREML_NOTIFY_START not in steps["node2"].environment_variables
        assert KEDRO_AZUREML_NOTIFY_START not in steps["node3"].environment_variables
        assert steps["node3"].environment_variables[KEDRO_AZUREML_NOTIFY_OUTCOME] == "1"
        assert steps["node3"].environment_variables[KEDRO_AZUREML_NOTIFY_SIBLINGS] == ""
        assert KEDRO_AZUREML_NOTIFY_OUTCOME not in steps["node1"].environment_variables

    def test_multi_leaf_pipeline_has_one_poster_with_siblings(self, dummy_plugin_config, multi_catalog):
        generator, job = _notified_generator(_three_leaf_pipeline(), dummy_plugin_config, multi_catalog, ["success"])
        posters = [
            name for name, step in job.jobs.items() if KEDRO_AZUREML_NOTIFY_OUTCOME in step.environment_variables
        ]
        assert posters == ["leaf_c"]
        assert job.jobs["leaf_c"].environment_variables[KEDRO_AZUREML_NOTIFY_SIBLINGS] == "leaf_a,leaf_b"
        assert job.jobs["root"].environment_variables[KEDRO_AZUREML_NOTIFY_START] == "1"

    def test_single_node_pipeline_carries_both_markers(self, dummy_plugin_config, multi_catalog):
        single = pipeline([node(identity, inputs="input_data", outputs="output_data", name="only")])
        _, job = _notified_generator(single, dummy_plugin_config, multi_catalog, ["start", "success", "failure"])
        env = job.jobs["only"].environment_variables
        assert env[KEDRO_AZUREML_NOTIFY_START] == "1"
        assert env[KEDRO_AZUREML_NOTIFY_OUTCOME] == "1"
        assert env[KEDRO_AZUREML_NOTIFY_SIBLINGS] == ""

    def test_job_without_notifications_stamps_nothing(self, dummy_pipeline, dummy_plugin_config, multi_catalog):
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline):
            generator = AzureMLPipelineGenerator("p", "unit_test_env", dummy_plugin_config, {}, catalog=multi_catalog)
            assert generator.notification_roles(dummy_pipeline) is None
            for step in generator.generate().jobs.values():
                assert not any(key.startswith("KEDRO_AZUREML_NOTIFY") for key in step.environment_variables)

    def test_designation_is_stable(self, dummy_plugin_config, multi_catalog):
        first, _ = _notified_generator(_three_leaf_pipeline(), dummy_plugin_config, multi_catalog, ["success"])
        second, _ = _notified_generator(_three_leaf_pipeline(), dummy_plugin_config, multi_catalog, ["success"])
        assert first.notification_roles(_three_leaf_pipeline()) == second.notification_roles(_three_leaf_pipeline())

    def test_multi_leaf_success_without_experiment_name_fails(self, dummy_plugin_config, multi_catalog):
        with pytest.raises(ConfigException, match="Job 'job-a' enables the 'success' notification.*3 leaf nodes"):
            _notified_generator(
                _three_leaf_pipeline(), dummy_plugin_config, multi_catalog, ["success"], experiment_name=None
            )

    def test_multi_leaf_failure_only_without_experiment_name_passes(self, dummy_plugin_config, multi_catalog):
        _, job = _notified_generator(
            _three_leaf_pipeline(), dummy_plugin_config, multi_catalog, ["failure"], experiment_name=None
        )
        assert len(job.jobs) == 4

    def test_display_name_defaults_to_job_name(self, dummy_pipeline, dummy_plugin_config, multi_catalog):
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline):
            generator = AzureMLPipelineGenerator(
                "p",
                "unit_test_env",
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                notification_config=NotificationConfig(webhook_env="HOOK_URL", events=["failure"]),
                job_name="job-a",
            )
            definition = json.loads(generator.generate().jobs["node1"].environment_variables[KEDRO_AZUREML_NOTIFY])
        assert definition["display_name"] == "job-a"


class TestDatastoreInputs:
    """An ``AzureMLDatastoreDataset`` input compiles to its datastore path."""

    @staticmethod
    def _catalog():
        from kedro.io import DataCatalog
        from kedro_datasets.pickle import PickleDataset

        from kedro_azureml_pipeline.datasets import AzureMLDatastoreDataset

        return DataCatalog({
            "input_data": AzureMLDatastoreDataset(
                datastore="shared_store",
                datastore_path="ercot/label-name/table_a",
                dataset={"type": PickleDataset, "filepath": "table_a.pickle"},
            )
        })

    def test_input_is_the_datastore_path_with_az_input(self, dummy_pipeline, dummy_plugin_config):
        """The step gets the datastore URI as a folder input, and its command names it with ``--az-input``."""
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=dummy_pipeline):
            job = AzureMLPipelineGenerator("test", "local", dummy_plugin_config, {}, catalog=self._catalog()).generate()
        step = job.jobs["node1"]
        assert step.inputs["input_data"].path == "azureml://datastores/shared_store/paths/ercot/label-name/table_a"
        assert step.inputs["input_data"].type == "uri_folder"
        assert "--az-input=input_data ${{inputs.input_data}}" in step.command

    def test_intermediate_use_raises(self, dummy_pipeline, dummy_plugin_config):
        """A datastore dataset between two nodes is refused."""
        generator = AzureMLPipelineGenerator("test", "local", dummy_plugin_config, {}, catalog=self._catalog())
        generator.catalog["i2"] = generator.catalog["input_data"]
        with pytest.raises(ValueError, match="can only be used as pipeline inputs"):
            generator._get_input("i2", dummy_pipeline)

    def test_output_raises(self, dummy_plugin_config):
        """A datastore dataset cannot be an output."""
        generator = AzureMLPipelineGenerator("test", "local", dummy_plugin_config, {}, catalog=self._catalog())
        with pytest.raises(ValueError, match="cannot be used as outputs"):
            generator._get_output("input_data")


class TestOtherOutputs:
    """Outputs of other dataset classes compile to a folder with no name and no path."""

    def test_memory_dataset_output_is_an_unnamed_folder(self, dummy_plugin_config):
        """A ``MemoryDataset`` output becomes an unnamed ``uri_folder`` output."""
        from kedro.io import DataCatalog, MemoryDataset

        catalog = DataCatalog({"output_data": MemoryDataset()})
        output = AzureMLPipelineGenerator("test", "local", dummy_plugin_config, {}, catalog=catalog)._get_output(
            "output_data"
        )
        assert output.type == "uri_folder"
        assert output.name is None
        assert output.path is None
