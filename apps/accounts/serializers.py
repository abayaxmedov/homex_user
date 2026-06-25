import random
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Client, FCMDevice, Language, Master, OTPRecord
from apps.accounts.tokens import issue_role_tokens
from apps.integrations.adapters import SMSClient


class MasterSummarySerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    distance_km = serializers.SerializerMethodField()
    eta_minutes = serializers.SerializerMethodField()

    class Meta:
        model = Master
        fields = (
            "id",
            "full_name",
            "phone",
            "specialization",
            "avatar",
            "rating",
            "is_online",
            "is_available",
            "lat",
            "lng",
            "last_location_at",
            "distance_km",
            "eta_minutes",
        )

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_distance_km(self, obj):
        return getattr(obj, "distance_km", None)

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_eta_minutes(self, obj):
        return getattr(obj, "eta_minutes", None)


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = (
            "id",
            "phone",
            "first_name",
            "last_name",
            "avatar",
            "language",
            "notifications_enabled",
            "push_enabled",
            "current_tariff",
            "tariff_expires_at",
            "total_spent",
            "total_orders",
        )
        read_only_fields = ("phone", "total_spent", "total_orders", "current_tariff", "tariff_expires_at")


class MasterProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Master
        fields = (
            "id",
            "phone",
            "first_name",
            "last_name",
            "full_name",
            "specialization",
            "avatar",
            "rating",
            "is_online",
            "is_available",
            "lat",
            "lng",
            "last_location_at",
            "language",
            "notifications_enabled",
            "push_enabled",
        )
        read_only_fields = ("phone", "rating", "lat", "lng", "last_location_at")


class MasterLoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            master = Master.objects.get(phone=attrs["phone"], is_active=True)
        except Master.DoesNotExist as exc:
            raise serializers.ValidationError("Telefon yoki parol noto'g'ri") from exc
        if not master.check_password(attrs["password"]):
            raise serializers.ValidationError("Telefon yoki parol noto'g'ri")
        attrs["master"] = master
        return attrs

    def create(self, validated_data):
        master = validated_data["master"]
        tokens = issue_role_tokens(master, "master")
        tokens["master"] = MasterSummarySerializer(master).data
        return tokens


class SendOTPSerializer(serializers.Serializer):
    phone = serializers.CharField()

    def validate_phone(self, value):
        key = f"otp:cooldown:{value}"
        if cache.get(key):
            raise serializers.ValidationError("OTP so'rovi uchun 3 daqiqa kuting")
        return value

    def create(self, validated_data):
        phone = validated_data["phone"]
        code = f"{random.randint(0, 999999):06d}"
        expires_at = timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS)
        OTPRecord.objects.create(phone=phone, code=code, expires_at=expires_at)
        cache.set(f"otp:{phone}", {"code": code, "attempts": 0}, timeout=settings.OTP_TTL_SECONDS)
        cache.set(f"otp:cooldown:{phone}", True, timeout=settings.OTP_SEND_COOLDOWN_SECONDS)
        SMSClient().send_otp(phone, code)
        return {"phone": phone, "expires_in": settings.OTP_TTL_SECONDS}


class VerifyOTPSerializer(serializers.Serializer):
    phone = serializers.CharField()
    otp_code = serializers.CharField(min_length=6, max_length=6)

    def validate(self, attrs):
        phone = attrs["phone"]
        if cache.get(f"otp:block:{phone}"):
            raise serializers.ValidationError("Ko'p noto'g'ri urinish. 15 daqiqa kuting")
        payload = cache.get(f"otp:{phone}")
        record = OTPRecord.objects.filter(phone=phone, is_used=False).order_by("-created_at").first()
        if not payload or not record or record.expires_at < timezone.now():
            raise serializers.ValidationError("OTP muddati tugagan")
        if payload["code"] != attrs["otp_code"]:
            attempts = int(payload.get("attempts", 0)) + 1
            payload["attempts"] = attempts
            cache.set(f"otp:{phone}", payload, timeout=settings.OTP_TTL_SECONDS)
            record.attempts = attempts
            record.save(update_fields=["attempts"])
            if attempts >= settings.OTP_MAX_ATTEMPTS:
                cache.set(f"otp:block:{phone}", True, timeout=settings.OTP_BLOCK_SECONDS)
            raise serializers.ValidationError("OTP kodi noto'g'ri")
        attrs["record"] = record
        return attrs

    def create(self, validated_data):
        phone = validated_data["phone"]
        record = validated_data["record"]
        record.is_used = True
        record.save(update_fields=["is_used"])
        client, created = Client.objects.get_or_create(phone=phone)
        tokens = issue_role_tokens(client, "client")
        tokens["is_new"] = created or not client.first_name
        tokens["client"] = ClientSerializer(client).data
        return tokens


class ClientRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ("first_name", "last_name", "language")


class LanguageSerializer(serializers.Serializer):
    language = serializers.ChoiceField(choices=Language.choices)


class RefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()

    def create(self, validated_data):
        refresh = RefreshToken(validated_data["refresh_token"])
        role = refresh.get("role")
        subject_id = refresh.get("sub")
        model = Master if role == "master" else Client if role == "client" else None
        if not model or not subject_id:
            raise serializers.ValidationError("Refresh token role is invalid")
        try:
            subject = model.objects.get(id=subject_id, is_active=True)
        except model.DoesNotExist as exc:
            raise serializers.ValidationError("Token user not found") from exc
        return issue_role_tokens(subject, role)


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(required=False, allow_blank=True)


class FCMDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCMDevice
        fields = ("id", "token", "platform", "is_active", "created_at")
        read_only_fields = ("id", "is_active", "created_at")
