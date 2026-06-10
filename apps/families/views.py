"""Family-scoped endpoints.

Three surfaces: the staff-only "create a new family + founding parent"
path (lets the deployment owner mint sibling families from the UI without
going through the public, throttled, ``ALLOW_PARENT_SIGNUP``-gated signup
endpoint), the parent-only co-parent invite minting endpoint, and the
anonymous invite-redemption surface backing the ``/join/<token>`` page.
"""
from __future__ import annotations

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.projects.serializers import UserSerializer
from config.permissions import IsParent, IsStaffParent

from .models import FamilyInvite
from .serializers import FamilySerializer
from .services import FamilyService, FamilyServiceError, InviteInvalidError


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


class FamilyInviteCreateView(APIView):
    """``POST /api/family/invites/`` — mint a co-parent invite link.

    Parent-only. Returns ``{token, join_path, expires_at}``; the frontend
    composes the absolute URL from its own origin so the link works
    behind any proxy hostname. Each POST mints a fresh single-use token —
    there's no cap on open invites because each is 24h-bounded and
    single-use, and the Manage UI only ever surfaces the latest one.
    """

    permission_classes = [permissions.IsAuthenticated, IsParent]

    def post(self, request):
        invite = FamilyInvite.mint(
            family=request.user.family, created_by=request.user,
        )
        return Response(
            {
                "token": invite.token,
                "join_path": f"/join/{invite.token}",
                "expires_at": invite.expires_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class JoinInviteView(APIView):
    """Anonymous invite-redemption surface at ``/api/auth/join/<token>/``.

    ``GET`` validates the token and returns the family name so the join
    page can render "Join the X family" before asking for credentials.
    ``POST`` (``{username, password, display_name}``) creates the
    co-parent and returns ``{token, user, family}`` — the same shape as
    signup, so the frontend reuses its post-signup login path.

    Invalid/expired/used tokens get one generic 404 message in both
    methods — an unauthenticated caller can't probe which failure mode
    they hit. POST shares the signup throttle scope (5/hour per IP).
    Deliberately NOT gated on ``ALLOW_PARENT_SIGNUP``: invites are
    parent-initiated and unguessable, while the toggle exists to close
    the open self-signup surface.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup"

    @staticmethod
    def _invalid_response():
        return Response(
            {"error": "This invite link is invalid or has expired."},
            status=status.HTTP_404_NOT_FOUND,
        )

    def get(self, request, token):
        invite = FamilyInvite.objects.filter(token=token).first()
        if invite is None or not invite.is_open:
            return self._invalid_response()
        return Response({
            "family_name": invite.family.name,
            "invited_by": invite.created_by.display_label,
            "expires_at": invite.expires_at.isoformat(),
        })

    def post(self, request, token):
        from apps.projects.serializers import UserSerializer

        try:
            parent, family, auth_token = FamilyService.create_parent_from_invite(
                token=token,
                username=request.data.get("username", ""),
                password=request.data.get("password", ""),
                display_name=request.data.get("display_name", ""),
            )
        except InviteInvalidError:
            return self._invalid_response()
        except FamilyServiceError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_data = UserSerializer(parent).data
        user_data["token"] = auth_token.key
        return Response(
            {
                "token": auth_token.key,
                "user": user_data,
                "family": FamilySerializer(family).data,
            },
            status=status.HTTP_201_CREATED,
        )
