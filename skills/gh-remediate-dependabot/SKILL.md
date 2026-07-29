---
name: gh-remediate-dependabot
description: Audit, triage, batch, remediate, and document GitHub Dependabot alerts across repositories and package ecosystems. Use when Codex needs to inspect open Dependabot vulnerabilities, explain why Dependabot cannot create a fix, prepare a weekly vulnerability-remediation batch, update vulnerable direct or transitive dependencies, validate lockfile changes, or create a reviewable security pull request.
---

# Dependabot Remediation

Build a traceable remediation campaign from GitHub alerts. Keep audit mode read-only, use repository-native package managers for fixes, and preserve human control over publishing and risk acceptance.

Resolve this skill's directory from the loaded `SKILL.md` and verify that both bundled scripts exist before starting. Do not assume the skill is copied into the target repository. If the user provides a central skill path that is not registered in the active session, state that limitation and use the explicitly provided copy as the workflow source; installation and session registration remain separate developer actions.

## Choose the operating mode

- Use **audit mode** by default. Inspect alerts, dependency paths, existing pull requests, and repository guidance without changing files or external state.
- Use **prepare mode** only when the user asks to fix, remediate, update, or prepare changes. Modify local dependency manifests and lockfiles, validate them, and leave the resulting changes unstaged and uncommitted for developer review.
- Use **publish mode** only when the user explicitly asks to create or update a pull request. Prefer a draft pull request unless the user requests otherwise.
- Require separate explicit approval to merge, dismiss an alert, accept risk, change Dependabot/security settings, or modify registry credentials.

## Resolve the target repository

Accept the target repository as any of:

- a local checkout path;
- `OWNER/REPOSITORY`;
- a GitHub repository or Dependabot-alert URL.

Normalize GitHub inputs to `OWNER/REPOSITORY`. When no target is supplied, use the current checkout only if its remote identifies one repository unambiguously; otherwise ask the user which repository to inspect. Accept multiple repositories for audit campaigns, but prepare and publish changes against one confirmed local checkout at a time.

Before any write, confirm that the checkout remote matches the requested repository and state the target and base branch. Never apply one repository's alert data to another checkout.

Work in the confirmed local checkout path supplied by the developer so changes are immediately visible in their editor and normal `git diff`. Do not use a temporary or hidden worktree merely to separate remediation batches. Prefer creating or switching to a dedicated local branch in that checkout and leave the prepared diff uncommitted. If pre-existing changes, an active branch, or Git worktree constraints make isolation necessary, explain the constraint and obtain confirmation before using another worktree; always surface its path and offer to transfer the uncommitted diff back before handoff.

## Load repository context

1. Read the applicable `AGENTS.md` files and repository-local setup, testing, style, and commit guidance.
2. Run `git status --short`. Preserve unrelated and pre-existing changes.
3. Find dependency manifests, lockfiles, `.github/dependabot.yml`, runtime-version files, and package-manager configuration.
4. Build an execution matrix for every manifest/lockfile pair: working directory, runtime version, package-manager version, registry/configuration, affected surface, and validation commands. Treat separate manifests as independent graphs even when they use the same ecosystem; never regenerate all lockfiles with the root toolchain by default.
5. Compare every discovered dependency graph with `.github/dependabot.yml`. Run the bundled coverage checker from the repository root and report graphs without scheduled updates:

   ```bash
   python3 /absolute/path/to/gh-remediate-dependabot/scripts/dependabot_config_coverage.py
   ```

   Treat missing coverage as a maintenance gap, not permission to edit Dependabot configuration. Changing security settings still requires explicit approval.
6. Read [references/triage-policy.md](references/triage-policy.md).
7. Read [references/ecosystem-playbooks.md](references/ecosystem-playbooks.md) only for ecosystems present in the alert inventory.

## Inventory the alerts

Resolve the bundled script relative to this `SKILL.md`, then run it from the target repository root. Do not assume the skill is stored inside the target repository:

```bash
python3 /absolute/path/to/gh-remediate-dependabot/scripts/dependabot_inventory.py
```

Pass one or more repositories when auditing outside the current checkout:

```bash
python3 /absolute/path/to/gh-remediate-dependabot/scripts/dependabot_inventory.py \
  --repo OWNER/REPOSITORY \
  --repo OWNER/ANOTHER-REPOSITORY
```

Use `--format json` when another tool needs structured output. The script performs read-only GitHub API calls through the authenticated `gh` CLI and groups alerts into candidate remediation units by repository, ecosystem, manifest, package, scope, dependency relationship, and patched major line.

Also inspect:

