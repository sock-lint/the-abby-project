"""Explicit password-confirmed account and family lifecycle endpoints."""
from rest_framework import serializers, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from . import lifecycle


class LifecyclePasswordThrottle(UserRateThrottle):
    scope = "account_lifecycle"
    rate = "10/min"

    def allow_request(self, request, view):
        return request.method == "GET" or super().allow_request(request, view)


class PasswordConfirmation(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False, write_only=True, max_length=1024)


class ContactTransferConfirmation(PasswordConfirmation):
    successor_id = serializers.IntegerField(min_value=1)


class AccountDeletionConfirmation(PasswordConfirmation):
    confirm_username = serializers.CharField(trim_whitespace=False, max_length=150)
    successor_id = serializers.IntegerField(min_value=1, required=False)


class FamilyClosureConfirmation(PasswordConfirmation):
    confirm_family_slug = serializers.CharField(trim_whitespace=False, max_length=140)
    family_version = serializers.RegexField(r"^[0-9a-f]{64}$")


class LifecycleView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [LifecyclePasswordThrottle]

    def get(self, request):
        with lifecycle.locked_family_members(request) as (family, actor, members):
            return Response(lifecycle.lifecycle_preview(family, actor, members))


class LifecycleMutationView(LifecycleView):
    serializer_class = None
    operation = None
    http_method_names = ["post", "options"]

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        with lifecycle.locked_family_members(request, nowait=True) as (family, actor, members):
            self.operation(family, actor, members, **serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactTransferView(LifecycleMutationView):
    serializer_class = ContactTransferConfirmation
    operation = staticmethod(lifecycle.transfer_contact)


class AccountDeletionView(LifecycleMutationView):
    serializer_class = AccountDeletionConfirmation
    operation = staticmethod(lifecycle.delete_self)


class FamilyClosureView(LifecycleMutationView):
    serializer_class = FamilyClosureConfirmation
    operation = staticmethod(lifecycle.close_family)
