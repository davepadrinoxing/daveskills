# Dependency Ecosystem Playbooks

Load only the sections that match the alert inventory. Prefer repository-documented commands over these generic examples.

## Bundler

1. Identify the `Gemfile` paired with each vulnerable `Gemfile.lock`. For each pair, record the nearest Ruby version declaration, the lockfile's `BUNDLED WITH` version, its platforms, its registry, and its own validation surface.
2. Inspect direct constraints with `bundle info`, `bundle list`, and the lockfile dependency graph.
3. Check the secure candidate gem's `required_ruby_version`. If it excludes the manifest's Ruby version, split the work into a runtime-upgrade remediation unit requiring user confirmation.
4. Run Bundler from the manifest directory with that graph's exact Ruby and Bundler versions. For example, use `bundle _2.4.1_ ...` when the lockfile records Bundler 2.4.1. Do not use the root application's Ruby or Bundler for every nested lockfile.
5. Compare the first patched version, the latest version in the installed release line, and Bundler's reported latest version. Keep framework gems on their current compatible major/minor line unless a broader upgrade is required and approved. When only a patch-line update is intended, prefer Bundler's restrictive flags:

   ```bash
   bundle update GEM --patch --strict
   ```

6. If the existing parent constraint permits the secure transitive gem, prefer a conservative lockfile update:

   ```bash
   bundle update GEM --conservative
   ```

   When `bundle update` is blocked while installing an unrelated native extension, resolve only the intended lockfile first:

   ```bash
   bundle lock --update GEM --conservative
   ```

   This is a resolver fallback, not validation. Still run the supported install/check and application tests separately, or report them as blocked.
7. For an alternate manifest, set `BUNDLE_GEMFILE` explicitly or run from its project directory according to repository guidance.
8. Keep the `Gemfile` unchanged when its existing constraints allow the secure transitive version.
9. When the constraint blocks the secure version, update the existing direct parent gem. Do not add the transitive gem to `Gemfile` solely to force resolution.
10. When no parent release provides a secure graph, investigate a maintained parent replacement or report the unit as blocked.
11. Run `bundle check`, the repository security audit, focused RSpec, and relevant build/start checks.
12. When the resolver adds an operator-only platform, remove it through Bundler rather than editing the lockfile:

    ```bash
    bundle lock --remove-platform PLATFORM
    ```

    Retain platform entries required by CI, release builds, or other developers. Review `GEM`, `PLATFORMS`, `DEPENDENCIES`, `RUBY VERSION`, and `BUNDLED WITH`; never add or remove dependency graph entries by hand.
13. If the bundle has no advisory scanner, run `bundler-audit` in a trusted disposable environment without adding it to the `Gemfile`. The scanner needs Git to update `ruby-advisory-db`. For a nested lockfile, pass the containing directory and lockfile name separately:

    ```bash
    bundle-audit check path/to/manifest --update --gemfile-lock Gemfile.lock
    ```

    Treat a database-download or registry failure as incomplete validation.
14. Do not change a registry to make resolution work or forward private registry credentials into an untrusted container. Use a trusted repository-supported environment, or stop and request the required source/credential decision.

## Yarn classic

1. Find the directory containing `package.json` and `yarn.lock`.
2. Inspect dependency paths with:

   ```bash
   yarn why PACKAGE
   yarn list --pattern PACKAGE
   ```

3. If every parent range permits a published secure transitive version, use the selective regeneration procedure below without changing `package.json`. Do not assume `yarn upgrade --pattern PACKAGE` refreshes an indirect dependency: verify the resulting graph; a successful no-op proves nothing about fixability.
4. If the range blocks it, update the existing direct parent to a supported release that permits the secure child.
5. If no secure child exists, update, replace, or remove the parent so the vulnerable package leaves the graph.
6. Never use `resolutions` or add the transitive package directly as a remediation.
7. Run `yarn install --frozen-lockfile` with normal lifecycle scripts, the repository audit command, focused tests, and build/lint checks appropriate to the package. Confirm that the frozen install leaves the lockfile unchanged.
8. Review `package.json` and `yarn.lock` together and reject unrelated lockfile churn.

