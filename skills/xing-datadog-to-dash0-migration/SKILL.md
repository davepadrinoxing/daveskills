---
name: xing-datadog-to-dash0-migration
description: Assess and guide XING/New Work service migrations from Datadog to Dash0 on Odyssey or Enclave, including repository discovery, Odyssey Helm values, Argo validation, Dash0 traces/logs/metrics checks, worker coverage, Prometheus applicability, Browser RUM gaps, SRE/SLO follow-ups, and rollout readiness.
---

# XING Datadog to Dash0 Migration

Use this skill when a user asks to migrate, assess, review, or validate a XING/New Work service moving from Datadog to Dash0. Start in assessment mode unless the user explicitly asks to implement and the repository context is clear.

## Operating Rules

- Read the local repo first. Prefer existing Odyssey/Enclave patterns and recently migrated sibling services over inventing new config.
- Treat Dash0 docs and Odyssey chart behavior as the source of truth. Use internal docs links provided by the user or already known in the repo; browse when the docs may have changed.
- Use the `dash0-api` skill for Dash0 authentication, dataset selection, and API queries. Prefer repeatable API calls over `dash0-cli`.
- Keep Datadog-only functionality until there is a Dash0 replacement and the team agrees to remove it.
- Do not remove Datadog Browser RUM unless Dash0 web SDK tokens and endpoint wiring are ready and preview is validated.
- Do not assume Prometheus is used. Prove it from repo config, docs, metrics endpoints, or team input.
- Separate backend/platform migration from Browser RUM, Prometheus tuning, and SLO cleanup. These often belong in follow-up PRs.

## Assessment Workflow

1. **Identify platform and deploy shape**
   - Locate `odyssey/`, `enclave/`, Helmfile values, or platform-specific manifests.
   - List all releases/workloads: web/API, AMQP, Kafka, Sidekiq, CronJobs, deploy-time Jobs, and other workers.
   - Check whether one namespace has multiple Helm releases. Only one release should enable the namespace-level Dash0 resource.

2. **Find current Datadog usage**
   - Search for Datadog Helm values, labels, annotations, env vars, tracing helpers, browser RUM packages, and dashboard/monitor references.
   - For Ruby apps, do not blindly remove `Xing::OpenTelemetry::Attribute.datadog_*`; there may be no Dash0 Ruby replacement. Check organization examples and SRE rules first.
   - Keep Datadog-specific browser code until the Dash0 web SDK migration is explicitly in scope.

3. **Apply Odyssey Dash0 baseline**
   - For `odyssey-helm-app`, create or reuse a shared values file similar to:

```yaml
version: "{{ requiredEnv "TAG" }}"
deploymentID: "{{ requiredEnv "DEPLOYMENT_VERSION" }}"

dash0:
  instrumentWorkloads: created-and-updated
  synchronizePersesDashboards: true
  synchronizePrometheusRules: true
  prometheusScrapingEnabled: true
  logCollectionEnabled: true

opentelemetry:
  service:
    name: <service-name>
```

   - Set `dash0.enabled: true` in exactly one release per namespace.
   - Include the shared Dash0 values in all releases so workload metadata is consistent.
   - Prefer `opentelemetry.service.name` and chart-generated `resource.opentelemetry.io/*` annotations over hand-composing `OTEL_RESOURCE_ATTRIBUTES`.
   - `filter` and `transform` are optional; add them only with a concrete reason.

4. **Handle deploy-time Jobs carefully**
   - Dash0 instrumentation can mutate Kubernetes Jobs by adding labels, env vars, init containers, and volumes.
   - Existing `Job.spec.template` is immutable, so Argo server-side diff may fail after instrumentation.
   - If deploy-time jobs are not important for observability, opt only those jobs out with pod annotation:

```yaml
podAnnotations:
  dash0.com/enable: "false"
```

   - Do not opt out long-running web/API/workers unless there is a specific compatibility issue.

