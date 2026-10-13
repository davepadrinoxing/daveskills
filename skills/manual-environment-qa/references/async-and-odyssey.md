# Async and Odyssey QA

Use this reference when behavior crosses Sidekiq, AMQP, Karafka, cronjobs, Odyssey workloads, or multiple components.

## Build a Causal Chain

Map the expected checkpoints before execution:

```text
trigger -> accepted request/write -> enqueue or publish -> worker/consumer processing -> downstream write/event -> user-visible result
```

For each checkpoint, identify:

- exact code/config owner
- correlation key available without exposing personal data
- expected state before and after
- read-only evidence source
- retry/idempotency expectation
- cleanup impact

Do not claim end-to-end success from only the first or final checkpoint.

When the producer/consumer does not expose a safe correlation key or success log, say so explicitly. Combine source-side trigger evidence, a bounded log window, and independently verified downstream state; do not invent topic offsets or claim log correlation that the implementation does not provide.

## Local Services

The current Docker stack defines:

- `app` / `xtm_app` for Rails
- `worker` / `xtm_worker` for `amqp_worker`
- `queue_processor` / `xtm_queue_processor` for Sidekiq `campaigns` and `default` queues
- Redis, MySQL, Kafka, and Schema Registry dependencies

Verify actual status before use:

```sh
make status
docker compose ps
```

Read logs with bounded output or a focused time window when possible. `make logs service=...` follows indefinitely, so use it only when interactive following is intended.

Karafka topics and consumers are declared in `karafka.rb`; a Karafka service is not defined in the current `docker-compose.yml`. Verify how the consumer is running before expecting local consumption. Starting a consumer can process messages and requires authorization.

## Sidekiq

Inspect job class, `queue_as`/Sidekiq options, enqueue call, retry behavior, uniqueness/idempotency controls, and the deployed worker queue arguments.

Read-only queue summary from a Rails runtime:

```ruby
require "sidekiq/api"

pp({
  queues: Sidekiq::Queue.all.to_h { |queue| [queue.name, queue.size] },
  scheduled: Sidekiq::ScheduledSet.new.size,
  retries: Sidekiq::RetrySet.new.size,
  dead: Sidekiq::DeadSet.new.size
})
```

Avoid dumping job arguments because they may contain personal or sensitive data. Capture queue counts around the exact action and use a safe correlation identifier in logs/state when available.

Before an authorized worker stop, inspect whether Sidekiq is actively processing work:

```ruby
require "sidekiq/api"

pp({
  processes: Sidekiq::ProcessSet.new.map { |process| { identity: process.identity, busy: process["busy"] } },
  active_workers: Sidekiq::Workers.new.size
})
```

Do not stop a shared worker or one with active work. After an authorized local stop, verify the process/container is actually stopped before enqueuing the QA job.

If cleanup requires deleting a queued QA job, first inspect the actual ActiveJob/Sidekiq wrapper used by the changed code. Prefer the JID captured at enqueue time; otherwise match the verified job class and sanitized stable arguments, require exactly one match, and record the JID before deletion. Stop when zero or multiple jobs match. Never select a cleanup target from queue count or class name alone.

The Odyssey values currently define separate workers for `default`, `campaigns`, `low`, `filling_candidates`, and candidate assignments. Verify spelling and actual deployed arguments from current templates and pods; do not infer a queue from a class name.

Retrying/deleting jobs, clearing sets, changing queue state, or starting/stopping workers requires explicit authorization.

## AMQP Workers

Inspect all relevant layers:

- publisher call and message name
- `config/amqp_wiring.rb` exchange/routing key
- `config/amqp_handlers.rb` processor mapping, retry/delay, and timeout
- `config/amqp_workers.yml` or `config/amqp_workers_deletions.yml` queue selection
- processor implementation and downstream effects
- local `worker` or Odyssey AMQP-worker logs

Remember that transaction rollback may prevent `after_commit` publication, while a committed publication cannot be recalled by rolling back XTM data. Confirm cleanup across the message consumer and downstream state.

Do not publish a synthetic message, purge/requeue a broker queue, or restart an AMQP worker without explicit authorization.

## Karafka Consumers

Inspect:

- topic and initial offset in `karafka.rb`
- consumer class and delegated service
- group/client configuration
- preview/production consumer release values
- idempotency under at-least-once delivery
- log and downstream-state evidence

The current repository declares profile-settings and representative-work-experience topics. Always verify current code because topic names and releases can change.

Producing a Kafka record, changing offsets, replaying a topic, or starting a consumer requires explicit authorization. Prefer observing an existing authorized trigger and verifying consumer logs plus downstream state.

## Cronjobs

First verify the task and schedule in `odyssey/main.preview/values.yaml.gotmpl` or the selected environment values. Then discover the deployed object and recent job history read-only:

```sh
kubectl config current-context
kubectl --context <verified-preview-context> -n xtm get cronjobs
kubectl --context <verified-preview-context> -n xtm describe cronjob <verified-name>
kubectl --context <verified-preview-context> -n xtm get jobs --sort-by=.metadata.creationTimestamp
```

Stop unless the resolved context is the intended preview cluster. Inspect relevant job/pod logs after resolving the exact job and pod. Triggering a cronjob manually, suspending it, or changing its schedule is a mutation and requires explicit authorization and preview coordination.

## Odyssey and Preview

The current preview Helmfile defines releases for the XTM app/API, AMQP workers, Karafka consumers, and multiple Sidekiq workers in namespace `xtm`. Discover actual resources rather than assuming Helm release names equal pod names:

```sh
kubectl config current-context
kubectl --context <verified-preview-context> -n xtm get deployments,pods,cronjobs
kubectl --context <verified-preview-context> -n xtm describe pod <verified-pod>
kubectl --context <verified-preview-context> -n xtm get pod <verified-pod> -o jsonpath='{.spec.containers[*].image}'
kubectl --context <verified-preview-context> -n xtm logs <verified-pod> --since=<bounded-window>
```

Stop unless the resolved context is the intended preview cluster. Compare the observed image tag/digest with the intended PR SHA or image tag when possible. Record the context, namespace, workload/pod, image, timestamp window, and sanitized correlation key in evidence.

Default to `get`, `describe`, and logs. The following require explicit authorization:

- deployment or Helm changes
- pod/workload restarts or scaling
- `kubectl exec` commands that mutate data or runtime state
- cronjob triggers
- queue/message manipulation
- configuration application

## Retries, Idempotency, and Timing

- Assume Sidekiq and Karafka work can run more than once.
- Separate “enqueued/published” from “processed successfully.”
- Define a bounded polling window based on actual retry/schedule configuration; do not use arbitrary long sleeps.
- Test duplicate delivery only when explicitly authorized and cleanup is safe.
- Verify no duplicate persisted/downstream effect after a retry or repeated request when idempotency is in scope.
- Mark a timeout as `Blocked` or `Executed and failed` based on whether the system completed incorrectly or the evidence channel was unavailable.
