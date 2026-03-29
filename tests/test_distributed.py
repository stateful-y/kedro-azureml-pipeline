import json
import os
from unittest.mock import patch

import pytest
from azure.ai.ml.entities import Job
from kedro.pipeline import node, pipeline

from kedro_azureml_pipeline.constants import DISTRIBUTED_CONFIG_FIELD
from kedro_azureml_pipeline.distributed import distributed_job
from kedro_azureml_pipeline.distributed.config import Framework
from kedro_azureml_pipeline.distributed.utils import is_distributed_master_node
from kedro_azureml_pipeline.generator import AzureMLPipelineGenerator
from tests.utils import identity


class TestDistributedJobDecorator:
    """Tests for the ``@distributed_job`` decorator."""

    @pytest.mark.parametrize("framework", [Framework.PyTorch, Framework.MPI, Framework.TensorFlow])
    @pytest.mark.parametrize("num_nodes", [1, 2, 4])
    def test_marks_node_with_config(self, framework, num_nodes):
        """Decorated node carries the distributed config attribute."""

        @distributed_job(framework, num_nodes=num_nodes)
        def my_distributed_node(x):
            return x

        p = pipeline([
            node(identity, inputs="input_data", outputs="i2", name="node1"),
            node(my_distributed_node, inputs="i2", outputs="i3", name="node2"),
            node(identity, inputs="i3", outputs="output_data", name="node3"),
        ])

        assert hasattr(p.nodes[1].func, DISTRIBUTED_CONFIG_FIELD)
        assert all(not hasattr(n.func, DISTRIBUTED_CONFIG_FIELD) for i, n in enumerate(p.nodes) if i != 1)

    @pytest.mark.parametrize("framework", [Framework.PyTorch, Framework.MPI, Framework.TensorFlow])
    def test_preserves_function_behavior(self, framework):
        """Decorated function still returns the same value as the original."""

        @distributed_job(framework, num_nodes=2)
        def my_node(x):
            return x

        sentinel = object()
        assert my_node(sentinel) is sentinel

    @pytest.mark.parametrize("framework", [Framework.PyTorch, Framework.MPI, Framework.TensorFlow])
    def test_config_is_valid_json(self, framework):
        """The attached config attribute can be serialized as JSON."""

        @distributed_job(framework, num_nodes=3)
        def my_node(x):
            return x

        config_str = str(getattr(my_node, DISTRIBUTED_CONFIG_FIELD))
        parsed = json.loads(config_str)
        assert isinstance(parsed, dict)


class TestDistributedPipelineGeneration:
    """Tests for Azure ML pipeline generation with distributed nodes."""

    @pytest.mark.parametrize("framework", [Framework.PyTorch, Framework.MPI, Framework.TensorFlow])
    @pytest.mark.parametrize(
        "num_nodes,kedro_params",
        [
            (1, {}),
            (2, {}),
            ("params:number_of_nodes", {"number_of_nodes": 8}),
            ("params:data_science.nodes", {"data_science": {"nodes": 12}}),
        ],
    )
    def test_generates_pipeline_with_distributed_node(
        self, dummy_plugin_config, framework, num_nodes, kedro_params, multi_catalog
    ):
        """Generated Azure ML pipeline sets the correct instance_count."""

        @distributed_job(framework, num_nodes=num_nodes)
        def my_distributed_node(x):
            return x

        p = pipeline([
            node(identity, inputs="input_data", outputs="i2", name="node1"),
            node(my_distributed_node, inputs="i2", outputs="i3", name="distributed_node"),
            node(identity, inputs="i3", outputs="output_data", name="node3"),
        ])

        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=p):
            generator = AzureMLPipelineGenerator(
                "dummy_pipeline",
                "unit_test_env",
                dummy_plugin_config,
                kedro_params,
                aml_env="unit_test/aml_env@latest",
                catalog=multi_catalog,
            )

            az_pipeline = generator.generate()
            assert isinstance(az_pipeline, Job)
            expected_num_nodes = num_nodes
            if isinstance(num_nodes, str):
                expected_num_nodes = (
                    kedro_params["number_of_nodes"]
                    if "number_of_nodes" in kedro_params
                    else kedro_params["data_science"]["nodes"]
                )
            assert az_pipeline.jobs["distributed_node"].resources["instance_count"] == expected_num_nodes

    @pytest.mark.parametrize("invalid_num_nodes", [False, 123.0, {}, "asdf"])
    def test_raises_on_invalid_num_nodes(self, dummy_plugin_config, invalid_num_nodes, multi_catalog):
        """A ``ValueError`` is raised for non-int, non-params num_nodes values."""

        @distributed_job(Framework.PyTorch, num_nodes=invalid_num_nodes)
        def my_distributed_node(x):
            return x

        p = pipeline([
            node(identity, inputs="input_data", outputs="i2", name="node1"),
            node(my_distributed_node, inputs="i2", outputs="i3", name="distributed_node"),
            node(identity, inputs="i3", outputs="output_data", name="node3"),
        ])

        with patch.object(AzureMLPipelineGenerator, "get_kedro_pipeline", return_value=p):
            generator = AzureMLPipelineGenerator(
                "dummy_pipeline",
                "unit_test_env",
                dummy_plugin_config,
                {},
                aml_env="unit_test/aml_env@latest",
                catalog=multi_catalog,
            )

            with pytest.raises(ValueError):
                generator.generate()


class TestMasterNodeDetection:
    """Tests for ``is_distributed_master_node`` environment detection."""

    @pytest.mark.parametrize(
        "environment,expected_master",
        [
            ({"TF_CONFIG": "ASD"}, False),
            ({"TF_CONFIG": json.dumps({"my_config": "not valid"})}, False),
            ({"RANK": "0"}, True),
            ({"RANK": "1"}, False),
            ({"RANK": "666"}, False),
            ({"OMPI_COMM_WORLD_RANK": "0"}, True),
            ({"OMPI_COMM_WORLD_RANK": "1"}, False),
            ({"TF_CONFIG": json.dumps({"task": {"type": "master"}})}, True),
            ({"TF_CONFIG": json.dumps({"task": {"type": "chief"}})}, True),
            ({"TF_CONFIG": json.dumps({"task": {"type": "worker"}})}, False),
            ({"TF_CONFIG": json.dumps({"task": {"type": "worker", "index": 1}})}, False),
            ({"TF_CONFIG": json.dumps({"task": {"type": "worker", "index": 0}})}, True),
        ],
    )
    def test_detects_master_correctly(self, environment, expected_master):
        """Rank detection returns the expected master status."""
        with patch.dict(os.environ, environment):
            assert is_distributed_master_node() == expected_master

    def test_returns_true_when_no_distributed_env(self):
        """Without distributed env vars, the process is assumed to be master."""
        clean_env = {k: v for k, v in os.environ.items() if k not in ("RANK", "OMPI_COMM_WORLD_RANK", "TF_CONFIG")}
        with patch.dict(os.environ, clean_env, clear=True):
            assert is_distributed_master_node() is True
