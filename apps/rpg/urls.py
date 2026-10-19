from django.urls import path

from . import experiment_views, progression_views, sprite_admin_views, views, workbench_views

urlpatterns = [
    path("rpg/content-workbench/", workbench_views.ContentWorkbenchView.as_view(), name="content-workbench"),
    path("rpg/content-workbench/drafts/", workbench_views.ContentDraftListView.as_view(), name="content-draft-list"),
    path("rpg/content-workbench/drafts/<uuid:draft_id>/", workbench_views.ContentDraftDetailView.as_view(), name="content-draft-detail"),
    path("rpg/content-workbench/drafts/<uuid:draft_id>/preview/", workbench_views.ContentDraftPreviewView.as_view(), name="content-draft-preview"),
    path("rpg/content-workbench/drafts/<uuid:draft_id>/simulate/", workbench_views.ContentDraftSimulationView.as_view(), name="content-draft-simulate"),
    path("rpg/content-workbench/drafts/<uuid:draft_id>/publish/", workbench_views.ContentDraftPublishView.as_view(), name="content-draft-publish"),
    path("rpg/progression-lab/", progression_views.ProgressionLabView.as_view(), name="progression-lab"),
    path("rpg/progression-lab/experiments/", experiment_views.ExperimentListView.as_view(), name="progression-experiment-list"),
    path("rpg/progression-lab/experiments/<uuid:experiment_id>/", experiment_views.ExperimentDetailView.as_view(), name="progression-experiment-detail"),
    path("rpg/progression-lab/experiments/<uuid:experiment_id>/compare/", experiment_views.ExperimentCompareView.as_view(), name="progression-experiment-compare"),
    path("rpg/progression-lab/experiments/<uuid:experiment_id>/comparisons/<uuid:comparison_id>/", experiment_views.ExperimentComparisonView.as_view(), name="progression-experiment-comparison"),
    path("rpg/progression-lab/experiments/<uuid:experiment_id>/decisions/", experiment_views.ExperimentDecisionView.as_view(), name="progression-experiment-decision"),
    path("rpg/progression-lab/experiments/<uuid:experiment_id>/observations/", experiment_views.ExperimentObservationView.as_view(), name="progression-experiment-observation"),
    path("rpg/progression-lab/observations/", experiment_views.ProgressionObservationsView.as_view(), name="progression-observations"),
    path(
        "rpg/progression-lab/simulate/",
        progression_views.ProgressionSimulationView.as_view(),
        name="progression-lab-simulate",
    ),
    path("character/", views.CharacterView.as_view(), name="character"),
    path("character/avatar/", views.AvatarPreferencesView.as_view(), name="character-avatar"),
    path("character/avatar/catalog/", views.AvatarCatalogView.as_view(), name="avatar-catalog"),
    path("character/avatar/configuration/", views.AvatarConfigurationView.as_view(), name="avatar-configuration"),
    path("streaks/", views.StreakView.as_view(), name="streaks"),
    path("inventory/", views.InventoryView.as_view(), name="inventory"),
    path(
        "inventory/<int:item_id>/use/",
        views.UseConsumableView.as_view(),
        name="use-consumable",
    ),
    path(
        "inventory/<int:item_id>/open/",
        views.OpenCoinPouchView.as_view(),
        name="open-coin-pouch",
    ),
    path("items/catalog/", views.ItemCatalogView.as_view(), name="item-catalog"),
    path("drops/recent/", views.RecentDropsView.as_view(), name="recent-drops"),
    path("cosmetics/", views.CosmeticsView.as_view(), name="cosmetics"),
    path("cosmetics/catalog/", views.CosmeticCatalogView.as_view(), name="cosmetics-catalog"),
    path("character/equip/", views.EquipCosmeticView.as_view(), name="character-equip"),
    path("character/unequip/", views.UnequipCosmeticView.as_view(), name="character-unequip"),
    path("character/trophy/", views.TrophyBadgeView.as_view(), name="character-trophy"),
    path("sprites/catalog/", views.SpriteCatalogView.as_view(), name="sprite-catalog"),
    path(
        "sprites/admin/",
        sprite_admin_views.SpriteAdminListView.as_view(),
        name="sprite-admin-list",
    ),
    # Tombstones prevent old clients receiving a misleading SPA HTML response.
    path(
        "sprites/admin/generate/",
        sprite_admin_views.SpriteGenerationRetiredView.as_view(),
        name="sprite-admin-generate-retired",
    ),
    path(
        "sprites/admin/<slug:slug>/reroll/",
        sprite_admin_views.SpriteGenerationRetiredView.as_view(),
        name="sprite-admin-reroll-retired",
    ),
    path(
        "sprites/admin/<slug:slug>/",
        sprite_admin_views.SpriteAdminDetailView.as_view(),
        name="sprite-admin-detail",
    ),
]
