from collections import defaultdict
from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.serializers import (
    ChronicleEntrySerializer,
    ManualEntryCreateSerializer,
    ManualEntryUpdateSerializer,
)
from config.permissions import IsParent
from config.viewsets import RoleFilteredQuerySetMixin, child_not_found_response, get_child_or_404


class ChronicleViewSet(
    RoleFilteredQuerySetMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ChronicleEntrySerializer
    permission_classes = [IsAuthenticated]
    role_filter_field = "user"

    def get_permissions(self):
        if self.action in ("update", "partial_update", "destroy", "manual"):
            return [IsAuthenticated(), IsParent()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return ManualEntryUpdateSerializer
        return ChronicleEntrySerializer

    def get_queryset(self):
        qs = self.get_role_filtered_queryset(ChronicleEntry.objects.all())
        # Parents can further scope with ?user_id=
        if self.request.user.role == "parent":
            user_id = self.request.query_params.get("user_id")
            if user_id:
                qs = qs.filter(user_id=user_id)
        chapter_year = self.request.query_params.get("chapter_year")
        if chapter_year:
            qs = qs.filter(chapter_year=chapter_year)
        return qs

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        """Group entries by chapter_year into chapter cards."""
        target = request.user
        if request.user.role == "parent" and (uid := request.query_params.get("user_id")):
            from django.contrib.auth import get_user_model
            target = get_object_or_404(get_user_model(), pk=uid, role="child")

        entries = list(
            ChronicleEntry.objects.filter(user=target).order_by("-chapter_year", "-occurred_on")
        )

        by_year: dict[int, list] = defaultdict(list)
        for e in entries:
            by_year[e.chapter_year].append(e)

        today = date.today()
        current_chapter = today.year if today.month >= 8 else today.year - 1

        chapters = []
        for year in sorted(by_year.keys(), reverse=True):
            is_current = (year == current_chapter)
            grade = None
            label = None
            if target.grade_entry_year is not None:
                grade = 9 + (year - target.grade_entry_year)
                if 9 <= grade <= 12:
                    label = {
                        9: "Freshman Year",
                        10: "Sophomore Year",
                        11: "Junior Year",
                        12: "Senior Year",
                    }[grade]
                elif grade < 9:
                    label = f"Grade {grade}"
                else:
                    # Post-HS — max age reached during this chapter (Aug year – Jul year+1).
                    # Aug–Dec birthdays land in calendar year `year`; Jan–Jul land in `year + 1`.
                    if target.date_of_birth:
                        age_in_chapter = year - target.date_of_birth.year
                        if target.date_of_birth.month < 8:
                            age_in_chapter += 1
                        label = f"Age {age_in_chapter} · {year}-{str(year + 1)[-2:]}"
            chapters.append({
                "chapter_year": year,
                "grade": grade,
                "label": label,
                "is_current": is_current,
                "is_post_hs": grade is not None and grade > 12,
                "stats": _stats_for(target, year, by_year[year], is_current),
                "entries": ChronicleEntrySerializer(by_year[year], many=True).data,
            })

        return Response({"chapters": chapters, "current_chapter_year": current_chapter})

    @action(detail=False, methods=["get"], url_path="pending-celebration")
    def pending_celebration(self, request):
        """Return the single unviewed BIRTHDAY entry for today, or 204."""
        today = date.today()
        entry = (
            ChronicleEntry.objects.filter(
                user=request.user,
                kind=ChronicleEntry.Kind.BIRTHDAY,
                occurred_on=today,
                viewed_at__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )
        if entry is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(ChronicleEntrySerializer(entry).data)

    @action(detail=True, methods=["post"], url_path="mark-viewed")
    def mark_viewed(self, request, pk=None):
        """Set viewed_at=now() if null — idempotent."""
        from django.utils import timezone
        entry = get_object_or_404(ChronicleEntry, pk=pk)
        # Role-filter ownership: child sees own, parent sees their kids.
        if request.user.role == "child" and entry.user_id != request.user.id:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if entry.viewed_at is None:
            entry.viewed_at = timezone.now()
            entry.save(update_fields=["viewed_at"])
        return Response(ChronicleEntrySerializer(entry).data)

    @action(detail=False, methods=["post"], url_path="manual")
    def manual(self, request):
        """Create a manual chronicle entry for a child. Parent-only."""
        serializer = ManualEntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user_id = data.pop("user_id")
        target = get_child_or_404(user_id)
        if target is None:
            return child_not_found_response()
        occurred_on: date = data["occurred_on"]
        chapter_year = occurred_on.year if occurred_on.month >= 8 else occurred_on.year - 1
        entry = ChronicleEntry.objects.create(
            user=target,
            kind=ChronicleEntry.Kind.MANUAL,
            chapter_year=chapter_year,
            **data,
        )
        return Response(ChronicleEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        if serializer.instance.kind != ChronicleEntry.Kind.MANUAL:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only manual entries are editable.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.kind != ChronicleEntry.Kind.MANUAL:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only manual entries are deletable.")
        instance.delete()


def _stats_for(user, chapter_year, entries, is_current):
    """For past chapters, read frozen RECAP metadata; for current, compute live."""
    for e in entries:
        if e.kind == ChronicleEntry.Kind.RECAP:
            return e.metadata
    if not is_current:
        return {}
    # Live stats for the in-progress current chapter.
    from django.db.models import Sum

    from apps.projects.models import Project
    from apps.rewards.models import CoinLedger

    start = date(chapter_year, 8, 1)
    end = date(chapter_year + 1, 7, 31)
    return {
        "projects_completed": Project.objects.filter(
            assigned_to=user,
            status="completed",
            completed_at__date__range=(start, end),
        ).count(),
        "coins_earned": int(
            CoinLedger.objects.filter(
                user=user,
                created_at__date__range=(start, end),
                amount__gt=0,
            ).aggregate(t=Sum("amount"))["t"] or 0
        ),
    }
