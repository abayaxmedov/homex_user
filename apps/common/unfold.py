def environment_callback(request):
    from django.conf import settings

    return ["Local", "info"] if settings.DEBUG else ["Production", "danger"]


def environment_title_prefix_callback(request):
    label, _ = environment_callback(request)
    return f"{label} | "


def new_orders_badge(request):
    from apps.orders.models import Order, OrderStatus

    return Order.objects.filter(status=OrderStatus.NEW).count()


def unread_notifications_badge(request):
    from apps.notifications.models import Notification

    return Notification.objects.filter(is_read=False).count()


def low_stock_badge(request):
    from django.db.models import F

    from apps.warehouse.models import MasterInventory, WarehouseProduct

    warehouse_low = WarehouseProduct.objects.filter(is_active=True, quantity__lte=F("low_threshold")).count()
    master_low = MasterInventory.objects.filter(quantity__lte=F("low_threshold")).count()
    return warehouse_low + master_low


def pending_withdraw_badge(request):
    from apps.wallet.models import WithdrawRequest

    return WithdrawRequest.objects.filter(status=WithdrawRequest.PENDING).count()


def pending_masters_badge(request):
    from apps.accounts.models import Master, MasterApprovalStatus

    return Master.objects.filter(approval_status=MasterApprovalStatus.PENDING).count()


def blocked_masters_badge(request):
    from apps.accounts.models import Master

    return Master.objects.filter(is_blocked=True).count()


def pending_cash_handover_badge(request):
    from apps.wallet.models import WithdrawRequest

    return WithdrawRequest.objects.filter(status=WithdrawRequest.PENDING).count()
