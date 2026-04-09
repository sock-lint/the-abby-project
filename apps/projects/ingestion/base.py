"""Shared types and helpers for project source ingestion."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

import requests
from django.core.cache import cache


USER_AGENT = "Mozilla/5.0 (compatible; TheAbbyProject/1.0)"
FETCH_TIMEOUT = 15
CACHE_TTL_SECONDS = 86400  # 24h


@dataclass
class MilestoneDraft:
    title: str
    description: str = ""
    order: int = 0

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
    milestones: list[MilestoneDraft] = field(default_factory=list)
    materials: list[MaterialDraft] = field(default_factory=list)
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
            "milestones": [m.to_dict() for m in self.milestones],
            "materials": [m.to_dict() for m in self.materials],
            "warnings": list(self.warnings),
            # Additive fields — safe for existing frontend consumers.
            "markdown": self.markdown,
            "ai_suggestions": self.ai_suggestions,
            "pipeline_warnings": list(self.pipeline_warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IngestionResult":
        return cls(
            title=data.get("title", "") or "",
            description=data.get("description", "") or "",
            cover_photo_url=data.get("cover_photo_url"),
            source_url=data.get("source_url"),
            source_type=data.get("source_type", "url"),
            category_hint=data.get("category_hint"),
            difficulty_hint=data.get("difficulty_hint"),
            milestones=[MilestoneDraft(**m) for m in data.get("milestones", [])],
            materials=[MaterialDraft(**m) for m in data.get("materials", [])],
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
        """GET a URL with a 24h Redis cache and standard User-Agent."""
        key = f"{cache_prefix}:{hashlib.md5(url.encode()).hexdigest()}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            resp = requests.get(
                url, timeout=FETCH_TIMEOUT, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(f"Failed to fetch URL: {exc}") from exc
        cache.set(key, resp.text, timeout=CACHE_TTL_SECONDS)
        return resp.text