- existing Dependabot and manual dependency pull requests;
- errors shown for alerts where Dependabot could not create an update;
- the dependency path from each vulnerable package to a direct dependency;
- all vulnerable ranges and first patched versions in a remediation unit.

Treat existing pull requests as overlap information only. Never remove, defer, or skip an
alert merely because Dependabot or a developer already opened a pull request for it. Assume
the local remediation campaign owns every open alert in scope unless the user explicitly
narrows that scope. Do not close, supersede, or otherwise modify those pull requests without
an explicit request.

Do not equate alert count or candidate-unit count with required version changes. One package update may close several advisories or candidate units, while the same package in multiple manifests or installed version lines may require separate changes. Confirm the installed graph before finalizing batches.

Treat a published patched version as actionable only after checking its runtime and package-manager requirements against the affected manifest's execution matrix. When the first secure release requires a newer runtime or package manager, classify and split it as a runtime/toolchain upgrade requiring user confirmation; do not describe it as a lockfile-only fix.

## Select secure target versions

For each remediation unit, distinguish:

- the first version patched against every advisory;
- the latest compatible version in the current supported release line;
- the package manager's unconstrained latest version.

Prefer the latest maintained patch in the current compatible release line that satisfies every advisory. Do not let a generic update command silently select a new major or framework line merely because it is the newest version in the registry. Use package-manager-native patch/minor constraints when available, and split any required major upgrade into a separate unit requiring confirmation.

## Build remediation units

Classify each grouped unit as one of:

- `urgent-patch`: a critical alert with a patch;
- `priority-patch`: a high runtime alert with a patch;
- `weekly-batch`: a patch is available and the change can enter routine remediation;
- `manual-investigation`: no patched version exists.

Refine priority using exposure, reachability, exploitability, EPSS, age, public-facing use, sensitive-data access, and compensating controls. Never use severity or EPSS alone to accept risk.

For every unit, choose the first durable strategy that produces a valid dependency graph:

1. update the vulnerable direct dependency;
2. perform a targeted lockfile update when the existing parent constraint already permits the secure transitive version;
3. update the direct parent to a supported release whose constraint permits the secure transitive version;
4. update, replace, or remove the direct parent when the vulnerable transitive package has no patched release;
5. report the unit as blocked when no supported secure graph exists.

Never add an override, resolution, or new direct constraint to force a transitive version. Those mechanisms bypass the parent contract and create indefinite security debt. Do not invent a fixed version for an unpatched advisory or claim a blocked unit is remediated. Report the remaining exposure, available mitigation, and decision needed from the human owner.

## Plan safe batches

Treat a weekly run as one campaign, not necessarily one pull request.

Combine units when they:

- share an ecosystem, manifest set, validation matrix, and rollback path;
- require patch or compatible minor updates;
- avoid unrelated lockfile churn;
- can be explained and reverted coherently.

Split units when they:

- cross package ecosystems unless the repository explicitly prefers one combined dependency PR;
- require major, framework, runtime, or package-manager upgrades;
- replace or remove dependencies;
- have incompatible constraints, materially different risk, or different owners;
- make the diff too large to review confidently.

State the proposed batches before editing when the campaign is complex.

## Prepare fixes

1. Start from the intended base branch and a clean understanding of pre-existing changes.
2. Use the repository's package manager. Never switch package managers.
3. Identify every manifest/lockfile pair affected by the remediation. Common pairs include `Gemfile`/`Gemfile.lock`, `package.json`/`package-lock.json`, `package.json`/`npm-shrinkwrap.json`, `package.json`/`yarn.lock`, `package.json`/`pnpm-lock.yaml`, and `package.json`/`bun.lock` or `bun.lockb`. Never create a second package manager's lockfile.
4. Run each update with the runtime and package-manager version recorded for that manifest. Use the repository's supported container or install the exact toolchain when necessary; do not silently resolve an alternate lockfile with the root application's toolchain.
5. Prefer a lockfile-only update for a transitive dependency when the existing manifest constraints permit the secure version. Leave `Gemfile`, `package.json`, and equivalent manifests unchanged in that case.
6. When the parent constraint excludes the secure transitive version, update the existing direct parent to the lowest-risk supported release line that permits a secure graph, normally selecting its latest patch. A manifest change is required in this case; adding the vulnerable transitive package as a direct dependency is not a substitute.
7. When no patched transitive release exists, find a supported parent release that removes or replaces it. Treat a parent replacement, removal, or breaking upgrade as a separate remediation unit requiring user confirmation.
8. If no durable supported path exists, stop preparing that unit and report it as blocked. Do not create an override, resolution, direct transitive pin, or hand-edited lockfile workaround.
9. Use package-manager commands to update manifests and lockfiles. Never hand-edit generated lockfile dependency graphs or record a version that violates its parent constraint.
10. Target a version that satisfies every advisory in the remediation unit. Prefer the lowest-risk maintained release line and its latest patch unless repository policy selects another supported version.
11. Capture the installed vulnerable version and introducing parent path before the update, then inspect the installed graph again afterward. Verify every occurrence against every patched threshold; text appearing in a lockfile is not sufficient evidence.
12. Review the complete diff and remove unrelated lockfile drift, including platform, workspace, and conditional-dependency entries introduced only by the operator's machine. Use the package manager's native cleanup command when available; never hand-edit a generated dependency graph to hide resolver drift.
13. Classify secondary lockfile changes as either required resolver consequences or unrelated churn. Keep required child/metadata changes and explain their parent relationship; revert unrelated changes with the package manager rather than editing checksums or graph entries manually.
14. Stop with the validated changes unstaged and uncommitted unless the user explicitly requested a commit or pull request. Report the checkout path, branch, changed files, and validation results so the developer can review the diff locally before deciding whether to publish it.

