"""Portfolio (project photo) MCP tools — read-only."""
from __future__ import annotations

from typing import Any

from django.db.models import Sum

from apps.portfolio.models import ProjectPhoto
from apps.projects.models import Project, User
from apps.timecards.models import TimeEntry

from ..context import get_current_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import GetPortfolioSummaryIn, ListProjectPhotosIn
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
