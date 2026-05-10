"""Family-scoped admin endpoints.

Today this only exposes the staff-only "create a new family + founding
parent" path, which lets the deployment owner (``createsuperuser``) mint
sibling families from the UI without going through the public, throttled,
``ALLOW_PARENT_SIGNUP``-gated signup endpoint.
"""
from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.serializers import UserSerializer
from config.permissions import IsStaffParent

from .serializers import FamilySerializer
from .services import FamilyService, FamilyServiceError


class AdminCreateFamilyView(APIView):
    """``POST /api/admin/families/`` — staff parents only.

    Mirrors the public signup body shape (``username, password,
    display_name, family_name``) and reuses ``FamilyService.create_family_with_parent``
    so all validation + atomic-transaction guarantees are shared. Crucially
    this endpoint does NOT honor ``ALLOW_PARENT_SIGNUP`` — staff bypasses
    the public toggle. ``GET`` returns 200 with an empty body so the
    frontend can ping it as a "is this user staff?" probe to gate the
    Admin tab visibility (mirrors the dev-tools tab pattern).
    """

    permission_classes = [permissions.IsAuthenticated, IsStaffParent]

    def get(self, request):
        return Response({"ok": True})

    def post(self, request):
        try:
            parent, family, token = FamilyService.create_family_with_parent(
                username=request.data.get("username", ""),
                password=request.data.get("password", ""),
                display_name=request.data.get("display_name", ""),
                family_name=request.data.get("family_name", ""),
            )
        except FamilyServiceError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_data = UserSerializer(parent).data
        user_data["token"] = token.key
        return Response(
            {
                "token": token.key,
                "user": user_data,
                "family": FamilySerializer(family).data,
            },
            status=status.HTTP_201_CREATED,
        )
