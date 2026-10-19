# Notify on run outcomes

Post one message to a webhook when a job starts, one when it finishes, and one when it fails, for scheduled and ad hoc runs alike. This page sets it up with a Slack incoming webhook and shows how to shape the message.

`--on-job-scheduled` on `kedro azureml run` fires in the submitting shell right after submission. It never runs for a job Azure ML's scheduler triggers, and it knows nothing about the outcome. Notifications run inside the job's own steps, so they cover both.

## 1. Create the webhook and put its URL in the step environment

Create a [Slack incoming webhook](https://api.slack.com/messaging/webhooks) for the target channel. The URL is a secret: it must reach the step as an environment variable and never appear in `azureml.yml` or in logs.

Two routes work:

- **A secret store read at startup.** If your project already fetches secrets inside Azure ML steps (for example from Key Vault in `settings.py`), add the webhook URL there and export it as `SLACK_WEBHOOK_URL`. This covers scheduled runs, because it needs nothing from the submitting shell.
- **`--env-var` at submission.** `kedro azureml run -j nightly --env-var SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL` stamps the value into every step of that submission. It does not reach jobs the scheduler triggers later.

## 2. Define the notification and reference it from the job

```yaml
notifications:
  alerts:
    webhook_env: SLACK_WEBHOOK_URL
    events: [start, success, failure]

jobs:
  nightly:
    pipeline:
      pipeline_name: data_processing
    experiment_name: nightly
    limits:
      timeout: 3600
    notifications: alerts
```

Definitions are named and shared, like `schedules`. A job factory can reference one too, and a more specific factory can reference a different one, which is how you report failures only for a subset of variants.

## 3. Compile and read the stamped steps

```bash
kedro azureml compile -j nightly
```

Every step of the job carries `KEDRO_AZUREML_NOTIFY` with the resolved definition. Exactly one root step carries `KEDRO_AZUREML_NOTIFY_START=1` and exactly one leaf step carries `KEDRO_AZUREML_NOTIFY_OUTCOME=1` together with `KEDRO_AZUREML_NOTIFY_SIBLINGS`, the other leaves it waits for. Nothing else changes, and a `kedro run` outside Azure ML posts nothing because the variables are absent.

## What posts, and when

Every Kedro node is its own Azure ML step and its own Kedro session, so the plugin decides which step speaks for the job:

| Event | Posted by | When |
|---|---|---|
| `start` | The designated root step | At its pipeline start, without waiting for other roots |
| `failure` | The step that raised | From its pipeline-error hook, naming the node and the first 250 characters of the exception |
| `success` | The designated leaf step | After its own node, once every sibling leaf's run is in a terminal state and all finished |
| `warning` | The designated leaf step | When the job finished but a step marked itself degraded, and the outage is new, has a new table, or has lasted `warning_repeat_hours` since the last message |
| `recovered` | The designated leaf step | On the first finished run without a degraded step after one with |

Two edge cases keep the "one outcome per job" promise:

- **A sibling leaf died without running its error hook** (killed for memory, cancelled). The outcome step sees the sibling's run failed or killed with no `kedro.error` tag on it, and posts one `failure` naming that sibling. A sibling that raised normally carries the tag and already posted, so the outcome step stays silent.
- **A sibling never reaches a terminal state within `wait_timeout`.** The outcome step posts an `unknown` message naming the pending siblings. Silence is the failure mode this feature exists to remove, so the cap produces a message rather than nothing.

## Report runs that served degraded output

A job can finish successfully while an input was missing or stale. To be told, have the
step that noticed set a `kedro.warning` tag on its own MLflow run, and subscribe the job to
`warning` and `recovered`:

```python
import mlflow

# Entries are table:reason:last_data, joined by ";". The reason is free text, such as
# empty or stale; last_data is an ISO 8601 instant or "unknown".
mlflow.set_tag("kedro.warning", "actual_system_conditions:empty:2026-09-30T08:55:00+00:00")
```

```yaml
notifications:
  alerts:
    token_env: SLACK_BOT_TOKEN
    channel: C0123456789
    events: [failure, warning, recovered]
    warning_repeat_hours: 24
```

The leaf step reads the tag from every step of the job, not only the leaves, and compares
the job with its previous finished run:

- The first degraded run posts a `warning`. Through the Slack API it opens a new thread.
- Later degraded runs post nothing, unless a table is new to the outage (a `warning` at
  once) or `warning_repeat_hours` have passed since the last message (a reminder). Times are
  run start times, and a run up to `warning_repeat_tolerance_minutes` early still reminds.
- The first clean run posts `recovered`, naming when the outage started.
- Reminders, re-warnings and `recovered` reply in the first warning's thread. The webhook
  cannot thread, so it posts them as separate messages.
- A failed run changes nothing: the next finished run is compared with the last finished
  run before it.

The outage state is written as `kedro.*` tags on the job's root run (`kedro.job_name`,
`kedro.notify_state` and the outage's start, last message, tables and thread), so it needs
an `experiment_name`. With `success` also subscribed, a degraded run posts its `warning`
instead of `success`.

Whether Azure ML cancels a job's remaining steps when one fails depends on the pipeline job's `continue_on_step_failure` setting, which the plugin does not set. Either way each raising step posts its own `failure`, so two steps failing at the same moment produce two messages.

!!! warning "Jobs killed at the root are not reported"

    A job-level timeout, a cancellation from Studio, or a preempted single-leaf job ends the step processes with a signal. No hook runs, so no message is posted. Cover that gap with an Azure Monitor alert on the workspace's failed and cancelled runs.

## Shape the message

Without `payload`, the plugin posts `{"text": "..."}`, which Slack incoming webhooks render as a plain message:

```text
[success] Daily training (pipeline training, env prod) finished after 3412s. Run: https://ml.azure.com/runs/...
```

To add content, point `payload` at a function that receives a [`NotificationEvent`][kedro_azureml_pipeline.hooks.NotificationEvent] and returns the mapping to post. The plugin posts it unchanged, so any schema the webhook accepts works, including Slack blocks:

```python
# my_project/notifications.py
from kedro_azureml_pipeline.hooks import NotificationEvent


def build_payload(event: NotificationEvent) -> dict:
    """Render a run event as Slack blocks."""
    icon = {"start": ":arrow_forward:", "success": ":white_check_mark:", "failure": ":x:"}.get(event.event, ":grey_question:")
    lines = [f"{icon} *{event.display_name}* {event.event} ({event.pipeline_name}, {event.kedro_env})"]
    if event.event == "failure":
        lines.append(f"Node `{event.node}`: {event.error}")
    if event.studio_url:
        lines.append(f"<{event.studio_url}|Open in Studio>")
    return {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]}
```

```yaml
notifications:
  alerts:
    webhook_env: SLACK_WEBHOOK_URL
    events: [start, success, failure]
    payload: my_project.notifications:build_payload
```

The builder runs inside the outcome step, which sees only its own node's outputs. Anything from other steps (metrics, registered model versions) has to come from MLflow: search the runs under `event.root_run_id` by their `kedro.node_name` tag. A builder that raises or returns something other than a mapping is logged at WARNING and the default payload is posted instead, so a formatting bug degrades the message rather than losing it.

## Post through the Slack API

A webhook has two limits. Slack labels every attachment it posts with "Added by *app*", and it returns no message timestamp, so the outcome messages cannot reply to the `start` message. Posting through the Slack API removes both: messages carry the app's own name and icon, and the `success` or `failure` of a run lands in a thread under its `start` message and is also sent to the channel, the way the GitHub app reports on a pull request.

1. In the Slack app that owns the channel, add the `chat:write` bot scope, install the app, and copy the bot user token (it starts with `xoxb-`). Store it the same way as the webhook URL, so that it reaches the step as an environment variable.
2. Invite the app to the channel and copy the channel ID from the channel details (it starts with `C`). The ID is not a secret and goes in `azureml.yml`.
3. Name both in the definition:

```yaml
notifications:
  alerts:
    token_env: SLACK_BOT_TOKEN
    channel: C0123456789
    webhook_env: SLACK_WEBHOOK_URL
    events: [start, success, failure]
    payload: my_project.notifications:build_payload
```

`webhook_env` may stay as a fallback: a step whose environment lacks the token posts through the webhook instead. The payload builder is unchanged. The plugin adds the `channel`, and for an outcome the `thread_ts` and `reply_broadcast` fields, to whatever the builder returns, so a payload of `text`, `blocks`, and `attachments` posts the same either way.

The thread works through MLflow. The announcer step tags the job's root run with the timestamp Slack returned for `start` (tag `kedro.notify_thread`), and the step that posts an outcome reads it back. A job without the `mlflow` extra, or one whose definition leaves out `start`, posts its outcomes as plain channel messages.

## Requirements and limits

- Posting uses the standard library with a 10 second timeout. Any error is logged at WARNING and swallowed; a webhook or Slack outage never fails a step. Neither the URL nor the token is ever logged. A reply Slack refuses (for example `not_in_channel` before the app is invited) is logged with Slack's error code.
- `wait_timeout` must be below the job's `limits.timeout`; configuration loading rejects anything else.
- A job that enables `success` on a pipeline with more than one leaf must declare `experiment_name` and run with the `mlflow` extra installed, so the outcome step can find its sibling runs. Compilation rejects a multi-leaf job without an experiment name.

## See also

- [Configuration reference](../reference/configuration.md#notifications) for every `notifications` field, including the Slack API pair
- [Hook lifecycle](../explanation/hook-lifecycle.md#how-run-notifications-work-remotely) for why one step per node forces the announcer and poster roles
- [Schedule pipelines](schedule-pipelines.md) for the runs the scheduler triggers
- [Deploy from CI/CD](deploy-from-cicd.md#use-a-callback-for-notifications) for the submission-time callback this complements