When a parent requests an exact vulnerable transitive version, a lockfile-only replacement with a different version is not a valid Yarn graph. Upgrade the existing direct parent or report the blocker; never falsify the lockfile entry.

Private registries can block `yarn why`, install, or audit even when a lockfile is present. Report that as incomplete validation; do not alter registry configuration or credentials.

Check the effective audit endpoint against repository policy. Yarn Classic's audit implementation can use the public Yarn registry regardless of `--registry`; do not assume installation registry settings also control advisory requests. If that endpoint is disallowed, use an approved advisory scanner/API instead and report exactly which package versions were scanned. A targeted scan proves the selected versions against that advisory database, not the absence of vulnerabilities across the whole application graph.

### Selective regeneration of a Yarn Classic transitive dependency

Yarn Classic honors existing cached resolutions during installation. `--force` refetches packages; it does not unlock selected transitive versions. Deleting the entire lockfile causes broad drift. Instead, use a trusted updater or the bundled `scripts/refresh_yarn_classic.cjs` helper to invalidate only reviewed package selectors, then let the repository's pinned Yarn regenerate those entries under the original parent ranges. This follows [Dependabot's transitive updater](https://github.com/dependabot/dependabot-core/blob/main/npm_and_yarn/helpers/lib/yarn/subdependency-updater.ts), which parses the lockfile, removes selected cached entries, and invokes Yarn's resolver. The helper does not synthesize replacement versions, checksums, dependency ranges, or registry metadata.

Before applying:

- Inspect every installed release line and introducing parent. Select a published stable target for each line that satisfies all advisories, parent constraints, and runtime requirements. Check newly introduced child dependencies recursively: a parent can declare a compatible Node engine while its newest permitted child requires a newer runtime. Verify a version-specific registry record includes a tarball and integrity; an advisory threshold or an echoed version string alone does not prove publication.
- Record the checkout, branch, current diff, runtime, Yarn CLI, and approved registry. Keep pre-existing changes. The helper takes backups and restores the original manifest and lockfile on resolver failure, an unexpected selected version, or unrelated graph changes; `node_modules` can still change during an unsuccessful install.
- Install the official parser and semver checker in a disposable tools directory, never the application's manifest. Use the organization's approved registry and normal credential configuration. Installing these helper dependencies with npm does not convert the application graph to npm or create an application npm lockfile.

Example setup, replacing paths and the registry with repository-supported values:

```bash
REMEDIATION_TOOLS=$(mktemp -d)
npm install --prefix "$REMEDIATION_TOOLS" --ignore-scripts --no-audit --no-fund \
  --registry "$APPROVED_REGISTRY" @yarnpkg/lockfile@1.1.0 semver@7.7.2

# Read-only plan. Supply a reviewed exact target for every installed release line.
node /absolute/path/to/skill/scripts/refresh_yarn_classic.cjs \
  --repo /absolute/path/to/repository --tools "$REMEDIATION_TOOLS" \
  --target 'PACKAGE@REVIEWED_VERSION'

# Apply in the same checkout using its supported Node and Yarn CLI.
node /absolute/path/to/skill/scripts/refresh_yarn_classic.cjs \
  --repo /absolute/path/to/repository --tools "$REMEDIATION_TOOLS" \
  --target 'PACKAGE@REVIEWED_VERSION' --apply \
  --yarn-cli /absolute/path/to/yarn/bin/yarn.js --registry "$APPROVED_REGISTRY"
```

Repeat `--target` to batch packages or cover multiple installed release lines. The helper supports a single manifest graph, rejects direct dependencies, workspaces, selected packages hidden behind npm aliases, unsupported sources, incompatible targets, and existing resolutions affecting a selected package. It also rejects wildcard package-name resolutions whose effect needs a richer matcher. For workspaces, aliases, or unusual sources, use a verified aware updater or investigate parent updates; a helper capability limit is not a dependency-contract blocker.

The regeneration install suppresses lifecycle scripts to keep resolution separate from application validation; it does not suppress engine checks. Afterward, run a normal frozen install, inspect all installed occurrences with `yarn why`/`yarn list`, verify the advisory ranges, and run application checks. New child selectors are allowed only when reachable from the updated packages; review their versions, engines, and advisories too. Existing unrelated entries must remain semantically unchanged. If the helper rejects a required shared-child change, report and investigate that resolver consequence rather than relaxing the checks blindly or manually repairing the lockfile.

Verify repeatability: rerunning the helper with the same targets must be a no-op. An unexpected newer registry selection requires a new target review; do not silently accept it. Classify a failed registry operation, an incompatible parent range, and an ineffective CLI command separately in the handoff.

Selective invalidation resolves the newest matching registry version; this helper validates the selected target but does not force Yarn to choose an earlier release. If a new child requires a newer runtime, inspect earlier patched package/child releases before declaring a runtime migration mandatory. When an older supported secure graph exists but the updater cannot select it, record a resolver-selection limitation and investigate a verified version-aware updater or parent change. Do not bypass engine checks, fabricate lock entries, or describe the package as unfixable. Continue compatible units from the batch separately.

## Yarn Berry

Honor `packageManager`, `.yarnrc.yml`, workspaces, constraints, and checked-in Yarn artifacts.

- Use the repository-supported `yarn up` or workspace command to update.
- Use immutable install mode only to validate after generating the intended lockfile.
- Check all workspaces that can install the vulnerable package.
- Do not add a Yarn resolution to force a transitive remediation.

## npm

Pair `package.json` with the existing `package-lock.json` or `npm-shrinkwrap.json`.

1. Inspect paths with `npm explain PACKAGE` or `npm ls PACKAGE`.
2. Use a targeted lockfile update when the existing parent range permits the secure child.
3. Otherwise update the existing direct parent to a supported release that permits or removes the vulnerable child.
4. Do not add `overrides`, add the child directly, or generate a different package manager's lockfile.
5. Validate with the repository's `npm ci`, audit, focused tests, and build commands.

## pnpm

Pair `package.json` with `pnpm-lock.yaml` and honor the repository's workspace configuration.

1. Inspect every occurrence with `pnpm why PACKAGE`.
2. Use the workspace-aware update command selected by repository guidance.
3. Update only the lockfile when the parent range permits the secure child; otherwise update the existing direct parent.
4. Do not add `pnpm.overrides`, add the child directly, or generate another lockfile format.
5. Validate with the repository's frozen-lockfile install, audit, focused tests, and build commands.

## Bun

Pair `package.json` with the repository's existing `bun.lock` or legacy `bun.lockb`.

1. Inspect the installed path with the Bun version and commands pinned by the repository.
2. Use Bun to update the lockfile when the parent range permits the secure child.
3. Otherwise update the existing direct parent to a supported release that permits or removes the vulnerable child.
4. Do not use overrides or resolutions, add the child directly, hand-edit either lockfile format, or convert lockfile formats during an unrelated remediation.
5. Validate with a frozen lockfile install, the available audit command, focused tests, and the application build.

## GitHub Actions

- Identify every workflow reference affected by the advisory.
- Prefer immutable full commit SHAs when repository policy requires them, retaining a readable version comment.
- Review action release notes and permission changes.
- Validate workflow syntax and inspect the workflow diff carefully.
- Do not broaden `permissions`, expose secrets, or change trigger scope as part of a version bump.

## Docker

- Identify whether the vulnerable component comes from a base image, installed OS package, or copied application artifact.
- Prefer a supported patched base tag or digest consistent with repository policy.
- Rebuild and rescan the image; a textual Dockerfile change alone is not proof of remediation.
- Separate runtime-base upgrades from unrelated application dependency batches when rollback or validation differs.

## Other ecosystems

Use the repository's existing package manager and lockfile. Apply the same invariants:

- trace the vulnerable package to a direct parent;
- satisfy every vulnerable range;
- avoid hand-editing generated dependency graphs;
- preserve checksums and reproducibility;
- run ecosystem-native graph, audit, install, and test commands;
- document incomplete validation and residual risk.
