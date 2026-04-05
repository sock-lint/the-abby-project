from django.contrib import admin

from .models import PaymentLedger


@admin.register(PaymentLedger)
class PaymentLedgerAdmin(admin.ModelAdmin):
    list_display = ["user", "entry_type", "amount", "description", "created_at"]
    list_filter = ["entry_type"]
    search_fields = ["user__username", "description"]
