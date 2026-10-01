"""Helpers for working with the fixture repositories under ``tests/fixtures/repos``."""

from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "repos"


def copy_fixture(name: str, destination: Path) -> Path:
    target = destination / name
    shutil.copytree(FIXTURES / name, target)
    return target


def add_noise(root: Path) -> None:
    """Files the filter must skip; generated at test time so they never pollute the repo."""
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "node_modules" / "left-pad" / "index.js").write_text("module.exports = 1;\n")
    (root / "dist").mkdir()
    (root / "dist" / "bundle.js").write_text("var a=1;\n")
    (root / "vendor").mkdir()
    (root / "vendor" / "lib.py").write_text("x = 1\n")
    (root / "package-lock.json").write_text("{}\n")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    (root / "data.bin.txt").write_bytes(b"text\x00with null")
    (root / "app.min.js").write_text("function a(){return 1}\n")
    (root / "long.js").write_text("var x=" + "1+" * 3000 + "1;\n")
    (root / "debug.log").write_text("ignored by .gitignore\n")
    (root / "secrets").mkdir()
    (root / "secrets" / "key.py").write_text("KEY = 'nope'\n")
    (root / "empty.py").write_text("")
    (root / "big.py").write_text("x = 1\n" * 120_000)  # ~720 KB
