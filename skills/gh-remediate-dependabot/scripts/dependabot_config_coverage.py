#!/usr/bin/env python3
"""Report dependency graphs not covered by local Dependabot update schedules."""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


EXCLUDED_DIRECTORIES = {
    ".bundle",
    ".git",
    ".ruby-lsp",
    ".terraform",
    ".venv",
    "node_modules",
    "vendor",
}

MANIFEST_ECOSYSTEMS = {
    "Gemfile.lock": "bundler",
    "bun.lock": "bun",
    "bun.lockb": "bun",
    "Cargo.lock": "cargo",
    "composer.lock": "composer",
    "deno.lock": "deno",
    "go.mod": "gomod",
    "gradle.lockfile": "gradle",
    "mix.lock": "mix",
    "npm-shrinkwrap.json": "npm",
    "package-lock.json": "npm",
    "Package.resolved": "swift",
    "packages.lock.json": "nuget",
    "Pipfile.lock": "pip",
    "pnpm-lock.yaml": "npm",
    "poetry.lock": "pip",
    "pubspec.lock": "pub",
    "uv.lock": "uv",
    "yarn.lock": "npm",
}

COMPOSE_FILENAMES = {
    "compose.yaml",
    "compose.yml",
    "docker-compose.yaml",
    "docker-compose.yml",
}


@dataclass(frozen=True)
class DependencySurface:
    ecosystem: str
    directory: str
    manifest: str
    supported: bool = True
    note: str | None = None


@dataclass
class UpdateEntry:
    ecosystem: str | None
    directories: list[str]


def normalize_directory(value: str) -> str:
    value = value.strip()
    if value in {"", "."}:
        return "/"
    if value in {"**/*", "/**/*"}:
        return "**/*"
    normalized = "/" + value.strip("/")
    return normalized if normalized != "" else "/"


def directory_for(path: Path, root: Path) -> str:
    relative = path.parent.relative_to(root).as_posix()
    return "/" if relative == "." else f"/{relative}"


def is_excluded(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in EXCLUDED_DIRECTORIES for part in parts)


def add_surface(
    surfaces: set[DependencySurface],
    root: Path,
    path: Path,
    ecosystem: str,
    *,
    supported: bool = True,
    note: str | None = None,
) -> None:
    surfaces.add(
        DependencySurface(
            ecosystem=ecosystem,
            directory=directory_for(path, root),
            manifest=path.relative_to(root).as_posix(),
            supported=supported,
            note=note,
        )
    )


def discover_surfaces(root: Path) -> list[DependencySurface]:
    surfaces: set[DependencySurface] = set()
    workflows_found = False

    for path in root.rglob("*"):
        if not path.is_file() or is_excluded(path, root):
            continue

        relative = path.relative_to(root)
        name = path.name

        ecosystem = MANIFEST_ECOSYSTEMS.get(name)
        if ecosystem:
            if name == "bun.lockb":
                add_surface(
                    surfaces,
                    root,
                    path,
                    ecosystem,
                    supported=False,
                    note="Legacy bun.lockb is not supported by Dependabot; migrate with Bun.",
                )
            else:
                add_surface(surfaces, root, path, ecosystem)
            continue

        if name == "pom.xml":
            add_surface(surfaces, root, path, "maven")
        elif name in {"build.gradle", "build.gradle.kts"}:
            add_surface(surfaces, root, path, "gradle")
        elif name.startswith("Dockerfile"):
            add_surface(surfaces, root, path, "docker")
        elif name in COMPOSE_FILENAMES:
            add_surface(surfaces, root, path, "docker-compose")
        elif name == "Chart.yaml":
            add_surface(surfaces, root, path, "helm")
        elif name == ".pre-commit-config.yaml":
            add_surface(surfaces, root, path, "pre-commit")
        elif name == ".terraform.lock.hcl":
            add_surface(surfaces, root, path, "terraform")
        elif name.endswith((".csproj", ".fsproj", ".vbproj", ".vcxproj", ".nuspec")):
            add_surface(surfaces, root, path, "nuget")
        elif (
            len(relative.parts) >= 3
            and relative.parts[:2] == (".github", "workflows")
            and path.suffix in {".yml", ".yaml"}
        ):
            workflows_found = True

    if workflows_found:
        surfaces.add(
            DependencySurface(
                ecosystem="github-actions",
                directory="/",
                manifest=".github/workflows",
            )
        )

    return sorted(
        surfaces,
        key=lambda item: (item.ecosystem, item.directory, item.manifest),
    )


def scalar(value: str) -> str:
    value = value.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].rstrip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def parse_key_value(value: str) -> tuple[str, str] | None:
    if ":" not in value:
        return None
    key, raw_value = value.split(":", 1)
    return key.strip(), scalar(raw_value)


