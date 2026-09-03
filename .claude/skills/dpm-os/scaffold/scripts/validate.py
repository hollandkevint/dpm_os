#!/usr/bin/env python3
"""DPM OS instance validator.

CLI mode:   python3 scripts/validate.py <instance-dir>
            exit 0 on pass, 1 on any finding, one line per finding.
Hook mode:  no argument, Claude Code PostToolUse JSON on stdin.
            Validates the written file only. Exit 2 on a blocking finding
            (missing decision heading, bad status, untagged evidence row,
            malformed log row), exit 0 with a stderr warning on a broken link.

Checks: required files, relative markdown links, decision-record headings,
decision-log row shape, provenance tags on evidence rows and log rows.
Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIRED_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "INDEX.md",
    "README.md",
    ".claude/settings.json",
    "scripts/validate.py",
    "context/strategy.md",
    "context/product.md",
    "context/consumers.md",
    "context/team-and-decision-rights.md",
    "context/data-contract.md",
    "context/metrics-and-quality.md",
    "context/commercial-and-access-boundaries.md",
    "rules/INDEX.md",
    "rules/discovery.md",
    "rules/commitment.md",
    "rules/launch.md",
    "packets/INDEX.md",
    "packets/_TEMPLATE.md",
    "decisions/INDEX.md",
    "decisions/_SCHEMA.md",
    "decisions/LOG.md",
    "risks/LOG.md",
    "source/INDEX.md",
    "ingestion/INDEX.md",
    "maintenance/INDEX.md",
    "maintenance/scorecard.md",
    "maintenance/owner-guide.md",
]

DECISION_HEADINGS = [
    "Status",
    "Date",
    "Decider",
    "Decision",
    "Evidence",
    "What would reverse this",
    "Review date",
]
STATUS_VALUES = {"pending", "decided", "superseded"}
LOG_CELLS = 7

PROVENANCE_RES = (
    re.compile(r"\(stakeholder-verbal,\s*[^,]+,\s*\d{4}-\d{2}-\d{2}\)\s*`?\s*$", re.I),
    re.compile(r"\(intuition,\s*[^,]+,\s*\d{4}-\d{2}-\d{2}\)\s*`?\s*$", re.I),
    re.compile(r"\(hub,\s*[^,]+,\s*\d{4}-\d{2}-\d{2}\)\s*`?\s*$", re.I),
    re.compile(r"\(industry-knowledge\)\s*`?\s*$", re.I),
    re.compile(r"\(chat,\s*no artifact\)\s*`?\s*$", re.I),
    re.compile(r"\bUnknown(\s*\([^)]*\))?\s*`?\s*$"),
)
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
FENCE_RE = re.compile(r"^```[^\n]*\n.*?^```[ \t]*$", re.S | re.M)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
PLACEHOLDER_RE = re.compile(r"^\s*(<[^>]*>|\(none( yet)?\)|tbd|todo|-)\s*(`<provenance-tag>`)?\s*$", re.I)
ROOT_MARKERS = ("context", "decisions", "rules", "packets")


def _strip_code(text: str) -> str:
    return INLINE_CODE_RE.sub("", FENCE_RE.sub("", text))


def find_root(path: Path) -> Path | None:
    cur = path.resolve()
    cur = cur if cur.is_dir() else cur.parent
    while True:
        if (cur / "INDEX.md").is_file() and sum((cur / m).is_dir() for m in ROOT_MARKERS) >= 2:
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _link_resolves(target: str, base: Path) -> bool:
    target = target.split("#", 1)[0].strip()
    if not target or target.startswith(("http://", "https://", "mailto:", "tel:")):
        return True
    if "<" in target or "{{" in target:
        return True
    return (base / target).resolve().exists()


def has_provenance(row: str, base: Path) -> bool:
    """A row is tagged when it ends with an enum tag, `Unknown`, or a resolvable relative link."""
    if any(rx.search(row) for rx in PROVENANCE_RES):
        return True
    links = LINK_RE.findall(row)
    if links:
        text, target = links[-1]
        stripped = row[: row.rfind("[" + text + "]")].rstrip()
        after = row[row.rfind("(" + target + ")") + len(target) + 2 :].strip().strip("`")
        if after == "" and _link_resolves(target, base):
            return True
        if stripped and after == "" and _link_resolves(target, base):
            return True
    return False


def check_required(root: Path) -> list[str]:
    return [f"{rel}: required file missing" for rel in REQUIRED_FILES if not (root / rel).is_file()]


def check_links(path: Path, root: Path) -> list[str]:
    if path.name == "_SCHEMA.md":
        return []
    text = _strip_code(path.read_text(encoding="utf-8"))
    out = []
    for _, target in LINK_RE.findall(text):
        if not _link_resolves(target, path.parent):
            out.append(f"{_rel(path, root)}: link does not resolve: {target.split('#', 1)[0]}")
    return out


def _section(text: str, heading: str) -> list[str]:
    """Lines under `## <heading>` up to the next heading."""
    lines = text.splitlines()
    out, inside = [], False
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if m:
            inside = m.group(2).strip().lower() == heading.lower()
            continue
        if inside:
            out.append(line)
    return out


def _is_decision_record(path: Path, root: Path) -> bool:
    rel = _rel(path, root)
    return (
        rel.startswith("decisions/")
        and path.suffix == ".md"
        and path.name not in {"_SCHEMA.md", "INDEX.md", "LOG.md"}
    )


def check_decision(path: Path, root: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    rel = _rel(path, root)
    headings = {re.sub(r"^#{2,6}\s+", "", h).strip().lower() for h in re.findall(r"^#{2,6}\s+.*$", text, re.M)}
    out = []
    for h in DECISION_HEADINGS:
        if h.lower() not in headings:
            out.append(f"{rel}: missing heading '## {h}'")
    status = next((l.strip() for l in _section(text, "Status") if l.strip()), "")
    if status and status.lower() not in STATUS_VALUES:
        out.append(f"{rel}: status '{status}' not in {sorted(STATUS_VALUES)}")
    for heading in ("Evidence", "Explicitly NOT doing"):
        for i, line in enumerate(_section(text, heading), 1):
            m = re.match(r"^\s*[-*]\s+(.*)$", line)
            if not m:
                continue
            row = m.group(1).strip()
            if not row or PLACEHOLDER_RE.match(row):
                continue
            if not has_provenance(row, path.parent):
                out.append(f"{rel}: untagged row {i} under '## {heading}': {row[:60]}")
    return out


def check_log(path: Path, root: Path) -> list[str]:
    rel = _rel(path, root)
    out = []
    rows = [l for l in path.read_text(encoding="utf-8").splitlines() if l.lstrip().startswith("|")]
    for n, line in enumerate(rows):
        if n < 2:
            continue  # header and separator
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != LOG_CELLS:
            out.append(f"{rel}: row {n + 1} has {len(cells)} cells, expected {LOG_CELLS}")
            continue
        status = cells[4].lower()
        if status not in STATUS_VALUES:
            out.append(f"{rel}: row {n + 1} status '{cells[4]}' not in {sorted(STATUS_VALUES)}")
        if not has_provenance(cells[3], path.parent):
            out.append(f"{rel}: row {n + 1} evidence cell has no tag, link, or Unknown")
    return out


def validate_file(path: Path, root: Path) -> tuple[list[str], list[str]]:
    """Returns (blocking, warnings)."""
    if path.suffix != ".md" or not path.is_file():
        return [], []
    warnings = check_links(path, root)
    blocking: list[str] = []
    if _is_decision_record(path, root):
        blocking += check_decision(path, root)
    if _rel(path, root) == "decisions/LOG.md":
        blocking += check_log(path, root)
    return blocking, warnings


def validate_dir(root: Path) -> list[str]:
    findings = check_required(root)
    for path in sorted(root.rglob("*.md")):
        if ".git" in path.parts:
            continue
        b, w = validate_file(path, root)
        findings += b + w
    return findings


def _hook() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0
    fp = (payload.get("tool_input") or {}).get("file_path")
    if not fp:
        return 0
    path = Path(fp)
    if not path.exists() or path.suffix != ".md":
        return 0
    root = find_root(path)
    if root is None:
        return 0
    blocking, warnings = validate_file(path, root)
    if warnings:
        print("[dpm-os] warnings:\n" + "\n".join(warnings), file=sys.stderr)
    if blocking:
        print("[dpm-os] BLOCKING, fix this turn:\n" + "\n".join(blocking), file=sys.stderr)
        return 2
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        root = Path(argv[1])
        if not root.is_dir():
            print(f"{argv[1]}: not a directory")
            return 1
        findings = validate_dir(root)
        for f in findings:
            print(f)
        return 1 if findings else 0
    return _hook()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
