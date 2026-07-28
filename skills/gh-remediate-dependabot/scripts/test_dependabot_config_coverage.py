#!/usr/bin/env python3
"""Tests for dependabot_config_coverage.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dependabot_config_coverage import coverage_report, parse_update_entries


class ParseUpdateEntriesTest(unittest.TestCase):
    def test_parses_directory_directories_and_globstar(self) -> None:
        entries = parse_update_entries(
            """
version: 2
updates:
  - directory: "/"
    package-ecosystem: "bundler"
    schedule:
      interval: weekly
  - package-ecosystem: npm
    directories:
      - "/client"
      - "/packages/*"
    schedule:
      interval: daily
  - package-ecosystem: "composer"
    directories: ["/", "**/*"]
    schedule:
      interval: monthly
"""
        )

        self.assertEqual(
            [
                ("bundler", ["/"]),
                ("npm", ["/client", "/packages/*"]),
                ("composer", ["/", "**/*"]),
            ],
            [(entry.ecosystem, entry.directories) for entry in entries],
        )


class CoverageReportTest(unittest.TestCase):
    def test_reports_nested_graphs_and_legacy_bun_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".github").mkdir()
            (root / "docs").mkdir()
            (root / "client").mkdir()
            (root / "legacy").mkdir()
            (root / ".ruby-lsp").mkdir()
            (root / "Gemfile.lock").touch()
            (root / "docs" / "Gemfile.lock").touch()
            (root / "client" / "package-lock.json").touch()
            (root / "legacy" / "bun.lockb").touch()
            (root / ".ruby-lsp" / "Gemfile.lock").touch()
            (root / ".github" / "dependabot.yml").write_text(
                """
version: 2
updates:
  - package-ecosystem: bundler
    directory: "/"
    schedule:
      interval: daily
  - package-ecosystem: npm
    directories:
      - "/client"
    schedule:
      interval: weekly
""",
                encoding="utf-8",
            )

            report = coverage_report(root)
            rows = {
                (row["ecosystem"], row["directory"]): row
                for row in report["surfaces"]
            }

            self.assertEqual("covered", rows[("bundler", "/")]["status"])
            self.assertEqual("uncovered", rows[("bundler", "/docs")]["status"])
            self.assertEqual("covered", rows[("npm", "/client")]["status"])
            self.assertEqual("unsupported", rows[("bun", "/legacy")]["status"])
            self.assertEqual(
                {"graphs": 4, "covered": 2, "uncovered": 1, "unsupported": 1},
                report["summary"],
            )

    def test_globstar_covers_nested_graphs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".github").mkdir()
            (root / "services" / "api").mkdir(parents=True)
            (root / "services" / "api" / "composer.lock").touch()
            (root / ".github" / "dependabot.yaml").write_text(
                """
version: 2
updates:
  - package-ecosystem: composer
    directories:
      - "**/*"
    schedule:
      interval: weekly
""",
                encoding="utf-8",
            )

            report = coverage_report(root)

            self.assertEqual(1, report["summary"]["covered"])
            self.assertEqual("covered", report["surfaces"][0]["status"])


if __name__ == "__main__":
    unittest.main()
