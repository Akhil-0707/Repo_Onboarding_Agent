"""Render the architecture graph as Mermaid on the server.

Small models write broken Mermaid; they are much better at JSON. The model returns a graph, the
references are verified, and this module produces the diagram deterministically. Every label is
sanitised so repository text can never inject Mermaid syntax, links or HTML.
"""

from __future__ import annotations

import re
from typing import Any

# Node shapes per module kind: (open, close) around a quoted label.
SHAPES: dict[str, tuple[str, str]] = {
    "entry": ("([", "])"),
    "data": ("[(", ")]"),
    "external": ("{{", "}}"),
    "ui": ("[/", "/]"),
    "config": ("[[", "]]"),
}
DEFAULT_SHAPE = ("[", "]")

# Light fills with dark text read well on both the light and the dark theme.
CLASS_DEFS: dict[str, str] = {
    "entry": "fill:#e0e7ff,stroke:#4f46e5,color:#1e1b4b",
    "core": "fill:#dbeafe,stroke:#2563eb,color:#172554",
    "service": "fill:#ccfbf1,stroke:#0d9488,color:#042f2e",
    "data": "fill:#fef3c7,stroke:#d97706,color:#451a03",
    "ui": "fill:#fce7f3,stroke:#db2777,color:#500724",
    "config": "fill:#f1f5f9,stroke:#64748b,color:#0f172a",
    "util": "fill:#ecfccb,stroke:#65a30d,color:#1a2e05",
    "external": "fill:#f5f5f4,stroke:#78716c,color:#1c1917,stroke-dasharray:4 3",
    "test": "fill:#f3e8ff,stroke:#9333ea,color:#3b0764",
    "other": "fill:#f8fafc,stroke:#94a3b8,color:#0f172a",
}

# Characters with meaning in Mermaid or HTML. `#` starts entity codes, `;` ends statements.
_UNSAFE = re.compile(r"[\"<>{}\[\]|`#;&\\]")
_SPACE = re.compile(r"\s+")
_ID = re.compile(r"[^a-z0-9_]")


def sanitize_label(text: str | None, limit: int = 48) -> str:
    text = _SPACE.sub(" ", _UNSAFE.sub("", (text or "").replace('"', "'"))).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def node_id(module_id: str) -> str:
    # Prefixed: bare ids like `end` or `graph` are Mermaid keywords.
    return "m_" + (_ID.sub("_", module_id.lower()) or "x")


def render_mermaid(data: dict[str, Any]) -> str:
    modules = data.get("modules", [])
    lines = ["flowchart LR" if len(modules) <= 5 else "flowchart TD"]
    known = set()
    for module in modules:
        nid = node_id(module["id"])
        known.add(nid)
        open_, close = SHAPES.get(module.get("kind", ""), DEFAULT_SHAPE)
        label = sanitize_label(module.get("name")) or sanitize_label(module["id"])
        lines.append(f'    {nid}{open_}"{label}"{close}')
    for edge in data.get("edges", []):
        source, target = node_id(edge["source"]), node_id(edge["target"])
        if source not in known or target not in known:
            continue
        if edge.get("derived"):
            count = edge.get("imports", 0)
            text = f"{count} import{'s' if count != 1 else ''}" if count else "imports"
            lines.append(f'    {source} -.->|"{text}"| {target}')
        else:
            label = sanitize_label(edge.get("label"), limit=32)
            arrow = f'-->|"{label}"|' if label else "-->"
            lines.append(f"    {source} {arrow} {target}")
    used = sorted({m.get("kind", "other") for m in modules} & set(CLASS_DEFS))
    for kind in used:
        lines.append(f"    classDef {kind} {CLASS_DEFS[kind]}")
    for kind in used:
        members = [node_id(m["id"]) for m in modules if m.get("kind", "other") == kind]
        lines.append(f"    class {','.join(members)} {kind}")
    return "\n".join(lines)
