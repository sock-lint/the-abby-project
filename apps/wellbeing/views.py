from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import WellbeingError, WellbeingService


class WellbeingTodayView(APIView):
    """GET /api/wellbeing/today/ — today's affirmation + saved gratitude lines.

    Self-scoped: always reads request.user, never accepts a user_id query
    param. Idempotent — first call creates today's row.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        entry = WellbeingService.get_or_create_today(request.user)
        return Response(WellbeingService.serialize_today(entry))


class WellbeingGratitudeView(APIView):
    """POST /api/wellbeing/today/gratitude/ — save 1-3 gratitude lines for today.

    Body: ``{"lines": ["...", "..."]}``. First-of-day submit pays a small
    coin trickle; subsequent same-day edits are free.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        lines = request.data.get("lines")
        try:
            result = WellbeingService.submit_gratitude(request.user, lines)
        except WellbeingError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            **WellbeingService.serialize_today(result["entry"]),
            "coin_awarded": result["coin_awarded"],
            "freshly_paid": result["freshly_paid"],
        })
