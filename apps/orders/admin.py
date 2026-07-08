from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from unfold.decorators import action

from apps.accounts.models import Master
from apps.common.admin_mixins import HomeXModelAdmin, HomeXTabularInline
from apps.dashboard.models import DashboardOrderAssistant
from apps.notifications.services import create_notification
from apps.orders.assignments import sync_related_set
from apps.orders.models import (
    HomeBanner,
    Order,
    OrderInventoryUsage,
    OrderMaster,
    OrderTracking,
    Review,
    ReviewPhoto,
)


@admin.register(HomeBanner)
class HomeBannerAdmin(HomeXModelAdmin):
    list_display = ("id", "banner_image", "banner_url", "is_active")
    list_editable = ("is_active",)
    search_fields = ("banner_url",)
    list_filter = ("is_active",)
    fields = ("banner_image", "banner_url", "is_active")


class OrderInventoryUsageInline(HomeXTabularInline):
    model = OrderInventoryUsage


class OrderMasterInline(HomeXTabularInline):
    """Usta biriktirish (dashboard 'Usta biriktirish' modalining admin ekvivalenti)."""

    model = OrderMaster
    fields = ("master", "has_accepted", "assigned_by", "is_active")
    autocomplete_fields = ("master",)
    extra = 1
    verbose_name = "Usta biriktirish"
    verbose_name_plural = "Ustalar (biriktirilgan)"


class OrderAssistantInline(HomeXTabularInline):
    """Shogird biriktirish (dashboard 'Shogird biriktirish' modali)."""

    model = DashboardOrderAssistant
    fields = ("assistant", "assigned_by", "note", "is_active")
    autocomplete_fields = ("assistant",)
    extra = 1
    verbose_name = "Shogird biriktirish"
    verbose_name_plural = "Shogirdlar (biriktirilgan)"


@admin.register(Order)
class OrderAdmin(HomeXModelAdmin):
    list_display = (
        "id",
        "client",
        "master",
        "masters_count",
        "assistants_count",
        "service",
        "status",
        "payment_type",
        "total_amount",
        "scheduled_date",
    )
    search_fields = ("client__phone", "master__phone", "address_text", "note")
    list_filter = ("status", "payment_type", "scheduled_date")
    inlines = [OrderMasterInline, OrderAssistantInline, OrderInventoryUsageInline]
    # Per-row button in the order list (like the dashboard "Usta/Shogird biriktirish").
    actions_row = ("assign_row",)

    @admin.display(description="Ustalar")
    def masters_count(self, obj):
        return obj.assigned_masters.filter(is_active=True).count()

    @admin.display(description="Shogirdlar")
    def assistants_count(self, obj):
        return obj.dashboard_assistants.filter(is_active=True).count()

    @action(description="Biriktirish", url_path="assign")
    def assign_row(self, request, object_id):
        """Dashboard-style assign page: pick masters + assistants (checkboxes)."""
        order = get_object_or_404(Order.objects.select_related("client", "service"), pk=object_id)
        changelist = reverse("admin:orders_order_changelist")

        if request.method == "POST":
            newly = sync_related_set(
                order, "assigned_masters", "master", request.POST.getlist("masters"), admin=request.user
            )
            sync_related_set(
                order, "dashboard_assistants", "assistant", request.POST.getlist("assistants"), admin=request.user
            )
            for master in newly:
                create_notification(
                    role="master",
                    master=master,
                    title="Yangi buyurtma biriktirildi",
                    body=order.address_text,
                    data={"order_id": str(order.id), "status": order.status},
                )
            self.message_user(request, "Usta/shogird biriktirish saqlandi.", messages.SUCCESS)
            return redirect(changelist)

        assigned_masters = set(
            str(mid) for mid in order.assigned_masters.filter(is_active=True).values_list("master_id", flat=True)
        )
        assigned_assistants = set(
            str(aid)
            for aid in order.dashboard_assistants.filter(is_active=True).values_list("assistant_id", flat=True)
        )
        candidates = [
            {
                "id": str(master.id),
                "name": master.full_name or master.phone,
                "available": master.is_available,
                "is_master": str(master.id) in assigned_masters,
                "is_assistant": str(master.id) in assigned_assistants,
            }
            for master in Master.objects.filter(is_active=True).order_by("first_name", "last_name")
        ]
        context = {
            **self.admin_site.each_context(request),
            "title": "Usta / Shogird biriktirish",
            "order": order,
            "candidates": candidates,
            "changelist_url": changelist,
        }
        return render(request, "admin/orders/assign.html", context)


@admin.register(OrderMaster)
class OrderMasterAdmin(HomeXModelAdmin):
    list_display = ("order", "master", "has_accepted", "is_active", "assigned_by", "created_at")
    search_fields = ("order__id", "master__phone", "master__first_name", "master__last_name")
    list_filter = ("has_accepted", "is_active")


@admin.register(OrderInventoryUsage)
class OrderInventoryUsageAdmin(HomeXModelAdmin):
    list_display = ("order", "inventory", "quantity", "unit_price", "total_price")


@admin.register(OrderTracking)
class OrderTrackingAdmin(HomeXModelAdmin):
    list_display = ("order", "master_lat", "master_lng", "distance_km", "eta_minutes", "updated_at")
    search_fields = ("order__client__phone", "order__master__phone", "order__address_text")


class ReviewPhotoInline(HomeXTabularInline):
    model = ReviewPhoto


@admin.register(Review)
class ReviewAdmin(HomeXModelAdmin):
    list_display = ("order", "master", "client", "rating", "is_official", "created_at")
    search_fields = ("comment", "master__phone", "client__phone")
    list_filter = ("rating", "is_official")
    inlines = [ReviewPhotoInline]


@admin.register(ReviewPhoto)
class ReviewPhotoAdmin(HomeXModelAdmin):
    list_display = ("review", "image")
