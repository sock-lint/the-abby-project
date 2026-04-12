from django.contrib import admin

from .models import CoinLedger, ExchangeRequest, Reward, RewardRedemption


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = ["name", "icon", "cost_coins", "rarity", "stock", "is_active"]
    list_filter = ["rarity", "is_active", "requires_parent_approval"]
    search_fields = ["name"]


@admin.register(RewardRedemption)
class RewardRedemptionAdmin(admin.ModelAdmin):
    list_display = ["user", "reward", "status", "coin_cost_snapshot", "requested_at"]
    list_filter = ["status"]
    search_fields = ["user__username", "reward__name"]


@admin.register(CoinLedger)
class CoinLedgerAdmin(admin.ModelAdmin):
    list_display = ["user", "amount", "reason", "description", "created_at"]
    list_filter = ["reason"]
    search_fields = ["user__username", "description"]


@admin.register(ExchangeRequest)
class ExchangeRequestAdmin(admin.ModelAdmin):
    list_display = ["user", "dollar_amount", "coin_amount", "status", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["created_at"]
