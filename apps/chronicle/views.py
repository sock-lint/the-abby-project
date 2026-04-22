from collections import defaultdict
from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.chronicle.models import ChronicleEntry
from apps.chronicle.serializers import ChronicleEntrySerializer, ManualEntryCreateSerializer
from config.permissions import IsParent
from config.viewsets import RoleFilteredQuerySetMixin, get_child_or_404


class ChronicleViewSet(
    RoleFilteredQuerySetMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ChronicleEntrySerializer
    permission_classes = [IsAuthenticated]
    role_filter_field = "user"

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
                    # Post-HS — age during this chapter
                    if target.date_of_birth:
                        age_in_chapter = year - target.date_of_birth.year
                        if target.date_of_birth.month >= 8:
                            age_in_chapter -= 1
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
