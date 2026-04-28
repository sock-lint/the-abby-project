"""Account-level endpoints — currently parent self-signup."""
from __future__ import annotations

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.families.serializers import FamilySerializer
from apps.families.services import FamilyService, FamilyServiceError
from apps.projects.serializers import UserSerializer


class SignupView(APIView):
    """Create a new Family + founding parent + auth token.

    POST /api/auth/signup/  body: ``{username, password, display_name, family_name}``
    Returns ``{token, user, family}``. Returns 403 if signup is disabled.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup"

    def post(self, request):
        if not getattr(settings, "ALLOW_PARENT_SIGNUP", True):
            return Response(
                {"error": "Signup is currently disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )
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
