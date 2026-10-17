"""Account URL conf — mounted at /api/."""
from django.urls import path

from .views import SignupView
from .lifecycle_views import AccountDeletionView, ContactTransferView, FamilyClosureView, LifecycleView

urlpatterns = [
    path("auth/signup/", SignupView.as_view(), name="auth-signup"),
    path("account/lifecycle/", LifecycleView.as_view(), name="account-lifecycle"),
    path("account/lifecycle/transfer/", ContactTransferView.as_view(), name="account-transfer"),
    path("account/lifecycle/delete/", AccountDeletionView.as_view(), name="account-delete-self"),
    path("account/lifecycle/close-family/", FamilyClosureView.as_view(), name="account-close-family"),
]
