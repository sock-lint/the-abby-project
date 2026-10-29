from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import PracticeSerializer, RequestSerializer, SelectSerializer


class DiscoveryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if "user_id" in request.query_params:
            raise ValidationError({"user_id": ["Egg discoveries belong to the signed-in account."]})


class DiscoveriesView(DiscoveryView):
    def get(self, request):
        if not services.enabled():
            return Response(services.envelope(request.user))
        with services.authorized_owner(request.user) as owner:
            return Response(services.envelope(owner))


class SelectView(DiscoveryView):
    def post(self, request):
        body = SelectSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        with services.authorized_owner(request.user) as owner:
            fresh = services.select_discovery(owner, **body.validated_data)
            return Response(services.envelope(owner), status=201 if fresh else 200)


class PauseView(DiscoveryView):
    def post(self, request, pk):
        body = RequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        with services.authorized_owner(request.user) as owner:
            services.pause_discovery(owner, discovery_id=pk, **body.validated_data)
            return Response(services.envelope(owner))


class PracticeView(DiscoveryView):
    def post(self, request):
        body = PracticeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        with services.authorized_owner(request.user) as owner:
            fresh = services.log_practice(owner, **body.validated_data)
            return Response(services.envelope(owner), status=201 if fresh else 200)
