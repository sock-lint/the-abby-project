"""Shared types and helpers for project source ingestion."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from django.core.cache import cache

from config.url_safety import UnsafeURLError, safe_get


USER_AGENT = "Mozilla/5.0 (compatible; TheAbbyProject/1.0)"
FETCH_TIMEOUT = 15
CACHE_TTL_SECONDS = 86400  # 24h


@dataclass
class StepDraft:
    """An ordered walkthrough instruction ('do this next').

    Distinct from ``MilestoneDraft``: steps are instructional, not tied to
    payments. Ingestors populate ``IngestionResult.steps`` with these; the
    commit path materializes them as ``ProjectStep`` rows.

    ``milestone_index`` is an optional 0-based index into
    ``IngestionResult.milestones`` — the commit path resolves it to a real
    ``ProjectMilestone.pk`` so steps can be grouped under their phase. Leave
    ``None`` for a loose / unassigned step.
    """
    title: str
    description: str = ""
    order: int = 0
    milestone_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Backwards-compat alias for the pre-steps naming. Still exported so any
# external code referencing ``MilestoneDraft`` continues to work, but new
# ingestors should construct ``StepDraft`` explicitly.
MilestoneDraft = StepDraft


@dataclass
class ResourceDraft:
    """A reference link (video, doc, inspiration) for a project or step.

    ``step_index`` is a 0-based index into ``IngestionResult.steps`` — the
    commit path resolves it to a real ``ProjectStep.pk``. Leave as ``None``
    to produce a project-level resource.
    """
    url: str
    title: str = ""
    resource_type: str = "link"  # link | video | doc | image
    order: int = 0
    step_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MaterialDraft:
    name: str
    description: str = ""
    estimated_cost: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IngestionResult:
    """Normalized draft returned by every ingestor."""

    title: str = ""
    description: str = ""
    cover_photo_url: str | None = None
    source_url: str | None = None
    source_type: str = "url"  # instructables | url | pdf
    category_hint: str | None = None
    difficulty_hint: int | None = None
    # Walkthrough steps (ordered "do this next" instructions). Populated by
    # ingestors; previously known as ``milestones`` — see ``from_dict`` shim.
    steps: list[StepDraft] = field(default_factory=list)
    # Goal-based milestones with optional ``bonus_amount``. Ingestors no
    # longer populate these — they stay empty unless a parent adds them from
    # the preview. The key remains in ``to_dict`` for frontend compatibility.
    milestones: list[StepDraft] = field(default_factory=list)
    materials: list[MaterialDraft] = field(default_factory=list)
    resources: list[ResourceDraft] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_html: str | None = None
    markdown: str | None = None
    ai_suggestions: dict[str, Any] | None = None
    pipeline_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "cover_photo_url": self.cover_photo_url,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "category_hint": self.category_hint,
            "difficulty_hint": self.difficulty_hint,
            "steps": [s.to_dict() for s in self.steps],
            "milestones": [m.to_dict() for m in self.milestones],
            "materials": [m.to_dict() for m in self.materials],
            "resources": [r.to_dict() for r in self.resources],
            "warnings": list(self.warnings),
            # Additive fields — safe for existing frontend consumers.
            "markdown": self.markdown,
            "ai_suggestions": self.ai_suggestions,
            "pipeline_warnings": list(self.pipeline_warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngestionResult":
        # Legacy shim: staging rows written before the steps/resources split
        # only have ``milestones``. Rehydrate them into ``steps`` so in-flight
        # jobs don't lose their walkthrough content across the deploy.
        raw_steps = data.get("steps")
        raw_milestones = data.get("milestones") or []
        if raw_steps is None:
            steps = [StepDraft(**m) for m in raw_milestones]
            milestones: list[StepDraft] = []
        else:
            steps = [StepDraft(**s) for s in raw_steps]
            milestones = [StepDraft(**m) for m in raw_milestones]

        return cls(
            title=data.get("title", "") or "",
            description=data.get("description", "") or "",
            cover_photo_url=data.get("cover_photo_url"),
            source_url=data.get("source_url"),
            source_type=data.get("source_type", "url"),
            category_hint=data.get("category_hint"),
            difficulty_hint=data.get("difficulty_hint"),
            steps=steps,
            milestones=milestones,
            materials=[MaterialDraft(**m) for m in data.get("materials", [])],
            resources=[ResourceDraft(**r) for r in data.get("resources", [])],
            warnings=list(data.get("warnings", [])),
        )


# Alias: pipeline stages operate on an "item" regardless of source.
IngestionItem = IngestionResult


class BaseIngestor:
    """Subclasses implement ``ingest`` and return an :class:`IngestionResult`."""

    source_type = "url"

    def ingest(self) -> IngestionResult:  # pragma: no cover - interface
        raise NotImplementedError

    # ---- shared helpers -------------------------------------------------

    @staticmethod
    def fetch_cached(url: str, cache_prefix: str) -> str:
        """GET a URL with a 24h Redis cache and standard User-Agent.

        Audit H4: routes through ``safe_get`` so a parent-supplied
        ingestion URL can't aim at cloud-metadata, loopback, or LAN-only
        hosts. ``UnsafeURLError`` is re-raised as ``ValueError`` (the
        existing exception contract for this method) so the per-source
        ingestors keep their single-error-class handling.
        """
        key = f"{cache_prefix}:{hashlib.md5(url.encode()).hexdigest()}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            resp = safe_get(
                url, timeout=FETCH_TIMEOUT, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
        except UnsafeURLError as exc:
            raise ValueError(f"Refused to fetch URL: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"Failed to fetch URL: {exc}") from exc
        cache.set(key, resp.text, timeout=CACHE_TTL_SECONDS)
        return resp.text

    @staticmethod
    def add_missing_section_warnings(
        result: IngestionResult,
        *,
        source_label: str = "",
    ) -> None:
        """Append standard warnings when steps / materials were not parsed.

        ``source_label`` (e.g. ``"in PDF"``) is interpolated so each ingestor
        can produce a source-appropriate message without cloning the logic.
        """
        suffix = f" {source_label}" if source_label else ""
        if not result.steps:
            result.warnings.append(
                f"No walkthrough steps found{suffix} — add steps manually."
            )
        if not result.materials:
            result.warnings.append(
                f"No materials list found{suffix} — add materials manually."
            )
