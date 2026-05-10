"""Family-scoped admin URL conf — mounted at /api/."""
from django.urls import path

from .views import AdminCreateFamilyView

urlpatterns = [
    path("admin/families/", AdminCreateFamilyView.as_view(), name="admin-families"),
]
