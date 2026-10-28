"""Shared hourly defaults for authorized Family project reassignment."""


def reassignment_rate_defaults(project, next_owner_id, *, rate_supplied):
    """Drop a parent's inherited zero when an assignment omits a rate.

    Callers authorize and validate the assignment first. Explicit rate choices,
    including zero, and metadata-only or same-owner edits remain authoritative.
    Clearing on unassignment prevents a later child assignment inheriting zero.
    """
    if (not rate_supplied and project.assigned_to_id is not None
            and next_owner_id != project.assigned_to_id
            and project.assigned_to.role == "parent"
            and project.hourly_rate_override == 0):
        return {"hourly_rate_override": None}
    return {}
