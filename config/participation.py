"""Personal workspace selection never changes an account's authority.

Parents remain parents in both spaces. This request hint only narrows
participating endpoints to the authenticated account's own records.
"""


def is_personal_space(request):
    return bool(
        request is not None
        and getattr(getattr(request, "user", None), "role", None) == "parent"
        and getattr(request, "headers", {}).get("X-Abby-Space", "").lower() == "personal"
    )


def personal_queryset(request, queryset, owner_field="user"):
    if is_personal_space(request):
        return queryset.filter(**{owner_field: request.user})
    return queryset
