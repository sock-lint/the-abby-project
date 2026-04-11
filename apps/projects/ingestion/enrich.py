"""Pipeline stage that asks Claude to enrich an ingested item.

No-op when ``ANTHROPIC_API_KEY`` is not set. The stage writes structured
suggestions to ``item.ai_suggestions`` but does NOT mutate the existing
``title``, ``description``, ``steps``, ``milestones``, ``materials``, or
``resources`` fields — the frontend renders AI suggestions as opt-in chips
so the child can accept or ignore them.
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
    "steps": [
        {
            "title": "string — short 'do this next' instruction (max 60 chars)",
            "description": "string — 1-3 kid-friendly sentences",
        }
    ],
    "resources": [
        {
            "title": "string — short display title",
            "url": "string — absolute URL",
            "resource_type": "link | video | doc | image",
            "step_index": "integer|null — 0-based index into steps, null for project-level",
        }
    ],
}


PROMPT = (
    "You are helping a teen categorize a maker project for their summer "
    "project tracker. Based on the project content below, return a JSON "
    "object with these keys: category (string), difficulty (int 1-5), "
    "skill_tags (array of short skill names), extra_materials (array of "
    "objects with name/description/estimated_cost), summary (a 1-2 "
    "sentence kid-friendly summary), steps, and resources.\n\n"
    "The ``steps`` array should contain 4-10 ordered, kid-friendly "
    "walkthrough instructions derived from the content — these are 'do "
    "this next' instructions, NOT payment goals. Each step has a short "
    "``title`` and a 1-3 sentence ``description``. Keep the tone warm "
    "and encouraging; avoid jargon.\n\n"
    "The ``resources`` array should contain any high-value reference URLs "
    "found in the content (videos, docs, inspiration pages). Use "
    "``resource_type`` of 'video' for video links, 'doc' for documents, "
    "'image' for images, and 'link' otherwise. Attach each resource to a "
    "step via ``step_index`` (0-based) when it clearly supports one step; "
    "otherwise set ``step_index`` to null for project-level references. "
    "Only include URLs that are absolute (starting with http).\n\n"
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
                # Bumped from 1024 to 2048: the response now carries ordered
                # walkthrough steps and per-step resources alongside the
                # original category/difficulty/skill_tags payload.
                max_tokens=2048,
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
