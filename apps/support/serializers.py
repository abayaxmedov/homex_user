from rest_framework import serializers

from apps.support.models import SupportChat, SupportMessage


class StringPKField(serializers.Field):
    def to_representation(self, value):
        return str(value) if value is not None else None


def _person_name(obj):
    if not obj:
        return ""
    full_name = getattr(obj, "full_name", None)
    if full_name:
        return full_name
    first_name = getattr(obj, "first_name", "") or ""
    last_name = getattr(obj, "last_name", "") or ""
    name = f"{first_name} {last_name}".strip()
    return name or getattr(obj, "username", "") or getattr(obj, "phone", "")


def _sender_payload(obj, role):
    if not obj:
        return None
    return {
        "id": str(obj.id),
        "role": role,
        "username": getattr(obj, "username", None) or _person_name(obj),
        "phone": getattr(obj, "phone", ""),
        "first_name": getattr(obj, "first_name", ""),
        "last_name": getattr(obj, "last_name", ""),
        "email": getattr(obj, "email", ""),
    }


class SupportChatSerializer(serializers.ModelSerializer):
    id = StringPKField(read_only=True)
    client = StringPKField(source="client_id", read_only=True)
    master = StringPKField(source="master_id", read_only=True)
    participant = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = SupportChat
        fields = (
            "id",
            "participant_role",
            "client",
            "master",
            "participant",
            "created_at",
            "updated_at",
            "unread_by_admin",
            "last_message",
        )
        read_only_fields = fields

    def get_participant(self, obj):
        return _sender_payload(obj.participant, obj.participant_role)

    def get_last_message(self, obj):
        if hasattr(obj, "_last_message"):
            last = obj._last_message
        elif getattr(obj, "last_message_id", None):
            last = SupportMessage.objects.select_related("client", "master", "admin").filter(pk=obj.last_message_id).first()
        else:
            last = obj.messages.select_related("client", "master", "admin").order_by("-created_at").first()
        if not last:
            return None
        return SupportMessageSerializer(last, context=self.context).data


class SupportMessageSerializer(serializers.ModelSerializer):
    id = StringPKField(read_only=True)
    chat = StringPKField(source="chat_id", read_only=True)
    client = StringPKField(source="client_id", read_only=True)
    master = StringPKField(source="master_id", read_only=True)
    admin = StringPKField(source="admin_id", read_only=True)
    content = serializers.CharField(source="message", read_only=True)
    timestamp = serializers.DateTimeField(source="created_at", read_only=True)
    from_user = serializers.SerializerMethodField()
    sender = serializers.SerializerMethodField()

    class Meta:
        model = SupportMessage
        fields = (
            "id",
            "chat",
            "sender_role",
            "sender",
            "client",
            "master",
            "admin",
            "message",
            "content",
            "attachment",
            "is_read",
            "from_user",
            "created_at",
            "timestamp",
        )
        read_only_fields = (
            "id",
            "chat",
            "sender_role",
            "sender",
            "client",
            "master",
            "admin",
            "content",
            "is_read",
            "from_user",
            "created_at",
            "timestamp",
        )

    def get_from_user(self, obj):
        return obj.sender_role != "admin"

    def get_sender(self, obj):
        if obj.sender_role == "admin":
            return _sender_payload(obj.admin, "admin")
        if obj.sender_role == "master":
            return _sender_payload(obj.master, "master")
        return _sender_payload(obj.client, "client")
