"""Drop ``SavingsGoal.current_amount``.

The field is now derived on read from ``PaymentService.get_balance(user)``
— storing it created drift risk between the stored value and the live
balance, and the two contribution paths (REST ``update_amount`` overwrote
from balance; MCP ``contribute_to_goal`` incremented) disagreed about what
the column meant.

See ``apps/projects/savings_service.py`` for the completion-detection
logic that now reads balance directly, and ``SavingsGoalSerializer`` for
the computed ``current_amount`` exposed to the API.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0016_move_user_out"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="savingsgoal",
            name="current_amount",
        ),
    ]
