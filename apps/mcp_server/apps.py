from django.apps import AppConfig


class MCPServerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mcp_server"
    verbose_name = "MCP Server"

    def ready(self):
        from django.db.models.signals import pre_delete
        from django.conf import settings
        from .retries import clear_deleted_member_responses, clear_deleted_mutation_response

        for label in ("movement.MovementSession", "payments.PaymentLedger",
                      "projects.Project", "rewards.RewardRedemption"):
            pre_delete.connect(
                clear_deleted_mutation_response, sender=label,
                dispatch_uid=f"mcp-mutation-receipt-delete-{label}",
            )
        pre_delete.connect(
            clear_deleted_member_responses, sender=settings.AUTH_USER_MODEL,
            dispatch_uid="mcp-mutation-receipt-delete-member",
        )