Adding a new direct dependency, changing registries or credentials, migrating package managers, or performing a major upgrade requires user confirmation unless it was already explicitly requested.

## Validate

Run validation in proportion to the affected dependency:

1. package-manager lockfile/install consistency;
2. installed-version or dependency-path inspection;
3. the repository's vulnerability check when available;
4. an independent ecosystem advisory scan when practical, run without adding the scanner to the application manifest; use a trusted disposable environment if the repository does not include a scanner;
5. focused tests for affected runtime or tooling behavior;
6. an application-level smoke, build, or test command proving the app still works with the updated graph;
7. build, lint, or full tests when the dependency affects those surfaces;
8. `git diff --check`, `git diff --stat`, and focused manifest/lockfile review.

Treat network, registry, and audit failures as incomplete validation. Record the exact blocked command; do not claim the alert is fixed merely because the lockfile text changed.

Do not create even a draft remediation pull request until the application-level check passes. If local environment or external infrastructure blocks that check, remain in prepare mode and ask the user whether to proceed with explicitly incomplete validation.

Dependabot alerts normally remain open until the secure change reaches the default branch and GitHub rescans it. Before merge, report alerts expected to close rather than claiming closure.

## Produce review evidence

For every prepared batch or pull request, include:

| Field | Required content |
|---|---|
| Alerts | Dependabot alert numbers plus GHSA/CVE identifiers |
| Dependency path | Direct dependency or parent chain introducing the package |
| Change | Manifest, old version or range, and selected secure version |
| Rationale | Why the strategy and batch boundary are safe |
| Validation | Commands run with pass, fail, or blocked status |
| Automation coverage | Whether Dependabot schedules cover every affected manifest directory |
| Remaining risk | Unpatched, deferred, or intentionally separated units |

Use the repository pull-request template and naming conventions. Do not leave placeholder ticket, testing, or QA sections in a published pull request.

Produce a before/after table grouped by manifest and package. Include the vulnerable installed version, introducing parent, selected secure version, alert numbers, GHSA/CVE identifiers, and whether all known patched thresholds are satisfied. Describe alerts as expected to close until GitHub rescans the merged default branch.

At the end of every run, also include this compact summary before the detailed evidence:

| Package | Before | After | Alerts expected to close |
|---|---:|---:|---:|
| `example-package` | `1.2.3` | `1.2.7` | 3 |

Count unique Dependabot alert numbers expected to close from each package change; do not
double-count advisories grouped into multiple candidate units. In audit mode, use the selected
secure target as `After`; use `blocked` or `not selected` when no valid target exists. Keep
scanner-only advisories in the detailed evidence and remaining-risk section unless GitHub has
assigned them Dependabot alert numbers.

## Guardrails

- Never expose tokens, private-registry credentials, or decrypted configuration.
- Never modify production, preview, or deployment data as part of dependency remediation.
- Never dismiss or reopen alerts, accept risk, merge, deploy, or enable auto-merge without an explicit user request.
- Never change `.github/dependabot.yml` merely because the coverage checker reports a gap; present the gap and request approval for the configuration change.
- Never hide failing validation by splitting or rewriting history.
- Never force a vulnerable transitive dependency into a nominally safe version without checking the parent contract and installed graph.
- Never introduce overrides, resolutions, or new direct pins for transitive vulnerabilities; pursue an upstream-aligned graph or report the remediation as blocked.
