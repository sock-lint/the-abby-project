"""Vision helpers for homework submissions.

``estimate_effort_from_proof`` asks Claude to look at a single proof
image and return an integer effort level 1-5. Used by
``HomeworkService.submit_completion`` when an assignment was authored by
a child and has ``rewards_pending_review=True``.

Follows the same lazy-import / direct-settings-read pattern used by
``HomeworkService.plan_assignment`` and ``apps/ingestion/pipeline/enrich.py``
— no shared Anthropic client abstraction exists yet, so we match the
existing convention.
"""
import base64
import json
import logging

from django.conf import settings


logger = logging.getLogger(__name__)


_EFFORT_PROMPT = (
    "You are helping rate the effort a child put into a completed homework "
    "assignment. Look at the image and return ONLY a JSON object:\n"
    '{"effort_level": 1-5, "reasoning": "one short sentence"}\n\n'
    "Rate on this scale:\n"
    "  1 = trivial / a few minutes (matching, circling, single sentence)\n"
    "  2 = light (short worksheet, 3-5 quick answers)\n"
    "  3 = typical homework (full worksheet, paragraph, or standard practice)\n"
    "  4 = substantial (multi-part problem set, short essay, project step)\n"
    "  5 = major (long essay, detailed project, extensive problem set)\n\n"
    "Homework context:\n"
    "Title: {title}\n"
    "Subject: {subject}\n"
    "Description: {description}\n"
)


def estimate_effort_from_proof(image_bytes, assignment, media_type="image/jpeg"):
    """Ask Claude to rate the effort on a scale of 1-5 from a proof image.

    Returns the effort level as an int clamped to ``[1, 5]``. Raises on
    any failure (missing API key, network error, parse failure) so the
    caller can fall back to a zero snapshot + parent Adjust flow.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured.")

    try:
        import anthropic  # type: ignore
    except ImportError as exc:
        raise RuntimeError("AI effort estimation requires the 'anthropic' package.") from exc

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    prompt = _EFFORT_PROMPT.format(
        title=assignment.title,
        subject=assignment.get_subject_display(),
        description=(assignment.description or "(none)")[:2000],
    )

    # Anthropic's vision endpoint expects one of a small set of media
    # types; default anything unexpected to image/jpeg.
    allowed_media = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if media_type not in allowed_media:
        media_type = "image/jpeg"

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=getattr(settings, "CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            },
        ],
    )
    text = (message.content[0].text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    payload = json.loads(text)
    effort = int(payload.get("effort_level", 3))
    return max(1, min(5, effort))
