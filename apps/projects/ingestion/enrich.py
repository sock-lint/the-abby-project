"""Pipeline stage that asks Claude to enrich an ingested item.

No-op when ``ANTHROPIC_API_KEY`` is not set. The stage writes structured
suggestions to ``item.ai_suggestions`` but does NOT mutate the existing
``title``, ``description``, ``milestones``, or ``materials`` fields —
the frontend renders AI suggestions as opt-in chips so the child can
accept or ignore them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .base import IngestionItem


SUGGESTION_SCHEMA = {
    "category": "string — best-fit category name",
    "difficulty": "integer 1-5",
    "skill_tags": ["array of skill names relevant to the project"],
    "extra_materials": [
        {"name": "string", "description": "string", "estimated_cost": "number|null"}
    ],
    "summary": "string — 1-2 sentence plain-English summary for a kid",
}


PROMPT = (
    "You are helping a teen categorize a maker project for their summer "
    "project tracker. Based on the project content below, return a JSON "
    "object with these keys: category (string), difficulty (int 1-5), "
    "skill_tags (array of short skill names), extra_materials (array of "
    "objects with name/description/estimated_cost), and summary (a 1-2 "
    "sentence kid-friendly summary).\n\n"
    "Return ONLY the JSON object, no other text.\n\n"
    "Available categories: {categories}\n\n"
    "Project title: {title}\n\n"
    "Project content (markdown):\n{markdown}\n"
)


@dataclass
class EnrichStage:
    name: str = "enrich"
    max_content_chars: int = 12_000

    def __call__(self, item: IngestionItem, context: dict[str, Any]) -> IngestionItem:
        from django.conf import settings
        api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
        if not api_key:
            return item

        content = item.markdown or item.description or ""
        if not content.strip():
            return item

        try:
            import anthropic  # type: ignore
        except ImportError:
            item.pipeline_warnings.append("enrich: anthropic package not installed")
            return item

        # Keep this import local so the pipeline module stays Django-agnostic.
        from apps.projects.models import SkillCategory
        categories = list(SkillCategory.objects.values_list("name", flat=True))

        try:
            client = anthropic.Anthropic(api_key=api_key)
            prompt = PROMPT.format(
                categories=", ".join(categories) or "(none)",
                title=item.title or "(untitled)",
                markdown=content[: self.max_content_chars],
            )
            message = client.messages.create(
                model=getattr(settings, "CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = (message.content[0].text or "").strip()
            if text.startswith("```"):
                # Strip code fences if Claude returned them.
                text = text.strip("`")
                if text.startswith("json"):
                    text = text[4:].strip()
            suggestions = json.loads(text)
            if isinstance(suggestions, dict):
                item.ai_suggestions = suggestions
        except Exception as exc:  # noqa: BLE001
            item.pipeline_warnings.append(f"enrich: {exc}")
        return item
