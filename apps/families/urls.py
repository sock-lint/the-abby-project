"""Family-scoped admin URL conf — mounted at /api/."""
from django.urls import path

from .views import AdminCreateFamilyView, FamilyInviteCreateView, JoinInviteView

urlpatterns = [
    path("admin/families/", AdminCreateFamilyView.as_view(), name="admin-families"),
    path("family/invites/", FamilyInviteCreateView.as_view(), name="family-invites"),
    path("auth/join/<str:token>/", JoinInviteView.as_view(), name="auth-join"),
]
