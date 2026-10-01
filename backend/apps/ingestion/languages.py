"""File-extension based language detection."""

from __future__ import annotations

from pathlib import PurePosixPath

# Languages we parse with tree-sitter (symbol-aware chunking + imports).
PARSEABLE = frozenset({"python", "javascript", "typescript", "tsx", "java", "go"})

EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".scala": "scala",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".vue": "vue",
    ".svelte": "svelte",
    ".md": "markdown",
    ".mdx": "markdown",
    ".rst": "restructuredtext",
    ".txt": "text",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".xml": "xml",
    ".gradle": "groovy",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".tf": "hcl",
    ".lua": "lua",
    ".dart": "dart",
    ".ex": "elixir",
    ".exs": "elixir",
    ".r": "r",
    ".jl": "julia",
}

FILENAMES: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "gnumakefile": "makefile",
    "procfile": "text",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "jenkinsfile": "groovy",
    ".env.example": "dotenv",
}

# Languages that count towards the repo's "code" breakdown (docs/config are excluded).
PROGRAMMING = frozenset(
    {
        "python",
        "javascript",
        "typescript",
        "tsx",
        "java",
        "go",
        "ruby",
        "rust",
        "c",
        "cpp",
        "csharp",
        "php",
        "kotlin",
        "swift",
        "scala",
        "shell",
        "powershell",
        "sql",
        "html",
        "css",
        "scss",
        "less",
        "vue",
        "svelte",
        "lua",
        "dart",
        "elixir",
        "r",
        "julia",
        "groovy",
        "dockerfile",
        "makefile",
        "hcl",
        "protobuf",
        "graphql",
    }
)

DISPLAY_NAMES = {"tsx": "TypeScript", "javascript": "JavaScript", "typescript": "TypeScript"}


def detect_language(path: str) -> str:
    """Language id for a repo-relative POSIX path (``"text"`` when unknown)."""
    p = PurePosixPath(path)
    name = p.name.lower()
    if name in FILENAMES:
        return FILENAMES[name]
    if name.startswith("dockerfile"):
        return "dockerfile"
    return EXTENSIONS.get(p.suffix.lower(), "text")


def display_name(language: str) -> str:
    return DISPLAY_NAMES.get(language, language.replace("cpp", "C++").capitalize())
