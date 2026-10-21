"""Explicit reader feedback and family-authored book invitations."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F, Q
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent
from config.viewsets import RoleFilteredQuerySetMixin

from .models import ReadingDiscoveryFeedback, ReadingFamilySuggestion
from .serializers import (
    DiscoveryFeedbackWriteSerializer, FamilySuggestionCreateSerializer,
    FamilySuggestionWriteSerializer, ReadingFamilySuggestionSerializer,
)
from .services import (
    _existing_request, lock_reading_owner as _lock_target, reading_payload as _payload,
)
from .views import _target_user


class ReadingDiscoveryFeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        target = _target_user(request)
        return Response({"results": list(
            ReadingDiscoveryFeedback.objects.filter(user=target).values("catalog_id", "choice"),
        )})

    def post(self, request):
        target = _target_user(request, source="data")
        write = DiscoveryFeedbackWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        catalog_id, choice = write.validated_data["catalog_id"], write.validated_data["choice"]
        with transaction.atomic():
            target = _lock_target(target, request.user)
            if choice:
                ReadingDiscoveryFeedback.objects.update_or_create(
                    user=target, catalog_id=catalog_id, defaults={"choice": choice},
                )
            else:
                ReadingDiscoveryFeedback.objects.filter(user=target, catalog_id=catalog_id).delete()
        return Response({"catalog_id": catalog_id, "choice": choice})


class ReadingFamilySuggestionViewSet(
    RoleFilteredQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
    mixins.CreateModelMixin, viewsets.GenericViewSet,
):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]
    serializer_class = ReadingFamilySuggestionSerializer

    def get_permissions(self):
        return [IsParent()] if self.action == "create" else super().get_permissions()

    def get_queryset(self):
        queryset = self.get_role_filtered_queryset(
            ReadingFamilySuggestion.objects.select_related("user", "user__family", "suggested_by"),
        ).filter(user__role="child").filter(
            Q(suggested_by__isnull=True)
            | Q(suggested_by__family_id=F("user__family_id"), suggested_by__role="parent"),
        )
        if self.action == "list" or "user_id" in self.request.query_params:
            queryset = queryset.filter(user=_target_user(self.request))
        if self.action == "list":
            queryset = queryset.filter(status=ReadingFamilySuggestion.Status.PENDING)
        return queryset

    def create(self, request, *args, **kwargs):
        target = _target_user(request, source="data")
        write = FamilySuggestionCreateSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        values = dict(write.validated_data)
        values.pop("user_id")
        request_id = values.pop("client_request_id")
        payload = _payload({**values, "suggested_by": request.user.pk})
        with transaction.atomic():
            target = _lock_target(target, request.user)
            parent = get_user_model().objects.filter(
                pk=request.user.pk, family_id=target.family_id, role="parent", is_active=True,
            ).first()
            if parent is None:
                raise NotFound("Parent not found.")
            suggestion = _existing_request(ReadingFamilySuggestion, target, request_id, payload)
            created = suggestion is None
            if created:
                suggestion = ReadingFamilySuggestion.objects.create(
                    user=target, suggested_by=parent, author_name=parent.display_label,
                    client_request_id=request_id, create_payload=payload, **values,
                )
            return Response(
                self.get_serializer(suggestion).data,
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )

    def partial_update(self, request, *args, **kwargs):
        suggestion = self.get_object()
        write = FamilySuggestionWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        with transaction.atomic():
            target = _lock_target(suggestion.user, request.user)
            suggestion = self.get_queryset().filter(pk=suggestion.pk, user=target).first()
            if suggestion is None:
                raise NotFound("Suggestion not found.")
            suggestion.status = write.validated_data["status"]
            suggestion.save(update_fields=["status", "updated_at"])
            return Response(self.get_serializer(suggestion).data)
