"""Detect languages, frameworks and tooling from file extensions and manifests.

Manifests are parsed as data only; nothing from the repository is ever executed.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from apps.ingestion.languages import PROGRAMMING

MANIFEST_NAMES = frozenset(
    {
        "package.json",
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "pipfile",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "go.mod",
        "cargo.toml",
        "gemfile",
        "composer.json",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "makefile",
        "tsconfig.json",
        "manage.py",
        "procfile",
    }
)

# dependency name (lower-case) -> framework / tool label
JS_FRAMEWORKS = {
    "react": "React",
    "next": "Next.js",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "@angular/core": "Angular",
    "svelte": "Svelte",
    "@sveltejs/kit": "SvelteKit",
    "solid-js": "SolidJS",
    "express": "Express",
    "fastify": "Fastify",
    "koa": "Koa",
    "@nestjs/core": "NestJS",
    "hono": "Hono",
    "electron": "Electron",
    "react-native": "React Native",
    "vite": "Vite",
    "webpack": "webpack",
    "tailwindcss": "Tailwind CSS",
    "jest": "Jest",
    "vitest": "Vitest",
    "mocha": "Mocha",
    "@playwright/test": "Playwright",
    "cypress": "Cypress",
    "typescript": "TypeScript",
    "prisma": "Prisma",
    "mongoose": "Mongoose",
    "graphql": "GraphQL",
    "socket.io": "Socket.IO",
    "commander": "Commander.js",
    "yargs": "yargs",
}
PY_FRAMEWORKS = {
    "django": "Django",
    "djangorestframework": "Django REST Framework",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "starlette": "Starlette",
    "tornado": "Tornado",
    "aiohttp": "aiohttp",
    "celery": "Celery",
    "sqlalchemy": "SQLAlchemy",
    "pydantic": "Pydantic",
    "pytest": "pytest",
    "numpy": "NumPy",
    "pandas": "pandas",
    "torch": "PyTorch",
    "tensorflow": "TensorFlow",
    "scikit-learn": "scikit-learn",
    "click": "Click",
    "typer": "Typer",
    "streamlit": "Streamlit",
    "langchain": "LangChain",
    "scrapy": "Scrapy",
}
GO_FRAMEWORKS = {
    "github.com/gin-gonic/gin": "Gin",
    "github.com/labstack/echo": "Echo",
    "github.com/gofiber/fiber": "Fiber",
    "github.com/go-chi/chi": "chi",
    "github.com/gorilla/mux": "Gorilla Mux",
    "github.com/spf13/cobra": "Cobra",
    "google.golang.org/grpc": "gRPC",
    "gorm.io/gorm": "GORM",
}
JVM_MARKERS = {
    "spring-boot": "Spring Boot",
    "springframework": "Spring",
    "quarkus": "Quarkus",
    "micronaut": "Micronaut",
    "junit": "JUnit",
    "hibernate": "Hibernate",
    "lombok": "Lombok",
}

_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+)")


@dataclass
class LanguageStat:
    files: int = 0
    bytes: int = 0
    lines: int = 0


@dataclass
class Detection:
    languages: dict[str, LanguageStat] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)
    """Run scripts found in manifests (package.json scripts, pyproject scripts, Makefile)."""
    go_module: str | None = None

    def language_percentages(self) -> dict[str, float]:
        code = {k: v for k, v in self.languages.items() if k in PROGRAMMING}
        total = sum(v.bytes for v in code.values()) or 1
        return {
            k: round(v.bytes * 100 / total, 1)
            for k, v in sorted(code.items(), key=lambda kv: -kv[1].bytes)
        }

    @property
    def primary_language(self) -> str | None:
        percentages = self.language_percentages()
        return next(iter(percentages), None)


def is_manifest(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return name in MANIFEST_NAMES or (name.startswith("requirements") and name.endswith(".txt"))


def _add(target: list[str], *labels: str) -> None:
    for label in labels:
        if label and label not in target:
            target.append(label)


def _from_package_json(text: str, detection: Detection) -> None:
    try:
        data = json.loads(text)
    except ValueError:
        return
    if not isinstance(data, Mapping):
        return
    deps: dict[str, object] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = data.get(key)
        if isinstance(section, Mapping):
            deps.update(section)
    for name in deps:
        if name.lower() in JS_FRAMEWORKS:
            _add(detection.frameworks, JS_FRAMEWORKS[name.lower()])
    scripts = data.get("scripts")
    if isinstance(scripts, Mapping):
        for name, command in list(scripts.items())[:20]:
            if isinstance(command, str):
                detection.scripts.setdefault(f"npm run {name}", command[:200])
    _add(detection.package_managers, "npm")


def _python_names(names: list[str], detection: Detection) -> None:
    for raw in names:
        match = _REQ_NAME.match(raw)
        if not match:
            continue
        name = match.group(1).split("[")[0].lower().replace("_", "-")
        if name in PY_FRAMEWORKS:
            _add(detection.frameworks, PY_FRAMEWORKS[name])


def _from_pyproject(text: str, detection: Detection) -> None:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    project = data.get("project", {})
    names: list[str] = list(project.get("dependencies", []) or [])
    for extra in (project.get("optional-dependencies") or {}).values():
        names.extend(extra or [])
    poetry = data.get("tool", {}).get("poetry", {})
    names.extend((poetry.get("dependencies") or {}).keys())
    _python_names([str(n) for n in names], detection)
    for name, target in (project.get("scripts") or {}).items():
        detection.scripts.setdefault(name, str(target)[:200])
    _add(detection.package_managers, "poetry" if poetry else "pip")


def _from_go_mod(text: str, detection: Detection) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("module "):
            detection.go_module = stripped.split()[1]
        for prefix, label in GO_FRAMEWORKS.items():
            if prefix in stripped:
                _add(detection.frameworks, label)
    _add(detection.package_managers, "go modules")


def _from_jvm(text: str, name: str, detection: Detection) -> None:
    lowered = text.lower()
    for marker, label in JVM_MARKERS.items():
        if marker in lowered:
            _add(detection.frameworks, label)
    _add(detection.package_managers, "Maven" if name == "pom.xml" else "Gradle")


def _from_makefile(text: str, detection: Detection) -> None:
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_.\-]+):(?!=)", line)
        if match and not match.group(1).startswith("."):
            detection.scripts.setdefault(f"make {match.group(1)}", "")
        if len(detection.scripts) > 40:
            break


def detect(files: list[tuple[str, str, int, int]], manifests: dict[str, str]) -> Detection:
    """``files`` is ``(path, language, bytes, lines)``; ``manifests`` maps path -> text."""
    detection = Detection()
    for _path, language, size, lines in files:
        stat = detection.languages.setdefault(language, LanguageStat())
        stat.files += 1
        stat.bytes += size
        stat.lines += lines

    for path in sorted(manifests, key=lambda p: (p.count("/"), p)):
        text = manifests[path]
        name = PurePosixPath(path).name.lower()
        _add(detection.manifests, path)
        if name == "package.json":
            _from_package_json(text, detection)
        elif name == "pyproject.toml":
            _from_pyproject(text, detection)
        elif name.startswith("requirements") or name == "pipfile":
            _python_names(text.splitlines(), detection)
            _add(detection.package_managers, "pip")
        elif name in {"setup.py", "setup.cfg"}:
            _python_names(re.findall(r"['\"]([A-Za-z0-9_.\-]+)[<>=~! ]", text), detection)
        elif name == "go.mod":
            _from_go_mod(text, detection)
        elif name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
            _from_jvm(text, name, detection)
        elif name == "cargo.toml":
            _add(detection.package_managers, "Cargo")
        elif name == "gemfile":
            _add(detection.package_managers, "Bundler")
            if "rails" in text:
                _add(detection.frameworks, "Ruby on Rails")
        elif name == "composer.json":
            _add(detection.package_managers, "Composer")
            if "laravel/framework" in text:
                _add(detection.frameworks, "Laravel")
        elif name == "dockerfile":
            _add(detection.frameworks, "Docker")
        elif name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
            _add(detection.frameworks, "Docker Compose")
        elif name == "makefile" and "/" not in path:
            _from_makefile(text, detection)
        elif name == "manage.py":
            _add(detection.frameworks, "Django")

    if any(p.startswith(".github/workflows/") for p, *_ in files):
        _add(detection.frameworks, "GitHub Actions")
    return detection
