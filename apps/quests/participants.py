"""Privacy-safe labels for saved participants without changing their history."""

FORMER_PARTICIPANT = "Former participant"


def participant_visibility(participants, observer_family_id=None):
    """Reuse prefetched rows and resolve a safe scope for old direct serializers.

    Native and MCP callers provide the observer's household. A caller without
    that context may retain names only when all participants currently share a
    household; mixed households cannot establish which observer may see a name.
    """
    rows = list(participants)
    if observer_family_id is None:
        families = {row.user.family_id for row in rows}
        if len(families) == 1:
            observer_family_id = next(iter(families))
    return rows, observer_family_id


def participant_label(participant, observer_family_id):
    if observer_family_id is not None and participant.user.family_id == observer_family_id:
        return participant.user.display_label
    return FORMER_PARTICIPANT
