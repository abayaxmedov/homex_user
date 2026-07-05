from django.db.models import Count, Q


def filter_masters_by_specialization(queryset, raw_value):
    """Filter a Master queryset by one or more specializations.

    ``raw_value`` is the raw query-param string and may contain several
    comma-separated specializations (e.g. ``"Santexnik, Elektrik"``). Each term
    is matched case-insensitively against the ``specialization`` field and the
    terms are OR-ed together, so a master matches if any of the requested
    specializations is contained in theirs. Blank/empty input leaves the
    queryset untouched.
    """
    if not raw_value:
        return queryset
    terms = [term.strip() for term in str(raw_value).split(",") if term.strip()]
    if not terms:
        return queryset
    query = Q()
    for term in terms:
        query |= Q(specialization__icontains=term)
    return queryset.filter(query)


def specialization_counts(queryset=None):
    """Return distinct non-empty specializations with the number of masters.

    Useful for building a specialization filter dropdown. Result is a list of
    ``{"specialization": str, "count": int}`` ordered by specialization.
    """
    from apps.accounts.models import Master

    if queryset is None:
        queryset = Master.objects.all()
    rows = (
        queryset.exclude(specialization="")
        .exclude(specialization__isnull=True)
        .values("specialization")
        .annotate(count=Count("id"))
        .order_by("specialization")
    )
    return [{"specialization": row["specialization"], "count": row["count"]} for row in rows]
