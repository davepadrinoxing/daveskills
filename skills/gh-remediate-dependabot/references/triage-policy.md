# Dependabot Triage Policy

Use this policy to prioritize remediation units and decide batch boundaries. Adapt service-level targets to repository or organization policy when one exists.

## Prioritization

Evaluate:

- advisory severity and CVSS;
- runtime, development, build, test, documentation, or deployment exposure;
- direct, transitive, unknown, or inconclusive relationship;
- public reachability, sensitive-data access, privilege, and vulnerable-function usage;
- EPSS and known exploitation;
- alert age and whether a supported patch exists;
- compatibility cost and compensating controls.

Suggested response targets:

- critical or known-exploited: begin immediately and isolate from the routine weekly batch;
- high runtime: prioritize within three business days;
- other patched alerts: handle in the next weekly campaign;
- no patched release: investigate reachability, parent upgrades, replacement, or mitigation and assign a human owner.

Treat these as defaults, not permission to delay a demonstrably exploitable issue.

## Fix availability

For several advisories affecting one installed package, satisfy every vulnerable range. The effective target is not necessarily the lexically highest version because ecosystems use different version semantics.

- Verify the selected version against every advisory.
- Account for multiple installed major lines separately.
- Treat inventory groups as candidates until package-manager graph inspection confirms the installed occurrences and parent paths.
- Do not claim a fix when only one vulnerable occurrence was updated.
- Do not dismiss an unpatched alert merely because its severity is low.

## Batch boundaries

Prefer one campaign with multiple coherent pull requests over one oversized pull request.

Good batch candidates:

- compatible patch/minor changes in one ecosystem;
- packages in the same manifest with the same test surface;
- several advisories closed by one dependency update;
- identical package updates across manifests when they share ownership and validation.

Separate:

- major or framework upgrades;
- runtime and tooling changes with different rollback needs;
- dependency replacements;
- generated documentation dependencies from application runtime dependencies when they deploy differently;
- changes owned or released by different teams.

## Durable transitive remediation

Use the dependency contract to select the remediation:

1. If the existing parent range permits a secure child, update only the lockfile with the repository's package manager.
2. If the parent range excludes the secure child, update the existing direct parent to a supported release that permits it.
3. If the child has no patched release, update, replace, or remove the direct parent so the vulnerable package leaves the graph.
4. If no supported secure graph exists, report the remediation as blocked and document mitigations and ownership.

Do not use overrides, resolutions, newly direct transitive constraints, or hand-edited lockfile entries. These approaches bypass the introducing parent's declared compatibility and turn an alert into locally maintained security debt rather than a long-term fix.

## Human decisions

Require explicit human direction before:

- accepting risk or dismissing an alert;
- merging or enabling auto-merge;
- changing security or Dependabot settings;
- introducing a new direct dependency;
- replacing a runtime dependency;
- taking a breaking/major upgrade;
- weakening or skipping required validation.
