# Dependency Ecosystem Playbooks

Load only the sections that match the alert inventory. Prefer repository-documented commands over these generic examples.

## Bundler

1. Identify the `Gemfile` paired with each vulnerable `Gemfile.lock`. For each pair, record the nearest Ruby version declaration, the lockfile's `BUNDLED WITH` version, its platforms, its registry, and its own validation surface.
2. Inspect direct constraints with `bundle info`, `bundle list`, and the lockfile dependency graph.
3. Check the secure candidate gem's `required_ruby_version`. If it excludes the manifest's Ruby version, split the work into a runtime-upgrade remediation unit requiring user confirmation.
4. Run Bundler from the manifest directory with that graph's exact Ruby and Bundler versions. For example, use `bundle _2.4.1_ ...` when the lockfile records Bundler 2.4.1. Do not use the root application's Ruby or Bundler for every nested lockfile.
5. If the existing parent constraint permits the secure transitive gem, prefer a conservative lockfile update:

   ```bash
   bundle update GEM --conservative
   ```

   When `bundle update` is blocked while installing an unrelated native extension, resolve only the intended lockfile first:

   ```bash
   bundle lock --update GEM --conservative
   ```

   This is a resolver fallback, not validation. Still run the supported install/check and application tests separately, or report them as blocked.
6. For an alternate manifest, set `BUNDLE_GEMFILE` explicitly or run from its project directory according to repository guidance.
7. Keep the `Gemfile` unchanged when its existing constraints allow the secure transitive version.
8. When the constraint blocks the secure version, update the existing direct parent gem. Do not add the transitive gem to `Gemfile` solely to force resolution.
9. When no parent release provides a secure graph, investigate a maintained parent replacement or report the unit as blocked.
10. Run `bundle check`, the repository security audit, focused RSpec, and relevant build/start checks.
11. Review the `GEM`, `PLATFORMS`, `DEPENDENCIES`, `RUBY VERSION`, and `BUNDLED WITH` sections. Reject unrelated platform or conditional dependency drift; never add top-level lockfile dependencies by hand.
12. Do not change a registry to make resolution work or forward private registry credentials into an untrusted container. Use a trusted repository-supported environment, or stop and request the required source/credential decision.

## Yarn classic

1. Find the directory containing `package.json` and `yarn.lock`.
2. Inspect dependency paths with:

   ```bash
   yarn why PACKAGE
   yarn list --pattern PACKAGE
   ```

3. If the parent range permits the secure transitive version, refresh that package through Yarn without changing `package.json`.
4. If the range blocks it, update the existing direct parent to a supported release that permits the secure child.
5. If no secure child exists, update, replace, or remove the parent so the vulnerable package leaves the graph.
6. Never use `resolutions` or add the transitive package directly as a remediation.
7. Run `yarn install`, the repository audit command, focused tests, and build/lint checks appropriate to the package.
8. Review `package.json` and `yarn.lock` together and reject unrelated lockfile churn.

When a parent requests an exact vulnerable transitive version, a lockfile-only replacement with a different version is not a valid Yarn graph. Upgrade the existing direct parent or report the blocker; never falsify the lockfile entry.

Private registries can block `yarn why`, install, or audit even when a lockfile is present. Report that as incomplete validation; do not alter registry configuration or credentials.

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
