from rest_framework import serializers

from apps.support.models import SupportMessage


class SupportMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportMessage
        fields = ("id", "sender_role", "message", "attachment", "is_read", "created_at")
        read_only_fields = ("id", "sender_role", "is_read", "created_at")
