"""Parent-only REST surface for the sprite admin UI on /manage.

Thin wrappers around the existing services in ``apps.rpg.sprite_authoring``
— no business logic here. Keeps
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
            "original_intent",
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


class SpriteGenerationRetiredView(APIView):
    """Keep retired authoring POSTs out of the site's HTML fallback."""

    permission_classes = [permissions.IsAuthenticated, IsStaffParent]

    def post(self, request, slug=None):
        return Response(
            {"detail": "AI sprite generation has been retired. Register prepared artwork instead."},
            status=status.HTTP_410_GONE,
        )
