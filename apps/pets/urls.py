from django.urls import path
from . import views

urlpatterns = [
    path("pets/stable/", views.StableView.as_view(), name="pet-stable"),
    path("pets/codex/", views.PetCodexView.as_view(), name="pet-codex"),
    path("pets/species/catalog/", views.PetSpeciesCatalogView.as_view(), name="pet-species-catalog"),
    path("pets/hatch/", views.HatchPetView.as_view(), name="pet-hatch"),
    path(
        "pets/companion-growth/recent/",
        views.CompanionGrowthRecentView.as_view(),
        name="pet-companion-growth-recent",
    ),
    path(
        "pets/companion-growth/seen/",
        views.CompanionGrowthSeenView.as_view(),
        name="pet-companion-growth-seen",
    ),
    path("pets/<int:pk>/feed/", views.FeedPetView.as_view(), name="pet-feed"),
    path("pets/<int:pk>/activate/", views.ActivatePetView.as_view(), name="pet-activate"),
    path("mounts/", views.MountsView.as_view(), name="mounts"),
    path("mounts/<int:pk>/activate/", views.ActivateMountView.as_view(), name="mount-activate"),
    path("mounts/breed/", views.BreedMountsView.as_view(), name="mount-breed"),
    path(
        "mounts/<int:pk>/expedition/",
        views.StartExpeditionView.as_view(),
        name="mount-expedition-start",
    ),
    path("expeditions/", views.ListExpeditionsView.as_view(), name="expeditions-list"),
    path(
        "expeditions/<int:pk>/claim/",
        views.ClaimExpeditionView.as_view(),
        name="expedition-claim",
    ),
]
