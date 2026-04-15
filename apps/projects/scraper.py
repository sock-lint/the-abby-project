"""Backward-compatible shim over the ingestion package.

Keeps the original ``scrape_instructables`` contract (dict with title, author,
thumbnail_url, step_count, category, url) used by
:class:`InstructablesPreviewView`. New code should use
``apps.ingestion.pipeline`` directly.
"""
from __future__ import annotations

from apps.ingestion.pipeline.instructables import InstructablesIngestor


def scrape_instructables(url: str) -> dict:
    result = InstructablesIngestor(url).ingest()
    return {
        "title": result.title,
        "author": "",  # no longer extracted; keep key for frontend compatibility
        "thumbnail_url": result.cover_photo_url or "",
        "step_count": len(result.milestones),
        "category": result.category_hint or "",
        "url": url,
    }
