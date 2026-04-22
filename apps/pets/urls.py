from django.urls import path
from . import views

urlpatterns = [
    path("pets/stable/", views.StableView.as_view(), name="pet-stable"),
    path("pets/species/catalog/", views.PetSpeciesCatalogView.as_view(), name="pet-species-catalog"),
    path("pets/hatch/", views.HatchPetView.as_view(), name="pet-hatch"),
    path("pets/<int:pk>/feed/", views.FeedPetView.as_view(), name="pet-feed"),
    path("pets/<int:pk>/activate/", views.ActivatePetView.as_view(), name="pet-activate"),
    path("mounts/", views.MountsView.as_view(), name="mounts"),
    path("mounts/<int:pk>/activate/", views.ActivateMountView.as_view(), name="mount-activate"),
    path("mounts/breed/", views.BreedMountsView.as_view(), name="mount-breed"),
]
