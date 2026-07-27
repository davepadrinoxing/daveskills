#!/usr/bin/env python3
"""Create a read-only, grouped inventory of GitHub Dependabot alerts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable


SEVERITY_RANK = {"unknown": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class InventoryError(RuntimeError):
    """Raised when the inventory cannot be collected safely."""


def run_gh(arguments: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise InventoryError("GitHub CLI `gh` is not installed or not on PATH.") from error

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown GitHub CLI error"
        raise InventoryError(detail)
    return result.stdout


def infer_repository() -> str:
    repository = run_gh(
        ["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]
    ).strip()
    if not repository or "/" not in repository:
        raise InventoryError("Could not infer OWNER/REPOSITORY from the current checkout.")
    return repository


def validate_repository(repository: str) -> str:
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise InventoryError(
            f"Invalid repository '{repository}'; expected OWNER/REPOSITORY."
        )
    return repository


def parse_json_stream(payload: str) -> list[dict[str, Any]]:
    """Parse one JSON array or multiple arrays emitted by `gh api --paginate`."""
    decoder = json.JSONDecoder()
    position = 0
    documents: list[Any] = []

    while position < len(payload):
        while position < len(payload) and payload[position].isspace():
            position += 1
        if position >= len(payload):
            break
        try:
            document, position = decoder.raw_decode(payload, position)
        except json.JSONDecodeError as error:
            raise InventoryError(f"GitHub returned invalid JSON: {error}") from error
        documents.append(document)

    alerts: list[dict[str, Any]] = []
    for document in documents:
        if isinstance(document, list):
            alerts.extend(item for item in document if isinstance(item, dict))
        elif isinstance(document, dict):
            alerts.append(document)
        else:
            raise InventoryError("GitHub returned an unexpected Dependabot response shape.")
    return alerts


def fetch_alerts(repository: str, state: str) -> list[dict[str, Any]]:
    endpoint = (
        f"repos/{repository}/dependabot/alerts"
        f"?state={state}&per_page=100&sort=created&direction=desc"
    )
    return parse_json_stream(run_gh(["api", "--paginate", endpoint]))


def severity(alert: dict[str, Any]) -> str:
    advisory = alert.get("security_advisory") or {}
    vulnerability = alert.get("security_vulnerability") or {}
    value = advisory.get("severity") or vulnerability.get("severity") or "unknown"
    return str(value).lower()


def cvss_score(alert: dict[str, Any]) -> float | None:
    advisory = alert.get("security_advisory") or {}
    scores: list[float] = []
    legacy = advisory.get("cvss") or {}
    if isinstance(legacy.get("score"), (int, float)):
        scores.append(float(legacy["score"]))
    for value in (advisory.get("cvss_severities") or {}).values():
        if isinstance(value, dict) and isinstance(value.get("score"), (int, float)):
            scores.append(float(value["score"]))
    return max(scores) if scores else None


def epss_percentage(alert: dict[str, Any]) -> float | None:
    epss = (alert.get("security_advisory") or {}).get("epss") or {}
    value = epss.get("percentage")
    return float(value) if isinstance(value, (int, float)) else None


def patched_version(alert: dict[str, Any]) -> str | None:
    version = (alert.get("security_vulnerability") or {}).get("first_patched_version")
    if isinstance(version, dict) and version.get("identifier"):
        return str(version["identifier"])
    return None


def natural_key(value: str) -> list[tuple[int, Any]]:
    parts = re.split(r"(\d+)", value)
    return [
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in parts
        if part
    ]


def patched_major_line(version: str | None) -> str:
    if not version:
        return "unpatched"
    match = re.match(r"^[^0-9]*(\d+)", version)
    return f"major-{match.group(1)}" if match else f"version-{version}"


def highest_severity(values: Iterable[str]) -> str:
    return max(values, key=lambda value: SEVERITY_RANK.get(value, 0), default="unknown")


def classify_priority(group: dict[str, Any]) -> str:
    if not group["fix_available"]:
        return "manual-investigation"
    if group["severity"] == "critical":
        return "urgent-patch"
    if group["severity"] == "high" and group["scope"] == "runtime":
        return "priority-patch"
    return "weekly-batch"


def normalize_alert(repository: str, alert: dict[str, Any]) -> dict[str, Any]:
    dependency = alert.get("dependency") or {}
    package = dependency.get("package") or {}
    advisory = alert.get("security_advisory") or {}
    vulnerability = alert.get("security_vulnerability") or {}
    return {
        "repository": repository,
        "number": alert.get("number"),
        "package": package.get("name") or "unknown",
        "ecosystem": package.get("ecosystem") or "unknown",
        "manifest": dependency.get("manifest_path") or "unknown",
        "scope": dependency.get("scope") or "unknown",
        "relationship": dependency.get("relationship") or "unknown",
        "severity": severity(alert),
        "cvss": cvss_score(alert),
        "epss": epss_percentage(alert),
        "ghsa": advisory.get("ghsa_id"),
        "cve": advisory.get("cve_id"),
        "summary": advisory.get("summary"),
        "vulnerable_range": vulnerability.get("vulnerable_version_range"),
        "patched_version": patched_version(alert),
        "created_at": alert.get("created_at"),
        "html_url": alert.get("html_url"),
    }


def group_alerts(repository_alerts: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for repository, alerts in repository_alerts.items():
        for alert in alerts:
            item = normalize_alert(repository, alert)
            key = (
                item["repository"],
                item["ecosystem"],
                item["manifest"],
                item["package"],
                item["scope"],
                item["relationship"],
                patched_major_line(item["patched_version"]),
            )
            buckets[key].append(item)

    groups: list[dict[str, Any]] = []
    for key, alerts in buckets.items():
        (
            repository,
            ecosystem,
            manifest,
            package,
            scope,
            relationship,
            version_line,
        ) = key
        patches = sorted(
            {item["patched_version"] for item in alerts if item["patched_version"]},
            key=natural_key,
        )
        cvss_values = [item["cvss"] for item in alerts if item["cvss"] is not None]
        epss_values = [item["epss"] for item in alerts if item["epss"] is not None]
        created_values = [item["created_at"] for item in alerts if item["created_at"]]
        group = {
            "repository": repository,
            "ecosystem": ecosystem,
            "manifest": manifest,
            "package": package,
            "scope": scope,
            "relationship": relationship,
            "version_line": version_line,
            "severity": highest_severity(item["severity"] for item in alerts),
            "max_cvss": max(cvss_values) if cvss_values else None,
            "max_epss": max(epss_values) if epss_values else None,
            "fix_available": all(item["patched_version"] for item in alerts),
            "patched_versions": patches,
            "oldest_alert": min(created_values) if created_values else None,
            "alert_numbers": sorted(
                (item["number"] for item in alerts if isinstance(item["number"], int))
            ),
            "advisories": [
                {
                    field: item[field]
                    for field in (
                        "number",
                        "ghsa",
                        "cve",
                        "severity",
                        "vulnerable_range",
                        "patched_version",
                        "summary",
                        "html_url",
                    )
                }
                for item in sorted(alerts, key=lambda value: value["number"] or 0)
            ],
        }
        group["priority"] = classify_priority(group)
        groups.append(group)

    priority_order = {
        "urgent-patch": 0,
        "priority-patch": 1,
        "manual-investigation": 2,
        "weekly-batch": 3,
    }
    return sorted(
        groups,
        key=lambda group: (
            group["repository"],
            priority_order[group["priority"]],
            -SEVERITY_RANK.get(group["severity"], 0),
            group["ecosystem"],
            group["manifest"],
            group["package"].lower(),
        ),
    )


def summary(repository_alerts: dict[str, list[dict[str, Any]]], groups: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repositories": len(repository_alerts),
        "alerts": sum(len(alerts) for alerts in repository_alerts.values()),
        "remediation_units": len(groups),
        "fixable_units": sum(1 for group in groups if group["fix_available"]),
        "manual_investigation_units": sum(
            1 for group in groups if not group["fix_available"]
        ),
    }


def markdown_escape(value: Any) -> str:
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def risk_summary(group: dict[str, Any]) -> str:
    values: list[str] = []
    if group["max_cvss"] is not None:
        values.append(f"CVSS {group['max_cvss']:g}")
    if group["max_epss"] is not None:
        values.append(f"EPSS {group['max_epss'] * 100:.3g}%")
    return "; ".join(values) or "—"


def advisory_summary(group: dict[str, Any]) -> str:
    identifiers: list[str] = []
    for advisory in group["advisories"]:
        for field in ("ghsa", "cve"):
            value = advisory.get(field)
            if value and value not in identifiers:
                identifiers.append(value)
    return ", ".join(identifiers) or "—"


def render_markdown(
    repository_alerts: dict[str, list[dict[str, Any]]],
    groups: list[dict[str, Any]],
) -> str:
    lines = ["# Dependabot inventory", ""]
    total = summary(repository_alerts, groups)
    alert_noun = "alert" if total["alerts"] == 1 else "alerts"
    form_verb = "forms" if total["alerts"] == 1 else "form"
    unit_noun = "unit" if total["remediation_units"] == 1 else "units"
    fixable_noun = "unit has" if total["fixable_units"] == 1 else "units have"
    manual_verb = (
        "requires"
        if total["manual_investigation_units"] == 1
        else "require"
    )
    lines.append(
        f"{total['alerts']} {alert_noun} {form_verb} "
        f"{total['remediation_units']} remediation "
        f"{unit_noun}; {total['fixable_units']} {fixable_noun} patches and "
        f"{total['manual_investigation_units']} {manual_verb} manual investigation."
    )

    for repository in repository_alerts:
        repository_groups = [
            group for group in groups if group["repository"] == repository
        ]
        lines.extend(["", f"## {repository}", ""])
        if not repository_groups:
            lines.append("No matching Dependabot alerts.")
            continue
        lines.extend(
            [
                "| Priority | Ecosystem | Manifest | Package | Exposure | Relationship | Severity | Risk | Alerts | Advisories | Patched versions |",
                "|---|---|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for group in repository_groups:
            alerts = ", ".join(f"#{number}" for number in group["alert_numbers"]) or "—"
            patches = ", ".join(group["patched_versions"]) or "none"
            values = [
                group["priority"],
                group["ecosystem"],
                group["manifest"],
                group["package"],
                group["scope"],
                group["relationship"],
                group["severity"],
                risk_summary(group),
                alerts,
                advisory_summary(group),
                patches,
            ]
            lines.append("| " + " | ".join(markdown_escape(value) for value in values) + " |")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch and group Dependabot alerts without changing GitHub or repository state."
    )
    parser.add_argument(
        "--repo",
        action="append",
        dest="repositories",
        metavar="OWNER/REPOSITORY",
        help="Repository to inspect; repeat for multiple repositories. Defaults to the current checkout.",
    )
    parser.add_argument(
        "--state",
        choices=("open", "fixed", "dismissed", "auto_dismissed"),
        default="open",
        help="Dependabot alert state to fetch (default: open).",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format (default: markdown).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repositories = [
            validate_repository(repository)
            for repository in dict.fromkeys(args.repositories or [infer_repository()])
        ]
        repository_alerts = {
            repository: fetch_alerts(repository, args.state)
            for repository in repositories
        }
        groups = group_alerts(repository_alerts)
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "summary": summary(repository_alerts, groups),
                        "groups": groups,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(render_markdown(repository_alerts, groups))
    except InventoryError as error:
        print(f"dependabot inventory failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
