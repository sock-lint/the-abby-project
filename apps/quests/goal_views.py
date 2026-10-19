from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsParent, IsStaffParent
from config.viewsets import child_not_found_response, get_child_or_404
from .goal_serializers import GoalWriteSerializer
from .goals import create_goal, list_goals, occurrence_payload, set_pin


class ChallengesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if "user_id" in request.query_params:
            if request.user.role != "parent":
                return child_not_found_response()
            raw_id = request.query_params["user_id"]
            try:
                user_id = int(raw_id)
            except (ValueError, TypeError):
                return child_not_found_response()
            user = get_child_or_404(user_id, requesting_user=request.user)
            if not user:
                return child_not_found_response()
        payload = list_goals(user)
        from .daily_bonus import get_daily_bonus_payload
        payload["daily_bonus"] = get_daily_bonus_payload(user)
        return Response(payload)


class CreateGoalView(APIView):
    permission_classes = [IsParent]

    def post(self, request):
        serializer = GoalWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        child = get_child_or_404(serializer.validated_data["user_id"], requesting_user=request.user)
        if not child:
            return child_not_found_response()
        try:
            occurrence = create_goal(request.user, child, serializer.validated_data)
        except ValueError as error:
            return Response({"error": str(error)}, status=status.HTTP_409_CONFLICT)
        return Response(occurrence_payload(occurrence), status=status.HTTP_201_CREATED)


class ChallengePinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, goal_id):
        try:
            return Response(set_pin(request.user, goal_id))
        except ValueError:
            return Response({"error": "Challenge not found"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, goal_id):
        try:
            return Response(set_pin(request.user, goal_id, clear=True))
        except ValueError:
            return Response({"error": "Challenge not found"}, status=status.HTTP_404_NOT_FOUND)


class ChallengeOpenedView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, goal_id):
        from .discovery import record_details_opened
        if request.query_params or not isinstance(request.data, dict) or request.data:
            return Response({"error": "Supply an empty object without query parameters."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(record_details_opened(request.user, goal_id))


class ChallengeDiscoveryView(APIView):
    permission_classes = [IsStaffParent]

    def get(self, request):
        from .discovery import discovery_observations
        if set(request.query_params) - {"_abby_session", "_abby_retry"}:
            return Response({"error": "Discovery observations accept no targeting parameters."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(discovery_observations(request.user))
