==========
Quickstart
==========

Video-tutorial
--------------

You can go through the written quickstart here or watch the video on
YouTube:

.. raw:: html

   <iframe width="560" height="315" src="https://www.youtube-nocookie.com/embed/w_9RzYpGplY" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>

----

Prerequisites
-------------

Before you start, make sure that you have the following resources
created in Azure and have their **names** ready to input to the plugin:

-  Azure Subscription ID
-  Azure Resource Group
-  Azure ML workspace
-  Azure ML Compute Cluster

Both flows use **Azure ML Environments** to define the execution image. The difference is whether your application code is baked into the image or uploaded at runtime:

1. **Code upload flow** — build a base image with dependencies only, register it as an Azure ML Environment, and set ``code_directory: "."`` so code is uploaded on every run. Best for fast iteration.
2. **Docker image flow** — build an image containing both dependencies and application code, register it as an Azure ML Environment, and set ``code_directory: ~``. Best for CI/CD and production repeatability.

Both flows require you to build a Docker image and push it to a registry.
If you use **Azure Container Registry (ACR)** for this, make sure it is
created and accessible from your Azure ML workspace before you begin.

Project initialization
----------------------

1. Make sure that you're logged into Azure (``az login``).
2. Prepare new virtual environment with Python >=3.9. Install the
   packages

   .. code:: console

      pip install "kedro>=0.18.5,<0.19" "kedro-docker" "kedro-azureml"

2. Create new project (e.g. from starter)

   .. code:: console

      kedro new --starter=spaceflights

      Project Name
      ============
      Please enter a human readable name for your new project.
      Spaces, hyphens, and underscores are allowed.
       [Spaceflights]: kedro_azureml_demo

      The project name 'kedro_azureml_demo' has been applied to:
      - The project title in /Users/marcin/Dev/tmp/kedro-azureml-demo/README.md
      - The folder created for your project in /Users/marcin/Dev/tmp/kedro-azureml-demo
      - The project's python package in /Users/marcin/Dev/tmp/kedro-azureml-demo/src/kedro_azureml_demo

3. Go to the project's directory: ``cd kedro-azureml-demo``
4. Add ``kedro-azureml`` to ``src/requirements.txt``
5. (optional) Remove ``kedro-telemetry`` from ``src/requirements.txt``
   or set appropriate settings
   (`https://github.com/kedro-org/kedro-plugins/tree/main/kedro-telemetry <https://github.com/kedro-org/kedro-plugins/tree/main/kedro-telemetry>`__).
