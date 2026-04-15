"""Portfolio (project photo) MCP tools — read-only."""
from __future__ import annotations

from typing import Any

from django.db.models import Sum

from apps.portfolio.models import ProjectPhoto
from apps.projects.models import Project, User
from apps.timecards.models import TimeEntry

from ..context import get_current_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    GetPortfolioSummaryIn,
    ListPortfolioMediaIn,
    ListProjectPhotosIn,
)
from ..server import tool
from ..shapes import project_photo_to_dict


def _resolve_target(user, requested_id: int | None) -> User:
    if requested_id is None or requested_id == user.id:
        return user
    if user.role != "parent":
        raise MCPPermissionDenied("Children can only view their own portfolio.")
    try:
        return User.objects.get(pk=requested_id)
    except User.DoesNotExist:
        raise MCPNotFoundError(f"User {requested_id} not found.")


@tool()
@safe_tool
def list_project_photos(params: ListProjectPhotosIn) -> dict[str, Any]:
    """List ProjectPhoto rows attached to a project (read-only)."""
    user = get_current_user()
    qs = ProjectPhoto.objects.select_related("project").filter(
        project_id=params.project_id,
    )
    if user.role != "parent":
        qs = qs.filter(project__assigned_to=user)

    photos = list(qs.order_by("-uploaded_at"))
    if not photos:
        # Check whether the project exists at all — raises if not visible.
        try:
            Project.objects.get(pk=params.project_id)
        except Project.DoesNotExist:
            raise MCPNotFoundError(f"Project {params.project_id} not found.")

    return {"photos": [project_photo_to_dict(p) for p in photos]}


@tool()
@safe_tool
def get_portfolio_summary(params: GetPortfolioSummaryIn) -> dict[str, Any]:
    """Aggregate counts for a user's portfolio: projects, photos, hours."""
    user = get_current_user()
    target = _resolve_target(user, params.user_id)

    completed_projects = Project.objects.filter(
        assigned_to=target, status="completed",
    ).count()
    total_photos = ProjectPhoto.objects.filter(project__assigned_to=target).count()
    total_minutes = TimeEntry.objects.filter(
        user=target, status="completed",
    ).aggregate(total=Sum("duration_minutes"))["total"] or 0

    return {
        "user_id": target.id,
        "completed_projects": completed_projects,
        "total_photos": total_photos,
        "total_hours": round(total_minutes / 60, 1),
    }


@tool()
@safe_tool
def list_portfolio_media(params: ListPortfolioMediaIn) -> dict[str, Any]:
    """Aggregated recent work: project photos + approved homework proofs.

    Returns a unified, chronologically-sorted list so an LLM can answer
    "show me Abby's recent work" with one call. Each entry has a
    ``kind`` discriminator ("project_photo" | "homework_proof") plus
    enough metadata to render a tile.
    """
    from apps.homework.models import HomeworkProof

    user = get_current_user()
    target = _resolve_target(user, params.user_id)

    photos = list(
        ProjectPhoto.objects.select_related("project")
        .filter(project__assigned_to=target)
        .order_by("-uploaded_at")[: params.limit],
    )
    proofs = list(
        HomeworkProof.objects.select_related("submission__assignment")
        .filter(
            submission__user=target,
            submission__status="approved",
        )
        .order_by("-submission__created_at")[: params.limit],
    )

    items: list[dict[str, Any]] = []
    for p in photos:
        items.append({
            "kind": "project_photo",
            "id": p.id,
            "project_id": p.project_id,
            "project_title": p.project.title,
            "image_url": p.image.url if p.image else None,
            "caption": getattr(p, "caption", ""),
            "uploaded_at": p.uploaded_at.isoformat() if p.uploaded_at else None,
        })
    for pr in proofs:
        sub = pr.submission
        items.append({
            "kind": "homework_proof",
            "id": pr.id,
            "submission_id": sub.id,
            "assignment_title": sub.assignment.title,
            "image_url": pr.image.url if pr.image else None,
            "caption": "",
            "uploaded_at": sub.created_at.isoformat() if sub.created_at else None,
        })

    items.sort(key=lambda x: x.get("uploaded_at") or "", reverse=True)
    items = items[: params.limit]
    return {"media": items, "count": len(items)}
