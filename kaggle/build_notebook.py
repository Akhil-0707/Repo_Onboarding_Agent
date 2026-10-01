"""Generate serve_model.ipynb from serve_model.py (percent-format cells).

Usage: python kaggle/build_notebook.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "serve_model.py"
TARGET = HERE / "serve_model.ipynb"


def split_cells(text: str) -> list[dict[str, object]]:
    cells: list[dict[str, object]] = []
    for block in re.split(r"^# %%", text, flags=re.MULTILINE):
        if not block.strip():
            continue
        header, _, body = block.partition("\n")
        if header.strip() == "[markdown]":
            lines = [re.sub(r"^# ?", "", line) for line in body.strip("\n").splitlines()]
            cells.append({"cell_type": "markdown", "metadata": {}, "source": "\n".join(lines)})
        else:
            cells.append(
                {
                    "cell_type": "code",
                    "metadata": {},
                    "execution_count": None,
                    "outputs": [],
                    "source": body.strip("\n"),
                }
            )
    return cells


def main() -> None:
    notebook = {
        "cells": split_cells(SOURCE.read_text(encoding="utf-8")),
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "kaggle": {"accelerator": "nvidiaTeslaT4", "isInternetEnabled": True},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    TARGET.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET} ({len(notebook['cells'])} cells)")


if __name__ == "__main__":
    main()