6. Install the requirements ``pip install -r src/requirements.txt``
7. Initialize Kedro Azure ML plugin, it requires the Azure resource names as stated above. Experiment name can be anything you like (as
   long as it's allowed by Azure ML).

.. code:: console

    Usage: kedro azureml init [OPTIONS] SUBSCRIPTION_ID RESOURCE_GROUP
                              WORKSPACE_NAME CLUSTER_NAME

      Creates basic configuration for Kedro AzureML plugin

    Options:
      --azureml-environment, --aml-env TEXT
                                      Azure ML environment to use (required)

Example ``init`` command:

    .. code:: console

       kedro azureml init <AZURE_SUBSCRIPTION_ID> <AZURE_RESOURCE_GROUP> <AML_WORKSPACE_NAME> <COMPUTE_NAME> \
        --aml-env <YOUR_ARC>.azurecr.io/<IMAGE_NAME>:latest

.. note::
    Data between pipeline nodes is passed using Azure ML's built-in pipeline data passing.
    No storage account key is needed as AML handles inter-step data via the workspace's default datastore.

    If you need to route specific datasets through a different datastore (e.g. for
    compliance or performance), declare them explicitly in the catalog using
    ``AzureMLAssetDataset``. See :doc:`05_data_assets` for more information.

Adjusting the Data Catalog
--------------------------

8. Adjust the Data Catalog - the default one stores all data locally,
   whereas the plugin will automatically use Azure ML built-in storage for intermediate data. Only
   input data is required to be read locally.

   Final ``conf/base/catalog.yml`` should look like this:

   .. code:: yaml

      companies:
        type: pandas.CSVDataset
        filepath: data/01_raw/companies.csv
        layer: raw

      reviews:
        type: pandas.CSVDataset
        filepath: data/01_raw/reviews.csv
        layer: raw

      shuttles:
        type: pandas.ExcelDataset
        filepath: data/01_raw/shuttles.xlsx
        layer: raw

Build the environment
---------------------
For the project's code to run on Azure ML it needs to have an environment
with the necessary dependencies.


9. Start by executing the following command:

   .. code:: console

      kedro docker init

   This command creates a several files, including ``Dockerfile`` and ``.dockerignore``. These can be adjusted to match the workflow for your project.

Pick your deployment option
***************************

(Option 1) Code upload flow
~~~~~~~~~~~~~~~~~~~~~~~~~~~

With code upload, only dependencies live in the Docker image. Your project code
is uploaded to Azure ML on every ``kedro azureml submit`` invocation.

10. Everything apart from the section *install project requirements*
can be removed from the ``Dockerfile``.

    This plugin automatically creates empty ``.amlignore`` file (`see the official docs <https://learn.microsoft.com/en-us/azure/machine-learning/how-to-save-write-experiment-files#storage-limits-of-experiment-snapshots>`__)
    which means that all of the files (including potentially sensitive ones!) will be uploaded to Azure ML. Modify this file if needed.

    .. collapse:: See example Dockerfile for code upload flow

        .. code-block:: dockerfile

            ARG BASE_IMAGE=python:3.12
            FROM $BASE_IMAGE

            # install project requirements
            COPY src/requirements.txt /tmp/requirements.txt
            RUN pip install -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

11. Ensure ``execution.code_directory: "."`` is set in the ``azureml.yml`` config file (it's set by default if you used ``init``).



12. Build the image:

    .. code:: console

        kedro docker build --docker-args "--build-arg=BASE_IMAGE=python:3.12" --image=<acr repo name>.azurecr.io/kedro-base-image:latest

12. Login to ACR and push the image:

    .. code:: console

        az acr login --name <acr repo name>
        docker push <acr repo name>.azurecr.io/kedro-base-image:latest

13. Register the Azure ML Environment:

    .. code:: console

        az ml environment create --name <environment-name> --image <acr repo name>.azurecr.io/kedro-base-image:latest

\
Now you can re-use this environment and run the pipeline without the need to build the docker image again (unless you add some dependencies to your environment, obviously 😉 ).

.. warning::
    | Azure Code upload feature has issues with empty folders as identified in `GitHub #33 <https://github.com/getindata/kedro-azureml/issues/33>`__, where empty folders or folders with empty files might not get uploaded to Azure ML, which might result in the failing pipeline.
    | We recommend to:
    | - make sure that Kedro environments you intent to use in Azure have at least one non-empty file specified
    | - gracefully handle folder creation in your pipeline's code (e.g. if your code depends on an existence of some folder)
    |
    | The plugin will do it's best to handle some of the edge-cases, but the fact that some of your files might not be captured by Azure ML SDK is out of our reach.

(Option 2) Docker image flow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

With docker image flow, both dependencies **and** your application code are baked
into the Docker image. You must rebuild and push the image whenever your code
changes.

.. note::
    | We recommend this option for CI/CD-automated MLOps workflows where
    | experiment repeatability is critical.

10. Keep the full ``Dockerfile`` (including the ``COPY`` and project install steps). Adjust the ``.dockerignore`` to include any files needed in the image, such as ``!data/01_raw`` for raw data.

11. Ensure ``execution.code_directory: ~`` (null) is set in ``azureml.yml`` so that code is **not** uploaded at runtime.

12. Build the image with your application code:

    .. code:: console

        kedro docker build --docker-args "--build-arg=BASE_IMAGE=python:3.12" --image=<acr repo name>.azurecr.io/kedro-app:latest

13. Login to ACR and push the image:

    .. code:: console

        az acr login --name <acr repo name>
        docker push <acr repo name>.azurecr.io/kedro-app:latest

14. Register the Azure ML Environment:

    .. code:: console

        az ml environment create --name <environment-name> --image <acr repo name>.azurecr.io/kedro-app:latest

15. Set ``execution.environment`` in ``azureml.yml`` to the registered environment name.


Run the pipeline
----------------

14. Define a job in your ``azureml.yml`` configuration:

    .. code:: yaml

       jobs:
         default_run:
           pipeline:
             pipeline_name: "__default__"

15. Submit the job to Azure ML Pipelines:

    .. code:: console

       kedro azureml submit -j default_run

16. Plugin will verify the configuration (e.g. the existence of the
    compute cluster) and then it will create a *Job* in the Azure ML.
    The URL to view the job will be displayed in the console output.

    .. code:: console

       RunId: placid_pot_bdcyntnkvn
       Web View: https://ml.azure.com/runs/placid_pot_bdcyntnkvn?wsid=/subscriptions/<redacted>/resourcegroups/<redacted>/workspaces/ml-ops-sandbox

       Streaming logs/azureml/executionlogs.txt
       ========================================

       [2022-07-22 11:45:38Z] Submitting 2 runs, first five are: 1ee5f43f:8cf2e387-e7ec-44cc-9615-2108891153f7,7d81aeeb:c8b837a9-1f79-4971-aae3-3191b29b42e8
       [2022-07-22 11:47:02Z] Completing processing run id c8b837a9-1f79-4971-aae3-3191b29b42e8.
       [2022-07-22 11:47:25Z] Completing processing run id 8cf2e387-e7ec-44cc-9615-2108891153f7.
       [2022-07-22 11:47:26Z] Submitting 1 runs, first five are: 362b9632:7867ead0-b308-49df-95ca-efa26f8583cb
       [2022-07-22 11:49:27Z] Completing processing run id 7867ead0-b308-49df-95ca-efa26f8583cb.
       [2022-07-22 11:49:28Z] Submitting 2 runs, first five are: 03b2293e:e9e210e7-10ab-4010-91f6-4a40aabf3a30,4f9ccafb:3c00e735-cd3f-40c7-9c1d-fe53349ca8bc
       [2022-07-22 11:50:50Z] Completing processing run id e9e210e7-10ab-4010-91f6-4a40aabf3a30.
       [2022-07-22 11:50:51Z] Submitting 1 runs, first five are: 7a88df7a:c95c1488-5f55-48fa-80ce-971d5412f0fb
       [2022-07-22 11:51:26Z] Completing processing run id 3c00e735-cd3f-40c7-9c1d-fe53349ca8bc.
       [2022-07-22 11:51:26Z] Submitting 1 runs, first five are: a79effc8:0828c39a-6f02-43f5-acfd-33543f0d6c74
       [2022-07-22 11:52:38Z] Completing processing run id c95c1488-5f55-48fa-80ce-971d5412f0fb.
       [2022-07-22 11:52:39Z] Submitting 1 runs, first five are: 0a18d6d6:cb9c8f61-e129-4394-a795-ab70be74eb0f
       [2022-07-22 11:53:03Z] Completing processing run id 0828c39a-6f02-43f5-acfd-33543f0d6c74.
       [2022-07-22 11:53:04Z] Submitting 1 runs, first five are: 1af5c8de:2821dc44-3399-4a26-9cdf-1e8f5b7d6b62
       [2022-07-22 11:53:28Z] Completing processing run id cb9c8f61-e129-4394-a795-ab70be74eb0f.
       [2022-07-22 11:53:51Z] Completing processing run id 2821dc44-3399-4a26-9cdf-1e8f5b7d6b62.

       Execution Summary
       =================
       RunId: placid_pot_bdcyntnkvn

|Kedro AzureML Pipeline execution|


------------

Using a different compute cluster for specific nodes
------------------

For certain nodes it can make sense to run them on a different
compute clusters (e.g. High Memory or GPU). This can be achieved
using `Node tags <https://kedro.readthedocs.io/en/stable/kedro.pipeline.node.html>`_
and adding additional compute targets in your ``azureml.yml``.

After creating an additional compute cluster in your AzureML workspace,
in this case the additional cluster is called ``cpu-cluster-8``,
we can add it in our ``azureml.yml`` under an alias (in this case ``chunky``).

.. code:: console

  compute:
    __default__:
      cluster_name: "cpu-cluster"
    chunky:
      cluster_name: "cpu-cluster-8"


Now we are able to reference this compute target in our kedro pipelines using kedro node tags:

.. code:: console

        [
            node(
                func=preprocess_companies,
                inputs="companies",
                outputs="preprocessed_companies",
                name="preprocess_companies_node",
                tags=["chunky"]
            ),
            node(
                func=preprocess_shuttles,
                inputs="shuttles",
                outputs="preprocessed_shuttles",
                name="preprocess_shuttles_node",
            ),
            node(
                func=create_model_input_table,
                inputs=["preprocessed_shuttles", "preprocessed_companies", "reviews"],
                outputs="model_input_table",
                name="create_model_input_table_node",
                tags=["chunky"]
            ),
        ],

When running our project, ``preprocess_companies`` and ``create_model_input_table``
will be run on ``cpu-cluster-8`` while all other nodes are run on the default ``cpu-cluster``.

Marking a node as deterministic
------------------

By default the plugin will mark all nodes of the Azure ML pipeline as non-deterministic, which
means that Azure ML will not reuse the results of the node if it has been run before.

To mark a node as deterministic, you can simply add the ``deterministic`` tag to the node.
This also implies the tag is reserved and cannot be used for compute types.

Distributed training
------------------

The plugins supports distributed training via native Azure ML distributed orchestration, which includes:

- MPI - https://learn.microsoft.com/en-us/azure/machine-learning/how-to-train-distributed-gpu#mpi
- PyTorch - https://learn.microsoft.com/en-us/azure/machine-learning/how-to-train-distributed-gpu#pytorch
- TensorFlow - https://learn.microsoft.com/en-us/azure/machine-learning/how-to-train-distributed-gpu#tensorflow

If one of your Kedro's pipeline nodes requires distributed training (e.g. you train a neural network with PyTorch), you can mark the node with ``distributed_job`` decorator from ``kedro_azureml.distributed.decorators`` and use native Kedro parameters to specify the number of nodes you want to spawn for the job.
An example for PyTorch looks like this:

.. code:: python

    #                    | use appropriate framework
    #                   \|/                      \/ specify the number of distributed nodes to spawn for the job
    @distributed_job(Framework.PyTorch, num_nodes="params:num_nodes")
    def train_model_pytorch(
        X_train: pd.DataFrame, y_train: pd.Series, num_nodes: int, max_epochs: int
    ):
        # rest of the code
        pass

In the ``pipeline`` you would use this node like that:

.. code:: python

    node(
        func=train_model_pytorch,
        inputs=["X_train", "y_train", "params:num_nodes", "params:max_epochs"],
        outputs="regressor",
        name="train_model_node",
    ),

and that's it!
The ``params:`` you use support namespacing as well as overriding at runtime, e.g. when launching the Azure ML job:

.. code:: console

    kedro azureml submit -j my_training_job --params '{"data_science": {"active_modelling_pipeline": {"num_nodes": 4}}}'

The ``distributed_job`` decorator also supports "hard-coded" values for number of nodes:

.. code:: python

    @distributed_job(Framework.PyTorch, num_nodes=2) # no need to use Kedro params here
    def train_model_pytorch(
        X_train: pd.DataFrame, y_train: pd.Series, num_nodes: int, max_epochs: int
    ):
        # rest of the code
        pass

We have tested the implementation heavily with PyTorch (+PyTorch Lightning) and GPUs. If you encounter any problems, drop us an issue on GitHub!

Submit customization
--------------------

Pipeline runs are configured as **jobs** in ``azureml.yml`` (see :doc:`06_scheduling`).
The ``kedro azureml submit`` command accepts a few additional options to override
settings at submit time:

- ``-w, --workspace`` selects a named workspace from the ``workspace`` section of ``azureml.yml``,
- ``--aml-env`` overrides the configured Azure ML Environment,
- ``--params`` takes a JSON string with parameters override (JSONed version of ``conf/*/parameters.yml``, not the Kedro's ``params:`` syntax),
- ``--env-var KEY=VALUE`` sets the OS environment variable injected to the steps during runtime (can be used multiple times),
- ``--load-versions`` specifies a particular dataset version (timestamp) for loading (similar behavior as Kedro),
- ``--dry-run`` previews what would be submitted without calling Azure ML,
- ``--once`` forces an immediate run even when the job has a schedule configured,
- ``--wait-for-completion`` blocks until the pipeline run finishes (useful in CI),
- ``--on-job-scheduled path.to.module:my_function`` specifies a callback invoked after each job is scheduled.

Jobs define the pipeline name, optional schedule, display name, compute cluster,
and experiment name in config. See :doc:`06_scheduling` for full details.

The ``--on-job-scheduled`` callback receives the Azure ML ``Job`` object as its
only argument:

.. code:: python

    # src/mymodule/callbacks.py
    def save_job_url(job):
        """Save the studio URL when the job is scheduled."""
        with open("job_url.txt", "w") as f:
            f.write(job.studio_url)

.. code:: console

    kedro azureml submit -j my_job --once --on-job-scheduled mymodule.callbacks:save_job_url


.. |br| raw:: html

  <br/>
