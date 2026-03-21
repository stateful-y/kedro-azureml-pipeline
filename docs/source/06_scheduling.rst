==========
Scheduling
==========

The ``kedro azureml submit`` command enables you to create and update
`Azure ML schedules <https://learn.microsoft.com/en-us/azure/machine-learning/how-to-schedule-pipeline-job>`_
for your Kedro pipelines. Each schedule maps a (optionally filtered) Kedro
pipeline to a cron or recurrence trigger.

Configuration
-------------

Schedules and jobs are defined in your ``conf/<env>/azureml.yml`` file
alongside the existing ``azure`` section.

Schedules section
*****************

The ``schedules`` section defines reusable, named trigger definitions that
can be referenced by multiple jobs:

.. code:: yaml

    schedules:
      daily_morning:
        cron:
          expression: "0 8 * * *"
          time_zone: "UTC"

      weekly_monday:
        recurrence:
          frequency: "week"
          interval: 1
          schedule:
            hours: [9]
            minutes: [0]
            week_days: ["monday"]
          time_zone: "Europe/Amsterdam"

Two trigger types are supported:

Cron trigger
~~~~~~~~~~~~

Uses a standard cron expression. Maps to ``azure.ai.ml.entities.CronTrigger``.

.. code:: yaml

    schedules:
      my_cron:
        cron:
          expression: "0 8 * * *"     # required
          start_time: "2025-01-01"     # optional
          end_time: "2025-12-31"       # optional
          time_zone: "UTC"             # optional, default "UTC"

Recurrence trigger
~~~~~~~~~~~~~~~~~~

Defines a repeating schedule by frequency and interval. Maps to
``azure.ai.ml.entities.RecurrenceTrigger``.

.. code:: yaml

    schedules:
      my_recurrence:
        recurrence:
          frequency: "week"            # required: minute, hour, day, week, month
          interval: 1                  # required
          schedule:                    # optional RecurrencePattern
            hours: [9, 17]
            minutes: [0]
            week_days: ["monday", "friday"]
          start_time: "2025-01-01"     # optional
          end_time: "2025-12-31"       # optional
          time_zone: "UTC"             # optional, default "UTC"

Jobs section
************

The ``jobs`` section defines the pipeline jobs to be submitted with their
associated schedules:

.. code:: yaml

    jobs:
      etl_daily:
        pipeline:
          pipeline_name: "__default__"
          tags: ["etl"]
        schedule: daily_morning   # reference to a named schedule
        display_name: "Daily ETL"
        description: "Run the ETL nodes every morning"
        experiment_name: "my_experiment"  # optional override

      full_pipeline_weekly:
        pipeline:
          pipeline_name: "__default__"
        schedule: weekly_monday
        display_name: "Full Pipeline Weekly"

Each job has the following fields:

- ``pipeline``: Pipeline filter options (see below)
- ``schedule``: Either a string referencing a named schedule, or an inline schedule definition
- ``display_name``: (optional) Human-readable name for the schedule in Azure ML
- ``description``: (optional) Description shown in the Azure ML portal
- ``experiment_name``: (optional) Override the experiment name from the ``azure`` section

Inline schedules
~~~~~~~~~~~~~~~~

Instead of referencing a named schedule, you can define the trigger inline:

.. code:: yaml

    jobs:
      inline_example:
        pipeline:
          pipeline_name: "__default__"
        schedule:
          cron:
            expression: "30 6 * * 1-5"
            time_zone: "Europe/London"

Pipeline filtering
******************

The ``pipeline`` field in each job accepts the following options to filter
which nodes of the Kedro pipeline are included:

.. code:: yaml

    pipeline:
      pipeline_name: "__default__"   # Kedro pipeline name (default: __default__)
      tags: ["etl", "preprocessing"] # filter by node tags
      node_names: ["clean_data"]     # specific node names
      from_nodes: ["split_data"]     # start from these nodes
      to_nodes: ["train_model"]      # end at these nodes
      from_inputs: ["raw_data"]      # start from nodes consuming these inputs
      to_outputs: ["predictions"]    # end at nodes producing these outputs
      node_namespaces: ["ml"]        # filter by namespace

These options mirror `Kedro's Pipeline.filter()
<https://docs.kedro.org/en/stable/kedro.pipeline.Pipeline.html>`_ parameters,
giving you fine-grained control over which parts of your pipeline run on
each schedule.

Full example
************

.. code:: yaml

    workspace:
      __default__:
        subscription_id: "abc-123"
        resource_group: "my-rg"
        name: "my-workspace"

    compute:
      __default__:
        cluster_name: "cpu-cluster"

    execution:
      environment: "my-aml-env@latest"

    schedules:
      daily_morning:
        cron:
          expression: "0 8 * * *"
          time_zone: "UTC"

      weekly_monday:
        recurrence:
          frequency: "week"
          interval: 1
          schedule:
            hours: [9]
            minutes: [0]
            week_days: ["monday"]
          time_zone: "Europe/Amsterdam"

    jobs:
      etl_daily:
        pipeline:
          pipeline_name: "__default__"
          tags: ["etl"]
        schedule: daily_morning
        display_name: "Daily ETL"
        description: "Run ETL nodes every morning"

      full_pipeline_weekly:
        pipeline:
          pipeline_name: "__default__"
        schedule: weekly_monday
        display_name: "Full Pipeline Weekly"

CLI usage
---------

Submit a specific job:

.. code:: console

    kedro azureml submit -j etl_daily

Submit multiple jobs:

.. code:: console

    kedro azureml submit -j etl_daily -j full_pipeline_weekly

Preview schedules without creating them:

.. code:: console

    kedro azureml submit -j etl_daily --dry-run

Force an immediate run (ignore any configured schedule):

.. code:: console

    kedro azureml submit -j etl_daily --once

Options
*******

.. code:: console

    Usage: kedro azureml submit [OPTIONS]

      Submit scheduled pipeline jobs to Azure ML.

    Options:
      -w, --workspace TEXT        Named workspace to use
      --aml-env TEXT              Azure ML Environment to use
      -j, --job TEXT              Name(s) of jobs to submit (required, can be
                                  repeated)
      --params TEXT               Parameters override in form of JSON string
      --env-var TEXT              Environment variables for steps, format:
                                  KEY=VALUE (can be repeated)
      -lv, --load-versions TEXT   Dataset load versions
      --dry-run                   Preview what schedules would be created without
                                  actually submitting to Azure ML.
      --once                      Force an immediate run even when a schedule is
                                  configured.
      --wait-for-completion       Block until the pipeline run completes
                                  (useful in CI).
      --on-job-scheduled TEXT     Callback function invoked after each job is
                                  scheduled, format: path.to.module:function_name
      -h, --help                  Show this message and exit.

Override defaults at submit time:

.. code:: console

    kedro azureml submit --aml-env myacr.azurecr.io/image:v2 --params '{"key": "value"}'
