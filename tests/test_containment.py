"""Containment test: no client term in any tracked file of this public repo.

The list below is the only place these terms may appear in the repo. Matching is
case-insensitive on word boundaries. This is regression coverage; a manual sweep
of tracked files and git history still runs before any push.
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()

BANNED = [
    "S2N",
    "Device Signal",
    "DeviceSignal",
    "MarketSignal",
    "RepSignal",
    "Owen",
    "Dorothy",
    "Kofol",
    "Omni",
    "Astro Data",
]
PATTERN = re.compile(r"\b(" + "|".join(re.escape(t) for t in BANNED) + r")\b", re.IGNORECASE)


def scan(paths):
    """Return (path, line_no, term) for every hit in the given files."""
    hits = []
    for p in paths:
        p = Path(p)
        if p.resolve() == SELF or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in PATTERN.finditer(line):
                hits.append((str(p), n, m.group(1)))
    return hits


def tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return [REPO / line for line in out.splitlines() if line]


class ContainmentTests(unittest.TestCase):
    def test_repo_has_no_client_terms(self):
        hits = scan(tracked_files())
        self.assertEqual(hits, [], f"client terms found: {hits}")

    def test_scan_catches_a_term(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.md"
            f.write_text(f"note about {BANNED[1]} here\n")
            self.assertEqual(len(scan([f])), 1)

    def test_scan_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.md"
            f.write_text(f"{BANNED[5].lower()} said so\n")
            self.assertEqual(len(scan([f])), 1)

    def test_scan_respects_word_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.md"
            f.write_text(f"{BANNED[8]}bus and {BANNED[8]}channel\n")
            self.assertEqual(scan([f]), [])


if __name__ == "__main__":
    unittest.main()
