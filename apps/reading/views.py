from django.db import transaction
from django.db.models import RestrictedError
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from config.viewsets import RoleFilteredQuerySetMixin, resolve_target_user

from .models import ReadingBook, ReadingSession
from .services import (
    create_reading_book, create_reading_session,
    lock_reading_owner as _lock_target, reading_summary,
)
from .serializers import (
    ReadingBookCreateSerializer,
    ReadingBookSerializer,
    ReadingBookWriteSerializer,
    ReadingSessionCreateSerializer,
    ReadingSessionSerializer,
    ReadingSessionWriteSerializer,
    DiscoveryFilterSerializer,
)


def _positive_id(raw, field):
    # DRF IntegerField accepts "1.0"; the shared target lookup expects a real
    # integer ID. Validate before that lookup so malformed probes return 400.
    if (
        isinstance(raw, bool) or not isinstance(raw, (str, int))
        or not str(raw).isascii() or not str(raw).isdigit() or len(str(raw)) > 19
    ):
        raise serializers.ValidationError({field: "A positive integer is required."})
    value = int(raw)
    if value < 1 or value > 9223372036854775807:
        raise serializers.ValidationError({field: "A positive integer is required."})
    return value


def _target_user(request, source="query_params", *, required_for_parent=True):
    bucket = request.query_params if source == "query_params" else request.data
    if "user_id" in bucket:
        _positive_id(bucket.get("user_id"), "user_id")
    if request.user.role == "parent" and required_for_parent and "user_id" not in bucket:
        raise serializers.ValidationError({"user_id": "Choose a child in your family."})
    target, error = resolve_target_user(request, source=source)
    if error is not None:
        raise NotFound("Child not found.")
    if request.user.role == "child" and "user_id" in bucket and int(bucket["user_id"]) != request.user.id:
        raise serializers.ValidationError({"user_id": "You can only access your own reading."})
    return target


class ReadingOwnerViewSet(RoleFilteredQuerySetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = self.get_role_filtered_queryset(super().get_queryset()).filter(user__role="child")
        if "user_id" in self.request.query_params:
            target = _target_user(self.request)
            queryset = queryset.filter(user=target)
        return queryset

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        with transaction.atomic():
            target = _lock_target(instance.user, request.user)
            # Read again after the lock, avoiding lost fields from stale PATCHes.
            instance = self.get_queryset().filter(pk=instance.pk, user=target).first()
            if instance is None:
                raise NotFound("Reading record not found.")
            write = self.write_serializer_class(
                instance, data=request.data, partial=True, context={"target_user": target},
            )
            write.is_valid(raise_exception=True)
            for field, value in write.validated_data.items():
                setattr(instance, field, value)
            instance.save()
            return Response(self.get_serializer(instance).data)


class ReadingBookViewSet(ReadingOwnerViewSet):
    queryset = ReadingBook.objects.select_related("user", "user__family")
    serializer_class = ReadingBookSerializer
    write_serializer_class = ReadingBookWriteSerializer

    def create(self, request, *args, **kwargs):
        write = ReadingBookCreateSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        target = _target_user(request, source="data")
        book, created = create_reading_book(request.user, target, write.validated_data)
        return Response(self.get_serializer(book).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        with transaction.atomic():
            target = _lock_target(instance.user, request.user)
            instance = self.get_queryset().filter(pk=instance.pk, user=target).first()
            if instance is None:
                raise NotFound("Book not found.")
            try:
                instance.delete()
            except RestrictedError:
                return Response(
                    {"detail": "This book has reading entries. Keep it on your shelf to preserve your reading history."},
                    status=status.HTTP_409_CONFLICT,
                )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReadingSessionViewSet(ReadingOwnerViewSet):
    queryset = ReadingSession.objects.select_related("user", "user__family", "book", "reading_daily_reward")
    serializer_class = ReadingSessionSerializer
    write_serializer_class = ReadingSessionWriteSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if "book" in self.request.query_params:
            queryset = queryset.filter(book_id=_positive_id(self.request.query_params["book"], "book"))
        return queryset

    def create(self, request, *args, **kwargs):
        target = _target_user(request, source="data")
        write = ReadingSessionCreateSerializer(data=request.data, context={"target_user": target})
        write.is_valid(raise_exception=True)
        session, created = create_reading_session(request.user, target, write.validated_data)
        return Response(self.get_serializer(session).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        with transaction.atomic():
            target = _lock_target(instance.user, request.user)
            self.get_queryset().filter(pk=instance.pk, user=target).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReadingSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        target = _target_user(request)
        return Response(reading_summary(target))


class ReadingRecommendationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .recommendations import recommend_books

        target = _target_user(request)
        filters = DiscoveryFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        values = dict(filters.validated_data)
        # Keep the original simple call shape for existing topic consumers.
        interest = values.pop("interest", None)
        if "book_format" in values:
            values["format"] = values.pop("book_format")
        if not values.get("q"):
            values.pop("q", None)
        if not values.get("rotation"):
            values.pop("rotation", None)
        return Response(recommend_books(target, interest=interest, **values))
