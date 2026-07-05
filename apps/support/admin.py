import json

from django.contrib import admin, messages
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Case, IntegerField, Value, When
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.common.admin_mixins import HomeXModelAdmin
from apps.support.models import SupportChat, SupportMessage
from apps.support.serializers import SupportMessageSerializer
from apps.support.services import (
    broadcast_admin_update,
    broadcast_support_message,
    create_support_message,
    mark_chat_read_by_admin,
)


class UnreadSupportFilter(admin.SimpleListFilter):
    """Filter support chats by whether they have unread (new) messages."""

    title = "Yangi xabarlar"
    parameter_name = "unread"

    def lookups(self, request, model_admin):
        return (("1", "Yangi xabari borlar"), ("0", "O'qilganlar"))

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(unread_by_admin__gt=0)
        if self.value() == "0":
            return queryset.filter(unread_by_admin=0)
        return queryset


@admin.register(SupportChat)
class SupportChatAdmin(HomeXModelAdmin):
    list_display = ("status_badge", "participant_role", "participant_display", "unread_by_admin", "updated_at", "open_chat")
    list_display_links = ("participant_role", "participant_display")
    search_fields = (
        "client__phone",
        "client__first_name",
        "client__last_name",
        "master__phone",
        "master__first_name",
        "master__last_name",
    )
    list_filter = (UnreadSupportFilter, "participant_role")
    readonly_fields = ("created_at", "updated_at", "unread_by_admin")
    actions = ["reply_to_selected"]

    def get_queryset(self, request):
        # Annotate a sort key BEFORE ordering is applied so chats with new
        # (unread) messages float to the top. We build the queryset the same way
        # Django's ModelAdmin.get_queryset does, but inject the annotation first
        # so get_ordering can reference it.
        queryset = self.model._default_manager.get_queryset().annotate(
            _has_unread=Case(
                When(unread_by_admin__gt=0, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset

    def get_ordering(self, request):
        # Unread chats first, then most recently updated.
        return ("-_has_unread", "-updated_at")

    def participant_display(self, obj):
        return obj.participant or "-"

    participant_display.short_description = "Participant"

    def status_badge(self, obj):
        unread = obj.unread_by_admin or 0
        if unread:
            return format_html(
                '<span class="support-status-badge" data-chat-id="{}" data-unread="{}" '
                'style="display:inline-flex;align-items:center;gap:4px;background:#dc3545;'
                'color:#fff;font-weight:700;padding:2px 9px;border-radius:10px;font-size:11px;'
                'white-space:nowrap;">● Yangi ({})</span>',
                obj.id,
                unread,
                unread,
            )
        return format_html(
            '<span class="support-status-badge" data-chat-id="{}" data-unread="0" '
            'style="color:#6c757d;font-size:11px;white-space:nowrap;">O‘qilgan</span>',
            obj.id,
        )

    status_badge.short_description = "Holat"

    def open_chat(self, obj):
        url = reverse("admin:support_supportchat_change", args=(obj.id,))
        return mark_safe(
            f'<a class="button support-chat-reply-btn" data-chat-id="{obj.id}" href="{url}" '
            'style="font-weight:700;padding:4px 8px;background:#0b5ed7;color:#fff;'
            'border-radius:4px;text-decoration:none;display:inline-flex;align-items:center;">Reply</a>'
        )

    open_chat.short_description = "Reply"

    def reply_to_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one chat to reply to.", level=messages.ERROR)
            return None
        return redirect(reverse("admin:support_supportchat_change", args=(queryset.first().id,)))

    reply_to_selected.short_description = "Reply to selected chat"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        chat = self.get_object(request, object_id)

        if request.method == "POST" and "reply_content" in request.POST:
            content = request.POST.get("reply_content", "").strip()
            if chat and content:
                message = create_support_message(chat=chat, sender=request.user, content=content)
                broadcast_support_message(message)
            return redirect(request.path)

        if chat and mark_chat_read_by_admin(chat):
            broadcast_admin_update(chat)

        messages_qs = (
            chat.messages.select_related("client", "master", "admin").order_by("created_at")
            if chat
            else SupportMessage.objects.none()
        )
        initial_messages = SupportMessageSerializer(messages_qs, many=True).data

        extra_context = extra_context or {}
        extra_context.update(
            {
                "admin_chat_id": getattr(chat, "id", None),
                "initial_messages": json.dumps(initial_messages, cls=DjangoJSONEncoder),
            }
        )
        return super().change_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        return super().changelist_view(request, extra_context=extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "messages/<uuid:chat_id>/json/",
                self.admin_site.admin_view(self.chat_messages_json),
                name="support_supportchat_messages_json",
            ),
        ]
        return custom_urls + urls

    def chat_messages_json(self, request, chat_id):
        if not request.user.is_staff:
            return HttpResponseForbidden()
        chat = self.get_object(request, chat_id)
        if not chat:
            return JsonResponse({"error": "Chat not found"}, status=404)
        if mark_chat_read_by_admin(chat):
            broadcast_admin_update(chat)
        messages_qs = chat.messages.select_related("client", "master", "admin").order_by("created_at")
        serializer = SupportMessageSerializer(messages_qs, many=True)
        return JsonResponse(serializer.data, safe=False)


@admin.register(SupportMessage)
class SupportMessageAdmin(HomeXModelAdmin):
    list_display = ("chat", "sender_role", "client", "master", "admin", "is_read", "created_at")
    search_fields = ("message", "client__phone", "master__phone")
    list_filter = ("sender_role", "is_read")
    readonly_fields = ("created_at", "updated_at")
