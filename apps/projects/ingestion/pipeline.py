"""Scrapy-style Item Pipeline for project ingestion.

Each Stage takes an :class:`IngestionItem` and a ``context`` dict and returns
the (possibly mutated) item. Stages run sequentially; a stage may raise
:class:`StageSkip` to bail out cleanly or append to
``item.pipeline_warnings`` for non-fatal issues.

The default pipeline is:

    ParseStage -> NormalizeStage -> MarkdownStage -> EnrichStage

FetchStage and PersistStage are intentionally NOT part of the default
pipeline — fetching is handled inside the per-source ingestor
(``InstructablesIngestor`` etc.) via the existing ``fetch_cached`` helper,
and persistence lives in the Celery task (``run_ingestion_job``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .base import IngestionItem


class StageSkip(Exception):
    """Raised by a stage to stop the pipeline without marking the job failed."""


class Stage(Protocol):
    name: str

    def __call__(self, item: IngestionItem, context: dict[str, Any]) -> IngestionItem: ...


@dataclass
class Pipeline:
    stages: list[Stage]
    on_warning: Callable[[str], None] | None = None

    def run(self, item: IngestionItem, context: dict[str, Any] | None = None) -> IngestionItem:
        ctx = context or {}
        for stage in self.stages:
            stage_name = getattr(stage, "name", stage.__class__.__name__)
            try:
                item = stage(item, ctx) or item
            except StageSkip:
                break
            except Exception as exc:  # noqa: BLE001 - non-fatal, record and continue
                msg = f"{stage_name}: {exc}"
                item.pipeline_warnings.append(msg)
                if self.on_warning:
                    self.on_warning(msg)
        return item


# ---- built-in stages ------------------------------------------------------


@dataclass
class ParseStage:
    """Delegate to the per-source ingestor's ``ingest`` method.

    The ingestor is stored on the stage instance so the pipeline doesn't need
    to know about fetching / parsing specifics.
    """

    ingestor: Any
    name: str = "parse"

    def __call__(self, item: IngestionItem, context: dict[str, Any]) -> IngestionItem:
        parsed = self.ingestor.ingest()
        # Preserve any pipeline-level fields already on ``item``.
        parsed.pipeline_warnings = list(item.pipeline_warnings) + list(parsed.pipeline_warnings)
        return parsed


@dataclass
class NormalizeStage:
    """Deduplicate materials/steps and clamp obvious overflows."""

    name: str = "normalize"
    max_title: int = 200
    max_description: int = 5000

    def __call__(self, item: IngestionItem, context: dict[str, Any]) -> IngestionItem:
        if item.title and len(item.title) > self.max_title:
            item.title = item.title[: self.max_title].rstrip()
        if item.description and len(item.description) > self.max_description:
            item.description = item.description[: self.max_description].rstrip() + "…"

        # Dedupe materials by lowered name.
        seen_materials: set[str] = set()
        deduped_materials = []
        for mat in item.materials:
            key = (mat.name or "").strip().lower()
            if not key or key in seen_materials:
                continue
            seen_materials.add(key)
            deduped_materials.append(mat)
        item.materials = deduped_materials

        # Reindex step order if missing.
        for idx, s in enumerate(item.steps):
            if not s.order:
                s.order = idx
        return item


def default_pipeline(ingestor: Any) -> Pipeline:
    """Assemble the default ingestion pipeline for a given source ingestor.

    Workstream 3 adds ``MarkdownStage`` and ``EnrichStage`` on top of this.
    """
    stages: list[Stage] = [
        ParseStage(ingestor=ingestor),
        NormalizeStage(),
    ]
    # Lazy imports so Workstream 3 modules are optional.
    try:
        from .markdown import MarkdownStage  # type: ignore
        stages.append(MarkdownStage())
    except ImportError:
        pass
    try:
        from .enrich import EnrichStage  # type: ignore
        stages.append(EnrichStage())
    except ImportError:
        pass
    return Pipeline(stages=stages)
