"""Portfolio (project photo) MCP tools.

Read-side: list / summary / media. Write-side: blob-first photo + proof
deletion (mirrors REST destroy). The ZIP export tool returns a manifest
of what *would* be in the archive — the actual bytes are downloaded via
``GET /api/portfolio/export/`` since MCP doesn't transport binary blobs.
"""
from __future__ import annotations

from typing import Any

from django.db.models import Sum

from apps.portfolio.models import ProjectPhoto
from apps.accounts.models import User
from apps.projects.models import Project
from apps.timecards.models import TimeEntry

from ..context import get_current_user
from ..errors import MCPNotFoundError, MCPPermissionDenied, safe_tool
from ..schemas import (
    DeleteHomeworkProofIn,
    DeleteProjectPhotoIn,
    ExportPortfolioIn,
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


@tool()
@safe_tool
def delete_project_photo(params: DeleteProjectPhotoIn) -> dict[str, Any]:
    """Delete a project photo (owner or parent). Blob-first."""
    user = get_current_user()
    try:
        photo = ProjectPhoto.objects.select_related("project").get(pk=params.photo_id)
    except ProjectPhoto.DoesNotExist:
        raise MCPNotFoundError(f"ProjectPhoto {params.photo_id} not found.")
    if user.role != "parent" and photo.user_id != user.id:
        raise MCPPermissionDenied("You can only delete your own photos.")
    if photo.image:
        photo.image.delete(save=False)
    photo.delete()
    return {"deleted": True, "photo_id": params.photo_id}


@tool()
@safe_tool
def delete_homework_proof(params: DeleteHomeworkProofIn) -> dict[str, Any]:
    """Delete a single homework-proof image (owner or parent). Blob-first.

    The parent ``HomeworkSubmission`` row is preserved so approval history
    stays intact.
    """
    from apps.homework.models import HomeworkProof

    user = get_current_user()
    try:
        proof = HomeworkProof.objects.select_related("submission").get(pk=params.proof_id)
    except HomeworkProof.DoesNotExist:
        raise MCPNotFoundError(f"HomeworkProof {params.proof_id} not found.")
    if user.role != "parent" and proof.submission.user_id != user.id:
        raise MCPPermissionDenied("You can only delete your own proofs.")
    if proof.image:
        proof.image.delete(save=False)
    proof.delete()
    return {"deleted": True, "proof_id": params.proof_id}


@tool()
@safe_tool
def get_portfolio_export_manifest(params: ExportPortfolioIn) -> dict[str, Any]:
    """Manifest of files that would be included in the portfolio ZIP.

    MCP doesn't transport binary blobs, so this returns a structured
    file listing (folder + filename + size + url + kind). Download the
    actual archive at ``GET /api/portfolio/export/`` via REST.
    """
    from apps.creations.models import Creation
    from apps.homework.models import HomeworkProof, HomeworkSubmission

    user = get_current_user()
    target = (
        User.objects.get(pk=params.user_id)
        if (params.user_id and user.role == "parent")
        else user
    )

    files: list[dict[str, Any]] = []

    photos = ProjectPhoto.objects.select_related("project").filter(
        project__assigned_to=target,
    )
    for p in photos:
        if not p.image:
            continue
        folder = p.project.title.replace("/", "_")
        files.append({
            "kind": "project_photo",
            "folder": folder,
            "filename": f"{p.id}_{p.caption or 'photo'}.jpg",
            "url": p.image.url,
            "size_bytes": getattr(p.image, "size", None),
        })

    proofs = HomeworkProof.objects.select_related("submission__assignment").filter(
        submission__user=target,
        submission__status=HomeworkSubmission.Status.APPROVED,
    )
    for pr in proofs:
        if not pr.image:
            continue
        subject = pr.submission.assignment.get_subject_display()
        folder = f"homework/{subject}".replace("/", "_")
        files.append({
            "kind": "homework_proof",
            "folder": folder,
            "filename": f"{pr.id}_{pr.caption or 'proof'}.jpg",
            "url": pr.image.url,
            "size_bytes": getattr(pr.image, "size", None),
        })

    creations = Creation.objects.select_related(
        "primary_skill", "primary_skill__category",
    ).filter(user=target)
    for c in creations:
        if not c.image:
            continue
        cat = c.primary_skill.category.name if c.primary_skill_id else "misc"
        folder = f"creations/{cat}".replace("/", "_")
        label = (c.caption or "creation")[:60]
        files.append({
            "kind": "creation",
            "folder": folder,
            "filename": f"{c.id}_{label}.jpg",
            "url": c.image.url,
            "size_bytes": getattr(c.image, "size", None),
        })

    return {
        "user_id": target.id,
        "files": files,
        "count": len(files),
        "download_url": "/api/portfolio/export/",
    }
