"""Shared hourly defaults for authorized Family project reassignment."""


def personal_rate_defaults(project):
    """Force zero without relabeling an already explicit Family zero."""
    return {
        "hourly_rate_override": 0,
        "hourly_rate_is_personal_default": (
            project.hourly_rate_is_personal_default or project.hourly_rate_override != 0
        ),
    }


def reassignment_rate_defaults(project, next_owner_id=None, *, rate_supplied, assignment_supplied=True):
    """Distinguish the personal zero default from deliberately authored rates.

    Callers authorize and validate the assignment first. Explicit rate choices,
    including zero or null, clear personal provenance. Metadata-only or
    same-owner edits with no rate preserve the saved choice and provenance.
    Clearing on unassignment prevents a later child assignment inheriting zero.
    """
    if rate_supplied:
        return {"hourly_rate_is_personal_default": False}
    if (assignment_supplied and project.hourly_rate_is_personal_default
            and project.assigned_to_id is not None
            and next_owner_id != project.assigned_to_id
            and project.assigned_to.role == "parent"
            and project.hourly_rate_override == 0):
        return {"hourly_rate_override": None, "hourly_rate_is_personal_default": False}
    return {}
