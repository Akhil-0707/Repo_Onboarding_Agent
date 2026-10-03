"""Run the analysis agent section by section, checkpointing as it goes.

Per section: a short tool-using research loop (notes), then a focused structured-output call
validated against the section's Pydantic schema, then reference repair. Finished sections are
never redone. When the model server disappears (``ModelOfflineError``) the in-progress
conversation is checkpointed and the job waits; ``resume_waiting_analyses`` restarts it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from django.conf import settings
from django.utils import timezone
from pydantic import BaseModel

from apps.agents.citations import FileIndex, RefReport, load_file_index
from apps.agents.digest import build_digest
from apps.agents.loop import AgentLogger, AgentLoop, BudgetExceededError, TokenBudget, Usage
from apps.agents.prompts import research_messages, structure_messages
from apps.agents.structured import StructuredOutputError, generate_structured
from apps.agents.tools import ToolContext
from apps.analysis.models import Analysis, AnalysisStatus
from apps.analysis.sections import SECTIONS, SectionCheckError, SectionSpec
from apps.common.logging import get_logger
from apps.ingestion.pipeline import job_is_failed
from apps.ingestion.progress import JobReporter
from apps.llm.client import LLMClient, get_llm_client
from apps.llm.cost import estimate_cost
from apps.llm.errors import LLMRequestError, ModelOfflineError
from apps.llm.health import check_llm_health
from apps.repos.models import IngestionJob, JobStatus, Repository

logger = get_logger(__name__)

STEP = "analyze"


def model_available() -> bool:
    return check_llm_health(force=True).online


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AnalysisRunner:
    def __init__(self, job_id: str, llm: LLMClient | None = None) -> None:
        self.job_id = str(job_id)
        self.job = IngestionJob.objects.select_related("repository").get(pk=self.job_id)
        self.repo: Repository = self.job.repository
        self.llm = llm or get_llm_client()
        self.reporter = JobReporter(self.job_id)
        self.analysis, _ = Analysis.objects.get_or_create(repository=self.repo)
        usage = self.analysis.usage or {}
        self.usage = Usage(
            calls=usage.get("calls", 0),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=usage.get("latency_ms", 0),
        )
        self.budget = TokenBudget(
            settings.ANALYSIS_TOKEN_BUDGET,
            used=self.usage.prompt_tokens + self.usage.completion_tokens,
        )
        self.agent_logger = AgentLogger(str(self.repo.pk), scope="analysis", run_id=self.job_id)

    # --- persistence ----------------------------------------------------------------------
    def _save(self, **fields: Any) -> None:
        for name, value in fields.items():
            setattr(self.analysis, name, value)
        self.analysis.usage = self.usage.as_dict()
        self.analysis.est_cost = estimate_cost(
            self.usage.prompt_tokens, self.usage.completion_tokens
        )
        self.analysis.save()

    def _set_section(self, key: str, **state: Any) -> None:
        sections = dict(self.analysis.sections or {})
        sections[key] = {**(sections.get(key) or {}), **state, "updated_at": _now_iso()}
        self._save(sections=sections)

    def _checkpoint(self, section: str, phase: str, **data: Any) -> None:
        self._save(checkpoint={"section": section, "phase": phase, **data})

    # --- lifecycle -----------------------------------------------------------------------
    def _pause(self, reason: str) -> None:
        logger.info("analysis_waiting_for_model", repo=self.repo.full_name, reason=reason)
        self._save(
            status=AnalysisStatus.WAITING_FOR_MODEL,
            waiting_since=self.analysis.waiting_since or timezone.now(),
        )
        self.reporter.waiting(STEP, "Waiting for the AI model to come back online…")
        self.reporter.log(STEP, f"Paused: {reason}. Will resume automatically.", level="warning")

    def run(self) -> str:
        if job_is_failed(self.job_id):
            return "skipped"
        if not model_available():
            self._pause("model server offline")
            return "waiting"

        if self.analysis.status == AnalysisStatus.WAITING_FOR_MODEL:
            self.reporter.resumed()
            self.reporter.log(STEP, "Model is back online; resuming the analysis.")
        self._save(
            status=AnalysisStatus.RUNNING,
            model=self.llm.model_name,
            waiting_since=None,
            started_at=self.analysis.started_at or timezone.now(),
        )
        self.reporter._set_step(STEP, {"status": "running", "started_at": _now_iso()})

        ctx = ToolContext(self.repo)
        digest = build_digest(ctx)
        index = load_file_index(ctx)
        total = len(SECTIONS)
        for position, spec in enumerate(SECTIONS):
            if self.analysis.section_status(spec.key) == "done":
                continue
            self.reporter.progress(STEP, position / total, f"Writing {spec.label}…")
            try:
                self._run_section(spec, ctx, digest, index)
            except ModelOfflineError as exc:
                self._pause(str(exc))
                return "waiting"
            except BudgetExceededError as exc:
                self._fail_remaining(str(exc))
                break
            except (StructuredOutputError, SectionCheckError, LLMRequestError) as exc:
                logger.warning("section_failed", section=spec.key, error=str(exc))
                self._set_section(spec.key, status="failed", error=str(exc)[:500])
                self.reporter.log(
                    STEP, f"{spec.label} could not be generated: {exc}", level="warning"
                )
                self._save(checkpoint=None)

        return self._finish()

    def _fail_remaining(self, reason: str) -> None:
        for spec in SECTIONS:
            if self.analysis.section_status(spec.key) != "done":
                self._set_section(spec.key, status="failed", error=reason)
        self.reporter.log(STEP, reason, level="error")

    def _finish(self) -> str:
        statuses = [self.analysis.section_status(s.key) for s in SECTIONS]
        done = statuses.count("done")
        status = (
            AnalysisStatus.DONE
            if done == len(statuses)
            else AnalysisStatus.PARTIAL if done else AnalysisStatus.FAILED
        )
        self._save(status=status, checkpoint=None, finished_at=timezone.now())
        tokens = self.usage.prompt_tokens + self.usage.completion_tokens
        message = f"{done}/{len(statuses)} sections · {tokens:,} tokens"
        if status == AnalysisStatus.FAILED:
            self.reporter._set_step(STEP, {"status": "failed", "message": message})
        else:
            self.reporter.complete(STEP, message)
        # The repository itself is usable either way; the job is finished.
        self.reporter.finish(JobStatus.DONE)
        return str(status)

    # --- one section ---------------------------------------------------------------------
    def _run_section(
        self, spec: SectionSpec, ctx: ToolContext, digest: str, index: FileIndex
    ) -> None:
        self._set_section(spec.key, status="running", error="")
        checkpoint = self.analysis.checkpoint or {}
        resuming = checkpoint.get("section") == spec.key

        if resuming and checkpoint.get("phase") == "structure":
            notes = checkpoint.get("notes", "")
            self.reporter.log(STEP, f"{spec.label}: resuming from saved research notes.")
        else:
            messages = (
                checkpoint["messages"]
                if resuming and checkpoint.get("phase") == "research"
                else research_messages(spec.key, digest, settings.ANALYSIS_MAX_ITERATIONS)
            )
            start_iteration = checkpoint.get("iteration", 0) if resuming else 0
            if resuming:
                self.reporter.log(
                    STEP, f"{spec.label}: resuming research at step {start_iteration}."
                )

            iteration = {"n": start_iteration}

            def on_step(msgs: list[dict[str, Any]]) -> None:
                iteration["n"] += 1
                self._checkpoint(spec.key, "research", messages=msgs, iteration=iteration["n"])

            loop = AgentLoop(
                self.llm,
                ctx,
                tools=spec.tools,
                max_iterations=settings.ANALYSIS_MAX_ITERATIONS,
                budget=self.budget,
                max_repairs=settings.ANALYSIS_MAX_REPAIRS,
                max_context_chars=settings.ANALYSIS_MAX_CONTEXT_CHARS,
                agent_logger=self.agent_logger,
                on_step=on_step,
                on_tool_end=lambda event: self.reporter.log(STEP, f"{spec.label}: {event.summary}"),
                purpose=f"{spec.key}:research",
            )
            try:
                result = loop.run(messages, start_iteration=start_iteration)
            finally:
                self.usage.merge(loop.usage)
                loop.usage = Usage()
            notes = result.final_text
            self._checkpoint(spec.key, "structure", notes=notes)

        result: dict[str, Any] = {}

        def accept(output: BaseModel) -> None:
            # Verify references now so unusable output is sent back to the model for a fix.
            data = output.model_dump(mode="json")
            report = spec.repair(data, index)
            if spec.ensure:
                spec.ensure(
                    data, self.llm, budget=self.budget, usage=self.usage,
                    agent_logger=self.agent_logger,
                )  # fmt: skip
            if spec.check:
                spec.check(data)
            result.update(data=data, report=report)

        generate_structured(
            self.llm,
            structure_messages(spec.key, digest, notes, spec.schema, **spec.params(ctx)),
            spec.schema,
            max_tokens=spec.max_tokens,
            budget=self.budget,
            usage=self.usage,
            agent_logger=self.agent_logger,
            purpose=spec.key,
            accept=accept,
        )
        data: dict[str, Any] = result["data"]
        report: RefReport = result["report"]
        self._set_section(spec.key, status="done", data=data, error="", references=report.as_dict())
        self._save(checkpoint=None)
        self.reporter.log(
            STEP,
            f"{spec.label} done ({report.checked} references checked, {report.repaired} repaired, "
            f"{report.dropped} removed).",
        )