5. **Decide Prometheus scope**
   - Search for Prometheus/Yabeda/OpenMetrics dependencies, `/metrics` routes, exporter ports, and `prometheus.io/*` annotations.
   - If the team confirms the service does not use Prometheus, record this and skip per-workload scrape config.
   - If Prometheus is used, confirm expected metric names, path, and port for each workload. Namespace-level `prometheusScrapingEnabled: true` is not enough to prove app metrics are scraped.

6. **Check SRE/SLO coverage**
   - Look for service definitions in `new-work/sre-rules` or the repo's SRE config.
   - HTTP/server SLOs may already have Dash0 coverage. Non-standard SLOs such as ActiveJob may remain Datadog-only until SRE supports translation.
   - Do not manually translate non-standard SLOs unless SRE guidance exists.

7. **Browser RUM decision**
   - Search for `@datadog/browser-rum`, frontend hooks, and bootstrap config.
   - Migrate to `@dash0/sdk-web` only when the team provides preview and production web ingest tokens, endpoint URL, env var names, and service naming.
   - Tokens embedded in browser JS must be ingest-only, dataset-scoped, environment-specific, and preferably restricted to web events.

## Post-Deploy Dash0 Validation

Run this phase after the infrastructure and test/preview deployment are applied. It applies when Dash0 is the migration backend or the requested validation target.

- Argo application is `Healthy` and cleanly `Synced`.
- `Dash0Monitoring/dash0-monitoring` exists and is synced in the namespace.
- Use dataset `odyssey-preview` for preview/test unless the user provides another dataset.
- Trigger real HTTP/API traffic, then query Dash0 for service traces.
- Query Dash0 for logs for the service and at least one worker if workers exist.
- Validate traces/logs include expected attributes where present:
  - `service.name`
  - `service.version`
  - `deployment.environment.name`
  - `deployment.id`
- Validate controlled or naturally occurring errors as error traces/logs when safe.
- Validate RED metrics or equivalent service metrics when available.
- Validate Prometheus/Yabeda app metrics only if the repo proves Prometheus is used.
- Validate AMQP, Kafka, Sidekiq, or other workers only after triggering real messages/jobs.
- Check Dash0 alert/check rules when SRE-generated checks are expected.
- Browser RUM events are validated only if the web SDK migration is in scope.

## Common Findings

- **Dash0 traffic visible but Argo sync unknown**: check for immutable deploy-time Job diffs caused by webhook mutation. Delete/prune completed jobs or opt deploy-time jobs out.
- **Metrics visible but only `k8s`, `container`, `envoy`, `istio`, `up`, or `scrape`**: platform metrics are present, but app Prometheus/Yabeda metrics are not proven.
- **No worker traces**: trigger real AMQP/Kafka/Sidekiq work; idle workers may not emit useful spans.
- **Datadog Ruby attributes still present**: acceptable if no Dash0-specific helper exists; verify with org examples and SRE rules.
- **Browser RUM still Datadog**: acceptable as a follow-up if Dash0 browser tokens are not ready.

## Completion Criteria

Call the backend/platform migration complete only when:

- preview Argo is clean,
- Dash0 receives traces, logs, and available service metrics for the primary service in the selected dataset,
- relevant long-running workers are validated or explicitly deferred,
- Prometheus is either validated or declared not applicable,
- known Datadog-only leftovers are documented with owners/follow-up decisions,
- production rollout risks and QA steps are written down.

Treat the validation as failed/blocking when preview is not healthy/synced, the service has no Dash0 traces after real traffic, service logs are absent, required workers cannot be validated without explanation, or resource attributes are missing in a way that breaks service identity or release tracking.

Leave these as follow-ups unless the user explicitly includes them in scope:

- Dash0 Browser RUM implementation,
- non-standard SLO translation,
- Datadog cleanup/removal,
- Prometheus scrape tuning for services that do not currently use Prometheus,
- worker telemetry that cannot be safely triggered in preview/test,
- alert/check rule gaps when SRE-generated Dash0 checks are not yet available,
- controlled error validation when it would create unsafe or noisy failures.
