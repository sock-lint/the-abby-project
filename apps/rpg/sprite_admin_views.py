"""Parent-only REST surface for the sprite admin UI on /manage.

Thin wrappers around the existing services in ``apps.rpg.sprite_authoring``
and ``apps.rpg.sprite_generation`` — no business logic here. Keeps
``apps/rpg/views.py`` from growing further (it already mixes public
catalog + habit + character views).
"""
from __future__ import annotations

from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent, IsStaffParent

from . import sprite_authoring as svc
from .models import SpriteAsset
from .sprite_authoring import SpriteAuthoringError
from .sprite_generation import SpriteGenerationError, generate_sprite_sheet


class SpriteAdminSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SpriteAsset
        fields = [
            "slug",
            "url",
            "pack",
            "frame_count",
            "fps",
            "frame_width_px",
            "frame_height_px",
            "frame_layout",
            "prompt",
            "motion",
            "style_hint",
            "tile_size",
            "reference_image_url",
            "created_by_name",
            "created_at",
            "updated_at",
        ]

    def get_url(self, obj: SpriteAsset) -> str:
        if not obj.image:
            return ""
        return obj.image.url

    def get_created_by_name(self, obj: SpriteAsset) -> str:
        user = obj.created_by
        if user is None:
            return ""
        return user.get_full_name() or user.username


class SpriteAdminListView(APIView):
    """GET /api/sprites/admin/ — full sprite catalog with authoring inputs."""

    permission_classes = [permissions.IsAuthenticated, IsParent]

    def get(self, request):
        qs = SpriteAsset.objects.select_related("created_by").order_by("pack", "slug")
        pack = request.query_params.get("pack")
        if pack:
            qs = qs.filter(pack=pack)
        return Response(SpriteAdminSerializer(qs, many=True).data)


class SpriteGenerateView(APIView):
    """POST /api/sprites/admin/generate/ — create or replace via Gemini.

    Sprites are GLOBAL content shared across every family — gate on
    IsStaffParent so a signup-created parent can't burn a deployment's
    Gemini budget seeding the public catalog with junk.
    """

    permission_classes = [permissions.IsAuthenticated, IsStaffParent]

    def post(self, request):
        data = request.data
        try:
            kwargs = _extract_generate_kwargs(data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = generate_sprite_sheet(actor=request.user, **kwargs)
        except (SpriteGenerationError, SpriteAuthoringError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class SpriteRerollView(APIView):
    """POST /api/sprites/admin/<slug>/reroll/ — replay stored inputs."""

    permission_classes = [permissions.IsAuthenticated, IsStaffParent]

    def post(self, request, slug):
        try:
            asset = SpriteAsset.objects.get(slug=slug)
        except SpriteAsset.DoesNotExist:
            return Response({"detail": f"sprite {slug!r} not found"}, status=status.HTTP_404_NOT_FOUND)

        if not asset.prompt:
            return Response(
                {"detail": "no stored prompt — use Replace instead"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tile_size = asset.tile_size or asset.frame_width_px or 64
        motion = asset.motion or "idle"
        return_debug_raw = bool(request.data.get("return_debug_raw"))

        try:
            result = generate_sprite_sheet(
                slug=asset.slug,
                prompt=asset.prompt,
                frame_count=asset.frame_count,
                tile_size=tile_size,
                fps=asset.fps,
                pack=asset.pack,
                style_hint=asset.style_hint,
                motion=motion,
                reference_image_url=asset.reference_image_url or None,
                return_debug_raw=return_debug_raw,
                overwrite=True,
                actor=request.user,
            )
        except (SpriteGenerationError, SpriteAuthoringError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class SpriteAdminDetailView(APIView):
    """PATCH / DELETE /api/sprites/admin/<slug>/ — metadata edit + delete."""

    permission_classes = [permissions.IsAuthenticated, IsStaffParent]

    def patch(self, request, slug):
        fps = request.data.get("fps")
        pack = request.data.get("pack")
        kwargs = {}
        if fps is not None:
            try:
                kwargs["fps"] = int(fps)
            except (TypeError, ValueError):
                return Response({"detail": "fps must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
        if pack is not None:
            kwargs["pack"] = str(pack)
        if not kwargs:
            return Response(
                {"detail": "at least one of fps / pack is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = svc.update_sprite_metadata(slug=slug, **kwargs)
        except SpriteAuthoringError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)

    def delete(self, request, slug):
        try:
            result = svc.delete_sprite(slug=slug)
        except SpriteAuthoringError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


def _extract_generate_kwargs(data) -> dict:
    """Pull a clean kwargs dict from request.data, raising ValueError on bad input."""
    slug = (data.get("slug") or "").strip()
    prompt = (data.get("prompt") or "").strip()
    if not slug:
        raise ValueError("slug is required")
    if not prompt:
        raise ValueError("prompt is required")

    def _as_int(name, default):
        raw = data.get(name)
        if raw in (None, ""):
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be an integer")

    return {
        "slug": slug,
        "prompt": prompt,
        "frame_count": _as_int("frame_count", 1),
        "tile_size": _as_int("tile_size", 64),
        "fps": _as_int("fps", 0),
        "pack": (data.get("pack") or "ai-generated").strip() or "ai-generated",
        "style_hint": (data.get("style_hint") or "").strip(),
        "motion": (data.get("motion") or "idle").strip() or "idle",
        "reference_image_url": (data.get("reference_image_url") or "").strip() or None,
        "return_debug_raw": bool(data.get("return_debug_raw")),
        "overwrite": bool(data.get("overwrite")),
    }
