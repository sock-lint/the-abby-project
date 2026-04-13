import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def get_project_suggestions(user):
    """
    Generate AI project suggestions based on user's skill progress and completed projects.
    Returns a list of suggestion dicts if the API key is available, otherwise returns
    curated fallback suggestions.
    """
    from apps.achievements.models import SkillProgress
    from apps.projects.models import Project, SkillCategory

    # Build user context
    completed = list(
        Project.objects.filter(assigned_to=user, status="completed")
        .values_list("title", "category__name", "difficulty")
    )
    skills = list(
        SkillProgress.objects.filter(user=user, level__gt=0)
        .select_related("skill", "skill__category")
        .values_list("skill__name", "skill__category__name", "level")
    )
    categories = list(SkillCategory.objects.values_list("name", flat=True))

    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return _fallback_suggestions(completed, skills, categories)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        completed_text = "\n".join(
            f"- {title} (category: {cat}, difficulty: {diff})"
            for title, cat, diff in completed
        ) or "None yet"

        skills_text = "\n".join(
            f"- {name} ({cat}): Level {level}"
            for name, cat, level in skills
        ) or "No skills leveled yet"

        message = client.messages.create(
            model=getattr(settings, "CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": (
                    "You are a project advisor for a teen's summer maker program. "
                    "Based on their completed projects and skill levels, suggest 3 new project ideas.\n\n"
                    f"Completed projects:\n{completed_text}\n\n"
                    f"Current skills:\n{skills_text}\n\n"
                    f"Available categories: {', '.join(categories)}\n\n"
                    "For each suggestion, provide a JSON array with objects containing:\n"
                    '- "title": project name\n'
                    '- "description": 2-3 sentence description\n'
                    '- "category": one of the available categories\n'
                    '- "difficulty": 1-5\n'
                    '- "estimated_hours": number\n'
                    '- "why": one sentence explaining why this is a good next project\n\n'
                    "Return ONLY the JSON array, no other text."
                ),
            }],
        )

        text = message.content[0].text.strip()
        # Extract JSON from response
        if text.startswith("["):
            suggestions = json.loads(text)
        else:
            # Try to find JSON array in the response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                suggestions = json.loads(text[start:end])
            else:
                return _fallback_suggestions(completed, skills, categories)

        return suggestions[:3]

    except Exception:
        logger.exception("AI project suggestions failed for user %s", user)
        return _fallback_suggestions(completed, skills, categories)


def _fallback_suggestions(completed, skills, categories):
    """Return curated suggestions when API is unavailable."""
    completed_cats = {cat for _, cat, _ in completed if cat}
    skill_cats = {cat for _, cat, _ in skills}
    all_cats = set(categories)

    # Suggest from unexplored categories first
    unexplored = all_cats - completed_cats - skill_cats
    suggestions = []

    starter_projects = {
        "Woodworking": {
            "title": "Simple Cutting Board",
            "description": "Make a hardwood cutting board using basic joinery. Great intro to measuring, cutting, and finishing wood.",
            "difficulty": 2, "estimated_hours": 6,
            "why": "A practical project that builds foundational woodworking skills.",
        },
        "Electronics": {
            "title": "Weather Station",
            "description": "Build a temperature and humidity monitor with an Arduino and LCD display.",
            "difficulty": 3, "estimated_hours": 8,
            "why": "Combines sensors, displays, and microcontroller programming.",
        },
        "Cooking": {
            "title": "Homemade Pasta Night",
            "description": "Learn to make fresh pasta from scratch — fettuccine, ravioli, and a simple sauce.",
            "difficulty": 2, "estimated_hours": 4,
            "why": "Hands-on kitchen skills with a delicious result.",
        },
        "Art & Crafts": {
            "title": "Watercolor Landscape Series",
            "description": "Paint 5 landscape scenes in watercolor, learning wet-on-wet and dry brush techniques.",
            "difficulty": 2, "estimated_hours": 10,
            "why": "Develops patience, color mixing, and composition skills.",
        },
        "Coding": {
            "title": "Personal Portfolio Website",
            "description": "Build a responsive personal website to showcase your maker projects using HTML, CSS, and JavaScript.",
            "difficulty": 3, "estimated_hours": 12,
            "why": "Creates something useful while learning web development fundamentals.",
        },
        "Outdoors": {
            "title": "Raised Garden Bed",
            "description": "Design and build a small raised garden bed, plant herbs or vegetables, and document the growth.",
            "difficulty": 2, "estimated_hours": 8,
            "why": "Combines construction skills with biology and patience.",
        },
        "Sewing & Textiles": {
            "title": "Tote Bag with Pockets",
            "description": "Sew a sturdy canvas tote bag with interior pockets and custom embellishments.",
            "difficulty": 2, "estimated_hours": 5,
            "why": "A practical project that teaches machine sewing fundamentals.",
        },
        "Science": {
            "title": "Water Quality Testing Kit",
            "description": "Build a simple water testing kit and analyze samples from different sources around your home.",
            "difficulty": 3, "estimated_hours": 6,
            "why": "Real science with measurement, documentation, and analysis.",
        },
    }

    # Prioritize unexplored categories
    for cat in list(unexplored)[:2]:
        if cat in starter_projects:
            proj = starter_projects[cat].copy()
            proj["category"] = cat
            suggestions.append(proj)

    # Fill remaining with skill-adjacent projects
    for cat in list(skill_cats)[:3]:
        if cat in starter_projects and len(suggestions) < 3:
            proj = starter_projects[cat].copy()
            proj["category"] = cat
            proj["difficulty"] = min(5, proj["difficulty"] + 1)
            proj["why"] = f"Builds on your existing {cat} skills with a new challenge."
            suggestions.append(proj)

    # Fill with any remaining
    for cat in list(all_cats):
        if len(suggestions) >= 3:
            break
        if cat in starter_projects and not any(s["category"] == cat for s in suggestions):
            proj = starter_projects[cat].copy()
            proj["category"] = cat
            suggestions.append(proj)

    return suggestions[:3]
