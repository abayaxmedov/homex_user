from uuid import UUID


CATEGORY_ALL_SENTINELS = {"all", "hammasi", "barchasi"}


def _is_uuid(value):
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def category_param(request):
    """Return the raw category filter value from the request, if any.

    Accepts `?category=`, `?category_id=` or `?category_slug=` (in that order).
    The sentinels in :data:`CATEGORY_ALL_SENTINELS` (and empty) mean "no filter".
    """
    value = (
        request.query_params.get("category")
        or request.query_params.get("category_id")
        or request.query_params.get("category_slug")
    )
    if not value or value.lower() in CATEGORY_ALL_SENTINELS:
        return None
    return value


def filter_by_category(queryset, request, field="category"):
    """Filter ``queryset`` by category id (UUID) or slug.

    ``field`` is the lookup path to the category FK relative to the queryset
    model, e.g. ``"category"`` (product/service lists), ``"service__category"``
    (service orders) or ``"product__category"`` (market orders). Pass an empty
    string / ``None`` when the queryset itself is a category model, so the id
    (`pk`) and `slug` are matched directly.

    Reads ``?category=<id|slug>``, ``?category_id=<uuid>`` or
    ``?category_slug=<slug>``; ``all``/``hammasi``/``barchasi`` and empty are
    treated as "no filter". Returns the queryset unchanged when no category is
    requested, so it is safe to chain unconditionally.
    """
    value = category_param(request)
    if value is None:
        return queryset
    id_lookup = f"{field}_id" if field else "id"
    slug_lookup = f"{field}__slug" if field else "slug"
    if _is_uuid(value):
        return queryset.filter(**{id_lookup: value})
    return queryset.filter(**{slug_lookup: value})
