from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.ingestion.detect import detect, is_manifest
from apps.ingestion.errors import LimitExceededError
from apps.ingestion.filters import FilterLimits, filter_repository, read_text
from apps.ingestion.languages import detect_language
from tests.conftest_fixtures import add_noise, copy_fixture


@pytest.fixture
def noisy_py_app(tmp_path: Path) -> Path:
    root = copy_fixture("py_app", tmp_path)
    add_noise(root)
    return root


def test_keeps_source_and_skips_noise(noisy_py_app: Path) -> None:
    result = filter_repository(noisy_py_app)
    paths = {f.path for f in result.files}

    assert "app/main.py" in paths
    assert "app/services.py" in paths
    assert "tests/test_services.py" in paths
    assert "README.md" in paths
    for skipped in [
        "node_modules/left-pad/index.js",
        "dist/bundle.js",
        "vendor/lib.py",
        "package-lock.json",
        "logo.png",
        "data.bin.txt",
        "app.min.js",
        "long.js",
        "debug.log",
        "secrets/key.py",
        "empty.py",
        "big.py",
    ]:
        assert skipped not in paths, skipped
    assert result.skipped["ignored_dir"] >= 2
    assert result.skipped["vendored"] == 1
    assert result.skipped["lockfile"] == 1
    assert result.skipped["binary"] == 2
    assert result.skipped["minified"] == 2
    assert result.skipped["gitignored"] == 2
    assert result.too_large == ["big.py"]


def test_paths_are_posix_and_languages_detected(noisy_py_app: Path) -> None:
    result = filter_repository(noisy_py_app)
    by_path = {f.path: f for f in result.files}
    assert all("\\" not in p for p in by_path)
    assert by_path["app/main.py"].language == "python"
    assert by_path["README.md"].language == "markdown"
    assert read_text(by_path["app/config.py"]).startswith("import os")


def test_file_count_limit(tmp_path: Path) -> None:
    for i in range(6):
        (tmp_path / f"m{i}.py").write_text("x = 1\n")
    with pytest.raises(LimitExceededError, match="more than 5"):
        filter_repository(tmp_path, FilterLimits(max_files=5))


def test_file_size_limit_is_configurable(tmp_path: Path) -> None:
    (tmp_path / "small.py").write_text("x = 1\n")
    (tmp_path / "medium.py").write_text("x = 1\n" * 100)
    result = filter_repository(tmp_path, FilterLimits(max_file_bytes=100))
    assert [f.path for f in result.files] == ["small.py"]
    assert result.too_large == ["medium.py"]


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlinks_are_never_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("x = 1\n")
    (repo / "leak.txt").symlink_to(outside)
    (repo / "linkdir").symlink_to(tmp_path)
    result = filter_repository(repo)
    assert [f.path for f in result.files] == ["a.py"]
    assert result.skipped["symlink"] == 2


def test_nested_gitignore_applies_to_its_directory(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / ".gitignore").write_text("generated.py\n")
    (tmp_path / "pkg" / "generated.py").write_text("x = 1\n")
    (tmp_path / "generated.py").write_text("x = 1\n")
    paths = {f.path for f in filter_repository(tmp_path).files}
    assert "generated.py" in paths
    assert "pkg/generated.py" not in paths


@pytest.mark.parametrize(
    ("path", "language"),
    [
        ("a/b.py", "python"),
        ("x.tsx", "tsx"),
        ("x.jsx", "javascript"),
        ("Dockerfile", "dockerfile"),
        ("Dockerfile.prod", "dockerfile"),
        ("Makefile", "makefile"),
        ("weird.xyz", "text"),
    ],
)
def test_detect_language(path: str, language: str) -> None:
    assert detect_language(path) == language


def test_detects_frameworks_and_scripts_from_manifests() -> None:
    manifests = {
        "package.json": (
            '{"scripts": {"dev": "vite"}, "dependencies": {"react": "1", "express": "5"},'
            ' "devDependencies": {"vitest": "1"}}'
        ),
        "backend/pyproject.toml": (
            '[project]\nname = "x"\ndependencies = ["Django>=5", "celery[redis]"]\n'
            '[project.scripts]\nserve = "x.main:run"\n'
        ),
        "go.mod": "module github.com/acme/tool\n\nrequire github.com/spf13/cobra v1.8.0\n",
        "pom.xml": "<artifactId>spring-boot-starter-web</artifactId>",
        "Dockerfile": "FROM python:3.13",
    }
    files = [
        ("main.go", "go", 100, 10),
        ("app.py", "python", 300, 30),
        ("README.md", "markdown", 900, 50),
        (".github/workflows/ci.yml", "yaml", 50, 5),
    ]
    detection = detect(files, manifests)

    for label in ["React", "Express", "Vitest", "Django", "Celery", "Cobra", "Spring Boot"]:
        assert label in detection.frameworks
    assert "Docker" in detection.frameworks
    assert "GitHub Actions" in detection.frameworks
    assert detection.go_module == "github.com/acme/tool"
    assert detection.scripts["npm run dev"] == "vite"
    assert detection.scripts["serve"] == "x.main:run"
    # markdown/yaml do not count as code
    assert detection.language_percentages() == {"python": 75.0, "go": 25.0}
    assert detection.primary_language == "python"


def test_is_manifest() -> None:
    assert is_manifest("package.json")
    assert is_manifest("sub/requirements-prod.txt")
    assert not is_manifest("src/app.py")
