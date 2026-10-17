import json

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, Q, RestrictedError, Sum
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.quests.activity import household_timezone
from config.viewsets import RoleFilteredQuerySetMixin, resolve_target_user

from .constants import INTERESTS
from .models import ReadingBook, ReadingSession
from .serializers import (
    ReadingBookCreateSerializer,
    ReadingBookSerializer,
    ReadingBookWriteSerializer,
    ReadingSessionCreateSerializer,
    ReadingSessionSerializer,
    ReadingSessionWriteSerializer,
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


def _lock_target(target, requester):
    # Every write takes the same owner lock, including deletes and corrections.
    # Recheck the family/role after waiting: account management may have changed
    # the target since request validation. no_key permits unrelated FK inserts.
    target = (
        get_user_model().objects.select_for_update(no_key=True, of=("self",))
        .select_related("family")
        .filter(pk=target.pk, role="child", family_id=requester.family_id)
        .first()
    )
    if target is None:
        raise NotFound("Child not found.")
    return target


def _payload(data):
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def _existing_request(model, target, request_id, payload):
    existing = model.objects.filter(user=target, client_request_id=request_id).first()
    if existing is not None and existing.create_payload != payload:
        raise serializers.ValidationError({"client_request_id": "This request was already saved with different details."})
    return existing


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
        values = dict(write.validated_data)
        values.pop("user_id", None)
        request_id = values.pop("client_request_id")
        payload = _payload(values)
        with transaction.atomic():
            target = _lock_target(target, request.user)
            book = _existing_request(ReadingBook, target, request_id, payload)
            created = book is None
            if created:
                book = ReadingBook.objects.create(
                    user=target, client_request_id=request_id, create_payload=payload, **values,
                )
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
    queryset = ReadingSession.objects.select_related("user", "user__family", "book")
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
        values = dict(write.validated_data)
        values.pop("user_id", None)
        request_id = values.pop("client_request_id")
        # Leave an omitted date out of the normalized request. A retry tomorrow
        # still refers to today's original entry rather than creating another.
        payload = _payload(values)
        book_id = values.pop("book")
        with transaction.atomic():
            target = _lock_target(target, request.user)
            session = _existing_request(ReadingSession, target, request_id, payload)
            created = session is None
            if created:
                book = ReadingBook.objects.filter(pk=book_id, user=target).first()
                if book is None:
                    raise serializers.ValidationError({"book": "Choose a book from this reader's shelf."})
                values.setdefault("occurred_on", timezone.localdate(timezone=household_timezone(target)))
                session = ReadingSession.objects.create(
                    user=target, book=book, client_request_id=request_id, create_payload=payload, **values,
                )
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
        books = ReadingBook.objects.filter(user=target).aggregate(
            books_total=Count("id"), books_finished=Count("id", filter=Q(status=ReadingBook.Status.FINISHED)),
        )
        sessions = ReadingSession.objects.filter(user=target).aggregate(
            sessions_total=Count("id"), total_minutes=Sum("duration_minutes", default=0), total_pages=Sum("pages_read", default=0),
        )
        tz = household_timezone(target)
        return Response({**books, **sessions, "today": timezone.localdate(timezone=tz).isoformat(), "timezone": str(tz)})


class ReadingRecommendationsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .recommendations import recommend_books

        target = _target_user(request)
        interest = request.query_params.get("interest")
        if interest is not None and interest not in INTERESTS:
            raise serializers.ValidationError({"interest": "Choose a supported reading interest."})
        return Response(recommend_books(target, interest=interest))
