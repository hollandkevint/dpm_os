import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCAFFOLD = REPO / ".claude" / "skills" / "dpm-os" / "scaffold"
VALIDATE = SCAFFOLD / "scripts" / "validate.py"

spec = importlib.util.spec_from_file_location("validate", VALIDATE)
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)

RECORD = """# Decision: ship the thing

## Status
decided

## Date
2026-01-05

## Decider
A. Person

## Context
Text.

## Decision
Ship.

## Why
Because.

## Evidence
- The buyer asked for it  (stakeholder-verbal, A. Person, 2026-01-04)
- Prior note  [ingestion/note.md](../ingestion/note.md)

## Explicitly NOT doing
- A second cohort  Unknown

## What would reverse this
Adoption under 20 percent by 2026-03-01.

## Review date
2026-03-01
"""


def copy_scaffold(dest: Path) -> None:
    """Copy scaffold/. into dest without overwriting existing files (KTD6)."""
    for src in SCAFFOLD.rglob("*"):
        rel = src.relative_to(SCAFFOLD)
        target = dest / rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)


def run_cli(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(VALIDATE), str(root)], capture_output=True, text=True)


def run_hook(file_path: Path) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": str(file_path)}})
    return subprocess.run([sys.executable, str(VALIDATE)], input=payload, capture_output=True, text=True)


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        copy_scaffold(self.tmp)
        (self.tmp / "ingestion" / "note.md").write_text("# note\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_raw_scaffold_passes(self):
        self.assertEqual(run_cli(SCAFFOLD).returncode, 0, run_cli(SCAFFOLD).stdout)

    def test_greenfield_copy_passes_and_has_settings(self):
        r = run_cli(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue((self.tmp / ".claude" / "settings.json").is_file())

    def test_missing_required_file_named(self):
        (self.tmp / "rules" / "launch.md").unlink()
        r = run_cli(self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("rules/launch.md: required file missing", r.stdout)

    def test_valid_record_passes(self):
        (self.tmp / "decisions" / "2026-01-05-ship.md").write_text(RECORD)
        r = run_cli(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_missing_heading_named(self):
        bad = RECORD.replace("## What would reverse this\nAdoption under 20 percent by 2026-03-01.\n", "")
        (self.tmp / "decisions" / "2026-01-05-ship.md").write_text(bad)
        r = run_cli(self.tmp)
        self.assertIn("missing heading '## What would reverse this'", r.stdout)

    def test_untagged_evidence_row_named(self):
        bad = RECORD.replace("- Prior note  [ingestion/note.md](../ingestion/note.md)", "- Prior note with no tag")
        (self.tmp / "decisions" / "2026-01-05-ship.md").write_text(bad)
        r = run_cli(self.tmp)
        self.assertIn("untagged row 2 under '## Evidence'", r.stdout)

    def test_bad_status_named(self):
        bad = RECORD.replace("## Status\ndecided", "## Status\ndone")
        (self.tmp / "decisions" / "2026-01-05-ship.md").write_text(bad)
        r = run_cli(self.tmp)
        self.assertIn("status 'done' not in", r.stdout)

    def test_log_row_cell_count(self):
        log = self.tmp / "decisions" / "LOG.md"
        log.write_text(log.read_text() + "| 2026-01-05 | Ship | A. Person | Unknown | decided | 2026-03-01 |\n")
        r = run_cli(self.tmp)
        self.assertIn("LOG.md: row 3 has 6 cells, expected 7", r.stdout)

    def test_log_row_evidence_cell_untagged(self):
        log = self.tmp / "decisions" / "LOG.md"
        log.write_text(log.read_text() + "| 2026-01-05 | Ship | A. Person | see thread | decided | 2026-03-01 |  |\n")
        r = run_cli(self.tmp)
        self.assertIn("row 3 evidence cell has no tag, link, or Unknown", r.stdout)

    def test_log_row_with_record_link_passes(self):
        (self.tmp / "decisions" / "2026-01-05-ship.md").write_text(RECORD)
        log = self.tmp / "decisions" / "LOG.md"
        log.write_text(log.read_text() + "| 2026-01-05 | Ship | A. Person | [record](2026-01-05-ship.md) | decided | 2026-03-01 |  |\n")
        r = run_cli(self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_broken_link_fails_cli_warns_hook(self):
        f = self.tmp / "context" / "product.md"
        f.write_text(f.read_text() + "\nSee [missing](../nowhere.md).\n")
        cli = run_cli(self.tmp)
        self.assertEqual(cli.returncode, 1)
        self.assertIn("link does not resolve: ../nowhere.md", cli.stdout)
        hook = run_hook(f)
        self.assertEqual(hook.returncode, 0)
        self.assertIn("link does not resolve", hook.stderr)

    def test_link_in_fenced_code_ignored(self):
        f = self.tmp / "context" / "product.md"
        f.write_text(f.read_text() + "\n```\n[x](../nowhere.md)\n```\n")
        self.assertEqual(run_cli(self.tmp).returncode, 0)

    def test_hook_blocks_untagged_record(self):
        rec = self.tmp / "decisions" / "2026-01-05-ship.md"
        rec.write_text(RECORD.replace("- Prior note  [ingestion/note.md](../ingestion/note.md)", "- untagged"))
        hook = run_hook(rec)
        self.assertEqual(hook.returncode, 2)
        self.assertIn("BLOCKING", hook.stderr)

    def test_hook_outside_instance_exits_zero(self):
        outside = Path(tempfile.mkdtemp()) / "loose.md"
        outside.write_text("- untagged claim\n")
        self.assertEqual(run_hook(outside).returncode, 0)


class NoOverwriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_preexisting_files_untouched(self):
        (self.tmp / "CLAUDE.md").write_text("mine\n")
        (self.tmp / "notes.md").write_text("notes\n")
        copy_scaffold(self.tmp)
        self.assertEqual((self.tmp / "CLAUDE.md").read_text(), "mine\n")
        self.assertEqual((self.tmp / "notes.md").read_text(), "notes\n")
        self.assertTrue((self.tmp / "INDEX.md").is_file())

    def test_settings_merge_keeps_existing_key(self):
        (self.tmp / ".claude").mkdir()
        existing = self.tmp / ".claude" / "settings.json"
        existing.write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}))
        copy_scaffold(self.tmp)
        merged = json.loads(existing.read_text())
        scaffold_hooks = json.loads((SCAFFOLD / ".claude" / "settings.json").read_text())["hooks"]
        merged.setdefault("hooks", {}).setdefault("PostToolUse", [])
        merged["hooks"]["PostToolUse"] += scaffold_hooks["PostToolUse"]
        existing.write_text(json.dumps(merged))
        final = json.loads(existing.read_text())
        self.assertIn("permissions", final)
        self.assertEqual(final["hooks"]["PostToolUse"][0]["hooks"][0]["command"], "python3 scripts/validate.py")


if __name__ == "__main__":
    unittest.main()
