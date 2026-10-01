"""Ingestion pipeline: clone -> filter -> detect -> parse -> chunk -> store.

All steps that need the working tree run in one task on one worker (the clone lives in a
local temp dir). Later stages that only need MongoDB (embeddings, analysis) are chained as
separate Celery tasks (see ``apps.ingestion.tasks``); ``finalize`` marks the snapshot ready.
The clone is always deleted, and repository code is never executed.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.accounts.crypto import TokenDecryptionError
from apps.accounts.services import get_github_token
from apps.common.logging import get_logger
from apps.ingestion import index_store
from apps.ingestion.chunking import Chunk, chunk_file
from apps.ingestion.clone import clone_repository
from apps.ingestion.depgraph import build_edges
from apps.ingestion.detect import detect, is_manifest
from apps.ingestion.errors import IngestionError
from apps.ingestion.filters import FilterLimits, FilterResult, filter_repository
from apps.ingestion.parsing import ParsedFile, parse_source
from apps.ingestion.progress import JobReporter
from apps.repos.models import IngestionJob, JobStatus, Repository, RepoStatus

logger = get_logger(__name__)

Cloner = Callable[..., Path]


@dataclass
class _Work:
    root: Path
    filtered: FilterResult | None = None
    texts: dict[str, str] = field(default_factory=dict)
    blob_shas: dict[str, str] = field(default_factory=dict)
    parsed: dict[str, ParsedFile] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)


def _token_for(job: IngestionJob, repo: Repository) -> str | None:
    if not repo.private or job.user is None:
        return None
    try:
        return get_github_token(job.user) or None
    except TokenDecryptionError:
        raise IngestionError("Your GitHub connection needs to be renewed. Sign in again.") from None


def _workdir() -> Path:
    base = settings.INGEST_WORKDIR or tempfile.gettempdir()
    Path(base).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="repoguide-", dir=base))


def run_ingestion(job_id: str, *, cloner: Cloner | None = None) -> str:
    """Run the clone-dependent stages for ``job_id``. Returns the repository id."""
    job = IngestionJob.objects.select_related("repository", "user").get(pk=job_id)
    repo = job.repository
    reporter = JobReporter(job_id)
    sandbox: Path | None = None
    try:
        reporter.job_started()
        Repository.objects.filter(pk=repo.pk).update(status=RepoStatus.INGESTING, error="")
        reporter.complete("resolve", f"{repo.full_name} @ {repo.commit_sha[:7]}")
        sandbox = _workdir()
        work = _Work(root=sandbox / "repo")
        _clone(work, job, repo, reporter, cloner or clone_repository)
        _filter(work, reporter)
        detection = _detect(work, reporter)
        _parse(work, reporter)
        _chunk(work, reporter)
        stats = _store(work, repo, detection, reporter)

        Repository.objects.filter(pk=repo.pk).update(
            stats=stats,
            languages=detection.language_percentages(),
            frameworks=detection.frameworks,
            detection={
                "manifests": detection.manifests[:50],
                "package_managers": detection.package_managers,
                "scripts": dict(list(detection.scripts.items())[:40]),
                "go_module": detection.go_module,
                "primary_language": detection.primary_language,
            },
        )
        return str(repo.pk)
    except IngestionError as exc:
        _fail(repo, reporter, str(exc))
        raise
    except Exception as exc:
        logger.exception("ingestion_crashed", job_id=job_id)
        try:
            _fail(repo, reporter, "Unexpected error while processing the repository.")
        except Exception:  # the failure itself may be what broke (e.g. DB down)
            logger.exception("ingestion_fail_record_failed", job_id=job_id)
        raise IngestionError("Unexpected error while processing the repository.") from exc
    finally:
        if sandbox is not None:
            shutil.rmtree(sandbox, ignore_errors=True)


def _fail(repo: Repository, reporter: JobReporter, message: str) -> None:
    Repository.objects.filter(pk=repo.pk).update(status=RepoStatus.FAILED, error=message)
    reporter.finish(JobStatus.FAILED, message)


def fail_job(job_id: str, message: str) -> None:
    job = IngestionJob.objects.select_related("repository").get(pk=job_id)
    _fail(job.repository, JobReporter(job_id), message)


def job_is_failed(job_id: str) -> bool:
    """Later chain stages call this first and do nothing if an earlier stage failed."""
    return IngestionJob.objects.filter(pk=job_id, status=JobStatus.FAILED).exists()


def mark_indexed(job_id: str) -> None:
    """Code index + embeddings are done: the snapshot can be browsed, searched and served from
    cache. The AI analysis continues in the same job (and may wait for the model server)."""
    if job_is_failed(job_id):
        return
    job = IngestionJob.objects.select_related("repository").get(pk=job_id)
    Repository.objects.filter(pk=job.repository_id).update(
        status=RepoStatus.READY, error="", ingested_at=timezone.now()
    )


def _clone(
    work: _Work, job: IngestionJob, repo: Repository, reporter: JobReporter, cloner: Cloner
) -> None:
    with reporter.step("clone"):
        reporter.log("clone", f"Fetching {repo.full_name} at commit {repo.commit_sha[:12]}")
        cloner(
            repo.url,
            repo.commit_sha,
            work.root,
            token=_token_for(job, repo),
            timeout=settings.INGEST_CLONE_TIMEOUT,
            max_bytes=settings.INGEST_MAX_REPO_MB * 1024 * 1024,
        )
        reporter.complete("clone", "Shallow clone complete")


def _filter(work: _Work, reporter: JobReporter) -> None:
    with reporter.step("filter"):
        limits = FilterLimits(
            max_files=settings.INGEST_MAX_FILES, max_file_bytes=settings.INGEST_MAX_FILE_KB * 1024
        )
        work.filtered = filter_repository(work.root, limits)
        skipped = ", ".join(f"{n} {reason}" for reason, n in work.filtered.skipped.most_common())
        reporter.log(
            "filter", f"Kept {len(work.filtered.files)} files; skipped {skipped or 'none'}"
        )
        if work.filtered.too_large:
            shown = ", ".join(work.filtered.too_large[:5])
            reporter.log(
                "filter",
                f"Skipped {len(work.filtered.too_large)} file(s) over "
                f"{settings.INGEST_MAX_FILE_KB} KB: {shown}",
                level="warning",
            )
        if not work.filtered.files:
            raise IngestionError("No source files left to analyze after filtering.")
        for file in work.filtered.files:
            raw = file.abs_path.read_bytes()
            work.blob_shas[file.path] = index_store.git_blob_sha(raw)
            work.texts[file.path] = raw.decode("utf-8", errors="replace")
        reporter.complete("filter", f"{len(work.filtered.files)} files kept")


def _detect(work: _Work, reporter: JobReporter) -> Any:
    assert work.filtered is not None
    with reporter.step("detect"):
        files = [
            (f.path, f.language, f.size, work.texts[f.path].count("\n") + 1)
            for f in work.filtered.files
        ]
        manifests = {f.path: work.texts[f.path] for f in work.filtered.files if is_manifest(f.path)}
        detection = detect(files, manifests)
        top = ", ".join(f"{k} {v}%" for k, v in list(detection.language_percentages().items())[:4])
        reporter.log("detect", f"Languages: {top or 'none detected'}")
        if detection.frameworks:
            reporter.log("detect", f"Frameworks & tools: {', '.join(detection.frameworks)}")
        reporter.complete("detect", top)
        return detection


def _parse(work: _Work, reporter: JobReporter) -> None:
    assert work.filtered is not None
    with reporter.step("parse"):
        files = work.filtered.files
        failures = 0
        for index, file in enumerate(files, start=1):
            try:
                parsed = parse_source(file.language, work.texts[file.path])
            except Exception as exc:  # one bad file must not sink the repo
                failures += 1
                logger.warning("parse_failed", path=file.path, error=str(exc))
                parsed = None
            if parsed is not None:
                work.parsed[file.path] = parsed
            if index % 100 == 0 or index == len(files):
                reporter.progress("parse", index / len(files), f"{index}/{len(files)} files")
        symbols = sum(len(p.symbols) for p in work.parsed.values())
        reporter.log("parse", f"Parsed {len(work.parsed)} files, found {symbols} symbols")
        if failures:
            reporter.log("parse", f"{failures} file(s) could not be parsed", level="warning")
        reporter.complete("parse", f"{symbols} symbols")


def _chunk(work: _Work, reporter: JobReporter) -> None:
    assert work.filtered is not None
    with reporter.step("chunk"):
        files = work.filtered.files
        for index, file in enumerate(files, start=1):
            parsed = work.parsed.get(file.path)
            work.chunks.extend(
                chunk_file(
                    file.path,
                    file.language,
                    work.texts[file.path],
                    parsed.symbols if parsed else None,
                )
            )
            if index % 200 == 0 or index == len(files):
                reporter.progress("chunk", index / len(files), f"{len(work.chunks)} chunks")
        reporter.complete("chunk", f"{len(work.chunks)} chunks")


def _store(work: _Work, repo: Repository, detection: Any, reporter: JobReporter) -> dict[str, Any]:
    assert work.filtered is not None
    with reporter.step("store"):
        all_paths = {f.path for f in work.filtered.files}
        edges = build_edges(work.parsed, all_paths, detection.go_module)

        index_store.clear_repo_index(repo.pk)
        index_store.save_blobs({work.blob_shas[p]: work.texts[p] for p in all_paths})
        reporter.progress("store", 0.3, "Saved file contents")
        file_docs = []
        total_lines = 0
        for file in work.filtered.files:
            lines = work.texts[file.path].count("\n") + 1
            total_lines += lines
            parsed = work.parsed.get(file.path)
            file_docs.append(
                {
                    "path": file.path,
                    "language": file.language,
                    "size": file.size,
                    "lines": lines,
                    "blob_sha": work.blob_shas[file.path],
                    "symbols": [s.as_dict() for s in parsed.symbols] if parsed else [],
                    "package": parsed.package if parsed else None,
                    "parse_errors": bool(parsed and parsed.has_errors),
                }
            )
        index_store.save_files(repo.pk, file_docs)
        reporter.progress("store", 0.6, "Saved file index")
        index_store.save_chunks(repo.pk, (c.as_document() for c in work.chunks))
        index_store.save_edges(repo.pk, (e.as_document() for e in edges))
        internal = sum(1 for e in edges if not e.external)
        reporter.log(
            "store",
            f"Stored {len(file_docs)} files, {len(work.chunks)} chunks, "
            f"{internal} internal and {len(edges) - internal} external dependency edges",
        )
        reporter.complete("store", "Index saved")
        return {
            "files": len(file_docs),
            "lines": total_lines,
            "bytes": work.filtered.total_bytes,
            "chunks": len(work.chunks),
            "symbols": sum(len(p.symbols) for p in work.parsed.values()),
            "dependency_edges": internal,
            "external_dependencies": len({e.dst for e in edges if e.external}),
            "skipped": dict(work.filtered.skipped),
        }
