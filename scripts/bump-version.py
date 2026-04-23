#!/usr/bin/env python3
"""Bump the project version in VERSION + pyproject.toml.

Usage: python scripts/bump-version.py <new-version>
The new version must match PEP 440 (e.g. 1.0.8, 1.1.0rc1).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PEP440 = re.compile(r"^\d+\.\d+\.\d+([abc]|rc)?\d*$")
ROOT = Path(__file__).resolve().parent.parent


def _replace(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, n = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"refusing to write {path}: pattern not found")
    path.write_text(new_text, encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    new_version = argv[1]
    if not PEP440.match(new_version):
        print(f"error: {new_version!r} is not a valid PEP 440 version", file=sys.stderr)
        return 2

    (ROOT / "VERSION").write_text(new_version + "\n", encoding="utf-8")
    _replace(
        ROOT / "pyproject.toml",
        r'^version\s*=\s*"[^"]+"',
        f'version = "{new_version}"',
    )
    print(f"bumped to {new_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