def parse_update_entries(payload: str) -> list[UpdateEntry]:
    """Parse the standard Dependabot updates subset without a YAML dependency."""
    lines = payload.splitlines()
    updates_index: int | None = None
    updates_indent = 0

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "updates:":
            updates_index = index
            updates_indent = len(line) - len(line.lstrip())
            break

    if updates_index is None:
        return []

    entries: list[UpdateEntry] = []
    current: UpdateEntry | None = None
    entry_indent: int | None = None
    directories_indent: int | None = None

    def finish() -> None:
        nonlocal current
        if current is not None:
            entries.append(current)
        current = None

    def apply_value(entry: UpdateEntry, key: str, value: str, indent: int) -> None:
        nonlocal directories_indent
        directories_indent = None
        if key == "package-ecosystem":
            entry.ecosystem = value
        elif key == "directory":
            entry.directories.append(normalize_directory(value))
        elif key == "directories":
            directories_indent = indent
            if value.startswith("[") and value.endswith("]"):
                for item in value[1:-1].split(","):
                    if scalar(item):
                        entry.directories.append(normalize_directory(scalar(item)))

    for line in lines[updates_index + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())
        if indent <= updates_indent:
            break

        if stripped.startswith("- ") and (
            entry_indent is None or indent == entry_indent
        ):
            if entry_indent is None:
                entry_indent = indent
            finish()
            current = UpdateEntry(ecosystem=None, directories=[])
            directories_indent = None
            parsed = parse_key_value(stripped[2:])
            if parsed:
                apply_value(current, parsed[0], parsed[1], indent)
            continue

        if current is None:
            continue

        if (
            directories_indent is not None
            and indent > directories_indent
            and stripped.startswith("- ")
        ):
            current.directories.append(normalize_directory(scalar(stripped[2:])))
            continue

        parsed = parse_key_value(stripped)
        if not parsed:
            continue
        key, value = parsed
        apply_value(current, key, value, indent)

    finish()
    return entries


def config_path(root: Path) -> Path | None:
    for name in ("dependabot.yml", "dependabot.yaml"):
        candidate = root / ".github" / name
        if candidate.is_file():
            return candidate
    return None


def pattern_matches(directory: str, pattern: str) -> bool:
    if pattern == "**/*":
        return True
    return fnmatch.fnmatchcase(directory, normalize_directory(pattern))


def covering_entries(
    surface: DependencySurface,
    entries: Iterable[UpdateEntry],
) -> list[str]:
    matches: list[str] = []
    for entry in entries:
        if entry.ecosystem != surface.ecosystem:
            continue
        for directory in entry.directories:
            if pattern_matches(surface.directory, directory):
                matches.append(directory)
    return sorted(set(matches))


def coverage_report(root: Path) -> dict[str, object]:
    surfaces = discover_surfaces(root)
    dependabot_path = config_path(root)
    entries = (
        parse_update_entries(dependabot_path.read_text(encoding="utf-8"))
        if dependabot_path
        else []
    )

    rows: list[dict[str, object]] = []
    for surface in surfaces:
        matches = covering_entries(surface, entries) if surface.supported else []
        status = (
            "unsupported"
            if not surface.supported
            else "covered"
            if matches
            else "uncovered"
        )
        row = asdict(surface)
        row.update({"status": status, "matching_directories": matches})
        rows.append(row)

    return {
        "root": str(root),
        "config": (
            dependabot_path.relative_to(root).as_posix() if dependabot_path else None
        ),
        "summary": {
            "graphs": len(rows),
            "covered": sum(row["status"] == "covered" for row in rows),
            "uncovered": sum(row["status"] == "uncovered" for row in rows),
            "unsupported": sum(row["status"] == "unsupported" for row in rows),
        },
        "surfaces": rows,
    }


def render_markdown(report: dict[str, object]) -> str:
    summary = report["summary"]
    assert isinstance(summary, dict)
    lines = [
        "# Dependabot configuration coverage",
        "",
        (
            f"{summary['graphs']} dependency graphs: {summary['covered']} covered, "
            f"{summary['uncovered']} uncovered, {summary['unsupported']} unsupported."
        ),
        "",
        f"Configuration: `{report['config'] or 'not found'}`",
        "",
        "| Status | Ecosystem | Directory | Manifest | Matching configuration | Note |",
        "|---|---|---|---|---|---|",
    ]
    surfaces = report["surfaces"]
    assert isinstance(surfaces, list)
    for row in surfaces:
        assert isinstance(row, dict)
        matches = ", ".join(f"`{value}`" for value in row["matching_directories"])
        note = str(row["note"] or "—").replace("|", "\\|")
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["status"]),
                    str(row["ecosystem"]),
                    f"`{row['directory']}`",
                    f"`{row['manifest']}`",
                    matches or "—",
                    note,
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare local dependency graphs with Dependabot update directories "
            "without changing repository or GitHub state."
        )
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repository root to inspect (default: current directory).",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 when uncovered or unsupported graphs are found.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"coverage check failed: '{root}' is not a directory", file=sys.stderr)
        return 2

    report = coverage_report(root)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))

    summary = report["summary"]
    assert isinstance(summary, dict)
    gaps = int(summary["uncovered"]) + int(summary["unsupported"])
    return 1 if args.strict and gaps else 0


if __name__ == "__main__":
    sys.exit(main())
