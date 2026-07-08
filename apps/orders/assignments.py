"""Shared master/assistant assignment logic for an order.

Used by the dashboard "Usta/Shogird biriktirish" flow and the Unfold admin
per-row assign page. Each call REPLACES the active related set (the selection is
the full desired set), mirroring the Figma "Saqlash" modals.
"""


def sync_related_set(order, related_name, fk_field, wanted_ids, admin=None):
    """Replace ``order.<related_name>`` active rows so they match ``wanted_ids``.

    ``related_name`` is the reverse manager (``assigned_masters`` for
    :class:`OrderMaster`, ``dashboard_assistants`` for
    :class:`DashboardOrderAssistant`); ``fk_field`` is the master FK on that row
    (``master`` / ``assistant``). Removed rows are deactivated (not deleted) so
    history survives. Returns the list of newly assigned Master objects.
    """
    from apps.accounts.models import Master

    manager = getattr(order, related_name)
    wanted = {str(i) for i in wanted_ids}
    existing = {str(getattr(row, f"{fk_field}_id")): row for row in manager.all()}

    for master_id, row in existing.items():
        if master_id not in wanted and row.is_active:
            row.is_active = False
            row.save(update_fields=["is_active", "updated_at"])

    newly_assigned = []
    for master in Master.objects.filter(id__in=wanted):
        row = existing.get(str(master.id))
        if row is None:
            manager.create(**{fk_field: master, "assigned_by": admin})
            newly_assigned.append(master)
        elif not row.is_active:
            row.is_active = True
            row.assigned_by = admin
            row.save(update_fields=["is_active", "assigned_by", "updated_at"])
            newly_assigned.append(master)
    return newly_assigned
