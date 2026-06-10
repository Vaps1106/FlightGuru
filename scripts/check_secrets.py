#!/usr/bin/env python3
"""Secret-leak guard — fail if a likely secret appears in a git-tracked file.

Run in CI (and optionally as a pre-commit hook). Scans files known to git via
``git ls-files`` for token-shaped strings. .env is git-ignored so it is never
scanned; the archived v1 config is git-ignored too.
"""

from __future__ import annotations

import re
import subprocess
import sys

PATTERNS = [
    (re.compile(r"duffel_(?:live|test)_[A-Za-z0-9_\-]{10,}"), "Duffel token"),
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}\b"), "Telegram bot token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
]

SKIP_PREFIXES = ("archive/", "scripts/")
SKIP_SUFFIXES = (".db", ".png", ".jpg", ".jpeg", ".gif", ".ico")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    return [f for f in out.stdout.splitlines() if f]


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        if path.startswith(SKIP_PREFIXES) or path.endswith(SKIP_SUFFIXES):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        for rx, label in PATTERNS:
            if rx.search(text):
                findings.append(f"{path}: possible {label}")

    if findings:
        print("Secret scan FAILED — possible secrets in tracked files:")
        for f in findings:
            print("  " + f)
        return 1
    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
