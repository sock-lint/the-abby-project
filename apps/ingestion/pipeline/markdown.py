"""Pipeline stage that converts raw HTML on the item into clean Markdown.

We prefer ``crawl4ai`` when installed (LLM-friendly, handles JS-rendered
quirks) and fall back to ``markdownify`` if present. If neither is
available, the stage is a no-op and records a pipeline warning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .base import IngestionItem

logger = logging.getLogger(__name__)


@dataclass
class MarkdownStage:
    name: str = "markdown"
    max_chars: int = 40_000

    def __call__(self, item: IngestionItem, context: dict[str, Any]) -> IngestionItem:
        html = item.raw_html
        if not html:
            # Per-source ingestors may not populate raw_html yet; try to
            # synthesize a minimal markdown from title + description.
            if item.title or item.description:
                md = f"# {item.title}\n\n{item.description}".strip()
                item.markdown = md[: self.max_chars]
            return item

        md = _html_to_markdown(html)
        if md is None:
            item.pipeline_warnings.append(
                "markdown: no converter available (install crawl4ai or markdownify)"
            )
            return item
        item.markdown = md[: self.max_chars]
        return item


def _html_to_markdown(html: str) -> str | None:
    # Preferred: crawl4ai's HTML->markdown helper
    try:
        from crawl4ai.content_scraping_strategy import (  # type: ignore
            DefaultMarkdownGenerator,
        )
        gen = DefaultMarkdownGenerator()
        result = gen.generate_markdown(cleaned_html=html)
        # crawl4ai versions differ; try common attribute names.
        for attr in ("markdown_with_citations", "markdown", "raw_markdown"):
            value = getattr(result, attr, None)
            if value:
                return str(value)
    except Exception:  # noqa: BLE001 - fall through to next strategy
        logger.warning("crawl4ai markdown conversion failed, trying fallback", exc_info=True)

    # Fallback: markdownify
    try:
        from markdownify import markdownify as md  # type: ignore
        return md(html, heading_style="ATX")
    except Exception:  # noqa: BLE001
        logger.warning("markdownify conversion failed", exc_info=True)
        return None
