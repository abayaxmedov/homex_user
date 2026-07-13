import random
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Client, FCMDevice, Language, Master, MasterApprovalStatus, OTPRecord
from apps.accounts.tokens import issue_role_tokens
from apps.common.phone import normalize_phone
from apps.integrations.adapters import send_otp_async


def _playmarket_test_phone():
    return normalize_phone(getattr(settings, "PLAYMARKET_TEST_PHONE", ""))


def _is_playmarket_test_phone(phone):
    configured_phone = _playmarket_test_phone()
    configured_otp = getattr(settings, "PLAYMARKET_TEST_OTP", "")
    return bool(configured_phone and configured_otp) and phone == configured_phone


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
    current_tariff = serializers.SerializerMethodField(help_text="Client ulangan tarif nomi. ID emas, masalan: Premium.")
    addresses_count = serializers.SerializerMethodField(help_text="Clientga tegishli manzillar soni. Profile page count uchun.")

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
            "addresses_count",
            "total_spent",
            "total_orders",
        )
        read_only_fields = (
            "phone",
            "total_spent",
            "total_orders",
            "current_tariff",
            "tariff_expires_at",
            "addresses_count",
        )

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_current_tariff(self, obj):
        return obj.current_tariff.name if obj.current_tariff else None

    @extend_schema_field(serializers.IntegerField)
    def get_addresses_count(self, obj):
        return obj.addresses.count()


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
            "approval_status",
            "approved_at",
            "rejected_reason",
            "is_online",
            "is_available",
            "lat",
            "lng",
            "last_location_at",
            "language",
            "notifications_enabled",
            "push_enabled",
        )
        read_only_fields = (
            "phone",
            "rating",
            "approval_status",
            "approved_at",
            "rejected_reason",
            "lat",
            "lng",
            "last_location_at",
        )


class MasterLoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            master = Master.objects.get(phone=attrs["phone"])
        except Master.DoesNotExist as exc:
            raise serializers.ValidationError("Telefon yoki parol noto'g'ri") from exc
        if master.approval_status == MasterApprovalStatus.PENDING:
            raise serializers.ValidationError("Arizangiz admin tasdig'ini kutmoqda")
        if master.approval_status == MasterApprovalStatus.REJECTED:
            raise serializers.ValidationError(master.rejected_reason or "Arizangiz admin tomonidan rad etilgan")
        if not master.is_active:
            raise serializers.ValidationError("Master akkaunti faol emas")
        if not master.password:
            raise serializers.ValidationError("Admin hali login parol bermagan")
        if not master.check_password(attrs["password"]):
            raise serializers.ValidationError("Telefon yoki parol noto'g'ri")
        attrs["master"] = master
        return attrs

    def create(self, validated_data):
        master = validated_data["master"]
        tokens = issue_role_tokens(master, "master")
        tokens["master"] = MasterSummarySerializer(master).data
        return tokens


class MasterRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Master
        fields = ("id", "first_name", "last_name", "phone", "specialization", "approval_status", "created_at")
        read_only_fields = ("id", "approval_status", "created_at")

    def validate_phone(self, value):
        existing = Master.objects.filter(phone=value).first()
        if existing and existing.approval_status == MasterApprovalStatus.APPROVED:
            raise serializers.ValidationError("Bu telefon raqam bilan master allaqachon mavjud")
        return value

    def create(self, validated_data):
        master = Master.objects.filter(phone=validated_data["phone"]).first()
        if master:
            for field in ("first_name", "last_name", "specialization"):
                setattr(master, field, validated_data.get(field, getattr(master, field)))
            master.approval_status = MasterApprovalStatus.PENDING
            master.is_active = False
            master.password = ""
            master.rejected_reason = ""
            master.approved_at = None
            master.save(
                update_fields=[
                    "first_name",
                    "last_name",
                    "specialization",
                    "approval_status",
                    "is_active",
                    "password",
                    "rejected_reason",
                    "approved_at",
                    "updated_at",
                ]
            )
            return master
        return Master.objects.create(
            **validated_data,
            password="",
            is_active=False,
            approval_status=MasterApprovalStatus.PENDING,
        )


class SendOTPSerializer(serializers.Serializer):
    phone = serializers.CharField()

    def validate_phone(self, value):
        # Normalize first so every format variant (+998.., 998.., dashes) collapses
        # to ONE cooldown key — otherwise the per-phone cooldown is trivially bypassed.
        value = normalize_phone(value)
        if _is_playmarket_test_phone(value):
            return value
        if cache.get(f"otp:cooldown:{value}"):
            raise serializers.ValidationError("OTP so'rovi uchun 3 daqiqa kuting")
        return value

    def create(self, validated_data):
        phone = validated_data["phone"]  # already normalized in validate_phone
        if _is_playmarket_test_phone(phone):
            return {"phone": phone, "expires_in": settings.OTP_TTL_SECONDS}
        code = f"{random.randint(0, 999999):06d}"
        expires_at = timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS)
        OTPRecord.objects.create(phone=phone, code=code, expires_at=expires_at)
        cache.set(f"otp:{phone}", {"code": code, "attempts": 0}, timeout=settings.OTP_TTL_SECONDS)
        cache.set(f"otp:cooldown:{phone}", True, timeout=settings.OTP_SEND_COOLDOWN_SECONDS)
        # Dispatch off the request path: a slow/unreachable Eskiz must not block the
        # shared ASGI worker thread (would freeze the whole API).
        send_otp_async(phone, code)
        return {"phone": phone, "expires_in": settings.OTP_TTL_SECONDS}


class VerifyOTPSerializer(serializers.Serializer):
    phone = serializers.CharField()
    otp_code = serializers.CharField(min_length=6, max_length=6)

    def validate(self, attrs):
        phone = normalize_phone(attrs["phone"])  # same canonical form as send-otp
        attrs["phone"] = phone
        if _is_playmarket_test_phone(phone):
            if attrs["otp_code"] != getattr(settings, "PLAYMARKET_TEST_OTP", ""):
                raise serializers.ValidationError("OTP kodi noto'g'ri")
            attrs["record"] = None
            return attrs
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
        if record is not None:
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
        try:
            refresh = RefreshToken(validated_data["refresh_token"])
        except TokenError as exc:
            raise serializers.ValidationError({"refresh_token": str(exc)})
        role = refresh.get("role")
        subject_id = refresh.get("sub")
        model = Master if role == "master" else Client if role == "client" else None
        if not model or not subject_id:
            raise serializers.ValidationError("Refresh token role is invalid")
        lookup = {"id": subject_id, "is_active": True}
        if role == "master":
            lookup["approval_status"] = MasterApprovalStatus.APPROVED
        try:
            subject = model.objects.get(**lookup)
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
        extra_kwargs = {"token": {"validators": []}}

    def validate_token(self, value):
        return value.strip()
