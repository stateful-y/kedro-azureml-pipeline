from unittest.mock import MagicMock, patch

import pytest
from azure.ai.ml.entities import Job

from kedro_azureml_pipeline.config import ClusterConfig
from kedro_azureml_pipeline.constants import (
    KEDRO_AZUREML_MLFLOW_ENABLED,
    KEDRO_AZUREML_MLFLOW_EXPERIMENT_NAME,
    KEDRO_AZUREML_MLFLOW_NODE_NAME,
    KEDRO_AZUREML_MLFLOW_RUN_NAME,
)
from kedro_azureml_pipeline.generator import AzureMLPipelineGenerator, ConfigException


class TestPipelineGeneration:
    """Core pipeline generation and Kedro integration."""

    @pytest.mark.parametrize(
        "pipeline_name",
        [
            ("dummy_pipeline"),
            ("dummy_pipeline_compute_tag"),
        ],
    )
    @pytest.mark.parametrize(
        "generator_kwargs",
        [
            {"aml_env": "unit_test/aml_env@latest"},
        ],
    )
    def test_can_generate_azure_pipeline(
        self,
        pipeline_name,
        dummy_plugin_config,
        generator_kwargs: dict,
        multi_catalog,
        request,
    ):
        pipeline = request.getfixturevalue(pipeline_name)
        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=pipeline):
            env_name = "unit_test_env"
            generator = AzureMLPipelineGenerator(
                pipeline_name,
                env_name,
                dummy_plugin_config,
                {},
                catalog=multi_catalog,
                **generator_kwargs,
            )

            az_pipeline = generator.generate()
            assert isinstance(az_pipeline, Job) and az_pipeline.display_name == pipeline_name, (
                "Invalid basic pipeline data"
            )
            assert all(f"kedro azureml -e {env_name} execute" in node.command for node in az_pipeline.jobs.values()), (
                "Commands seems invalid"
            )

            assert all(node.environment == generator_kwargs["aml_env"] for node in az_pipeline.jobs.values()), (
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
