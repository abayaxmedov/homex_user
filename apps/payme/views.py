"""Payme (Paycom) Merchant API endpoints.

* ``PaymeWebHookAPIView``  — the JSON-RPC merchant webhook (hand this URL to the
  Payme kassa). Authenticates via ``Authorization: Basic base64("Paycom:<key>")``,
  renders every response — success or error — as HTTP 200 JSON-RPC, and is
  therefore exempt from the global HomeX auth/exception envelope.
* ``PaymeCheckoutUrlView`` — client-facing: returns the checkout redirect URL so
  the app can open Payme with one link.
* ``PaymeOrderStatusView`` — client-facing: the app polls this for the real
  (server-to-server confirmed) payment state; never trust the redirect alone.

Protocol reference: https://developer.help.paycom.uz/
"""
import base64
import logging

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.exceptions import ParseError as DRFParseError
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsClient
from apps.common.responses import success_response
from apps.orders.models import Order, OrderStatus
from apps.payme import exceptions
from apps.payme.classes.client import Payme
from apps.payme.const import TRANSACTION_TIMEOUT_MS
from apps.payme.models import PaymeTransaction
from apps.payme.services import (
    build_fiscal_items,
    mark_order_paid,
    mark_order_payment_cancelled,
    order_amount_tiyin,
)
from apps.payme.types import response
from apps.payme.util import time_to_payme, time_to_service

logger = logging.getLogger(__name__)

# Payme cancellation reason for an auto-cancelled, timed-out transaction.
TIMEOUT_CANCEL_REASON = 4


def build_payme_client() -> Payme:
    """Construct the SDK client from settings (checkout links + receipts)."""
    return Payme(
        payme_id=settings.PAYME_MERCHANT_ID,
        payme_key=settings.PAYME_KEY,
        is_test_mode=settings.PAYME_TEST_MODE,
        checkout_url=settings.PAYME_CHECKOUT_URL or None,
    )


@extend_schema(exclude=True)
class PaymeWebHookAPIView(APIView):
    """JSON-RPC merchant webhook. All six Merchant API methods dispatch here."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    # ------------------------------------------------------------------
    # Dispatch + protocol-level errors
    # ------------------------------------------------------------------

    def handle_exception(self, exc):
        """Render every error as an HTTP 200 JSON-RPC ``error`` body.

        Fully bypasses HomeX's global ``homex_exception_handler`` so the
        JSON-RPC envelope Payme expects is preserved.
        """
        if isinstance(exc, exceptions.BasePaymeException):
            return Response(exc.detail)
        if isinstance(exc, DRFParseError):
            return Response(exceptions.ParseError().detail)
        if isinstance(exc, MethodNotAllowed):
            return Response(exceptions.TransportError().detail)
        logger.exception("Payme webhook unhandled error")
        return Response(exceptions.InternalServiceError(str(exc)).detail)

    def post(self, request):
        self.check_ip(request)
        self.check_authorize(request)

        data = request.data  # raises DRFParseError on bad JSON -> handle_exception
        if not isinstance(data, dict):
            raise exceptions.InvalidRequest()

        method = data.get("method")
        params = data.get("params")
        if not method or not isinstance(method, str):
            raise exceptions.InvalidRequest()
        if not isinstance(params, dict):
            raise exceptions.InvalidRequest()

        methods = {
            "CheckPerformTransaction": self.check_perform_transaction,
            "CreateTransaction": self.create_transaction,
            "PerformTransaction": self.perform_transaction,
            "CancelTransaction": self.cancel_transaction,
            "CheckTransaction": self.check_transaction,
            "GetStatement": self.get_statement,
        }
        handler = methods.get(method)
        if handler is None:
            raise exceptions.MethodNotFound(method)

        return Response(handler(params))

    # ------------------------------------------------------------------
    # Auth (Basic base64("Paycom:<key>")) + IP allow-list
    # ------------------------------------------------------------------

    @staticmethod
    def check_authorize(request):
        auth = request.META.get("HTTP_AUTHORIZATION")
        if not auth:
            raise exceptions.PermissionDenied("Missing authorization header")

        try:
            decoded = base64.b64decode(auth.split()[-1]).decode()
            payme_key = decoded.split(":", 1)[-1]
        except Exception:  # noqa: BLE001 - any decode failure is an auth failure
            raise exceptions.PermissionDenied("Invalid authorization header")

        expected = settings.PAYME_TEST_KEY if settings.PAYME_TEST_MODE else settings.PAYME_KEY
        if not expected or payme_key != expected:
            raise exceptions.PermissionDenied("Invalid merchant key")

    def check_ip(self, request):
        allowed = getattr(settings, "PAYME_ALLOWED_IPS", None) or []
        if not allowed:
            return
        if self._client_ip(request) not in allowed:
            raise exceptions.PermissionDenied("Source IP not allowed")

    @staticmethod
    def _client_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require(params, *keys):
        for key in keys:
            if key not in params:
                raise exceptions.InvalidRequest(key)

    @staticmethod
    def fetch_account(params):
        account = params.get("account") or {}
        field = settings.PAYME_ACCOUNT_FIELD
        order_id = account.get(field) or account.get("order_id") or account.get("id")

        if not order_id:
            # data = the account field name, per protocol (-31050..-31099).
            raise exceptions.AccountDoesNotExist(field)

        try:
            return Order.objects.get(pk=order_id)
        except (Order.DoesNotExist, DjangoValidationError, ValueError, TypeError) as exc:
            raise exceptions.AccountDoesNotExist(field) from exc

    @staticmethod
    def validate_amount(order, amount):
        try:
            provided = int(amount)
        except (TypeError, ValueError) as exc:
            raise exceptions.IncorrectAmount("amount") from exc
        if provided != order_amount_tiyin(order):
            raise exceptions.IncorrectAmount("amount")

    @staticmethod
    def get_active_transaction(order_id, exclude_txn_id=None):
        queryset = PaymeTransaction.objects.filter(
            order_id=order_id,
            state__in=[
                PaymeTransaction.CREATED,
                PaymeTransaction.INITIATING,
                PaymeTransaction.SUCCESSFULLY,
            ],
        ).order_by("-created_at")
        if exclude_txn_id:
            queryset = queryset.exclude(transaction_id=exclude_txn_id)
        return queryset.first()

    @staticmethod
    def _is_expired(tx) -> bool:
        age_ms = (timezone.now() - tx.created_at).total_seconds() * 1000
        return age_ms > TRANSACTION_TIMEOUT_MS

    def _locked_tx(self, txn_id):
        try:
            return PaymeTransaction.objects.select_for_update().get(transaction_id=txn_id)
        except PaymeTransaction.DoesNotExist as exc:
            raise exceptions.TransactionNotFound(str(txn_id)) from exc

    # ------------------------------------------------------------------
    # Payme methods
    # ------------------------------------------------------------------

    def check_perform_transaction(self, params):
        self._require(params, "amount", "account")
        order = self.fetch_account(params)
        self.validate_amount(order, params["amount"])

        resp = response.CheckPerformTransaction(allow=True)
        for item in build_fiscal_items(order):
            resp.add_item(item)
        return resp.as_resp()

    def create_transaction(self, params):
        self._require(params, "id", "amount", "account")
        order = self.fetch_account(params)
        self.validate_amount(order, params["amount"])

        txn_id = str(params["id"])
        expired = False

        with transaction.atomic():
            # Lock the order so concurrent creates serialize (one-time payment).
            Order.objects.select_for_update().filter(pk=order.id).first()
            tx = PaymeTransaction.objects.select_for_update().filter(transaction_id=txn_id).first()

            if tx:
                if tx.order_id != order.id or int(tx.amount) != int(params["amount"]):
                    raise exceptions.TransactionAlreadyExists(txn_id)
                if tx.is_initiating() and self._is_expired(tx):
                    tx.mark_as_cancelled(TIMEOUT_CANCEL_REASON, PaymeTransaction.CANCELED_DURING_INIT)
                    expired = True
            else:
                active = self.get_active_transaction(order.id)
                if settings.PAYME_ONE_TIME_PAYMENT and active:
                    raise exceptions.TransactionAlreadyExists(str(active.transaction_id))
                tx = PaymeTransaction.objects.create(
                    transaction_id=txn_id,
                    order=order,
                    amount=int(params["amount"]),
                    state=PaymeTransaction.INITIATING,
                )

        # Commit the auto-cancel above, then signal the timeout error.
        if expired:
            raise exceptions.UnableToPerformOperation(txn_id)

        return response.CreateTransaction(
            transaction=tx.transaction_id,
            state=tx.state,
            create_time=time_to_payme(tx.created_at),
        ).as_resp()

    def perform_transaction(self, params):
        self._require(params, "id")
        txn_id = str(params["id"])
        expired = False

        with transaction.atomic():
            tx = self._locked_tx(txn_id)

            if tx.is_performed():
                result = self._perform_result(tx)
            elif tx.is_cancelled():
                # Nothing changed -> rollback is harmless.
                raise exceptions.UnableToPerformOperation(txn_id)
            elif self._is_expired(tx):
                tx.mark_as_cancelled(TIMEOUT_CANCEL_REASON, PaymeTransaction.CANCELED_DURING_INIT)
                expired = True
                result = None
            else:
                tx.mark_as_performed()
                mark_order_paid(tx.order)  # idempotent, runs exactly once under the row lock
                result = self._perform_result(tx)

        if expired:
            raise exceptions.UnableToPerformOperation(txn_id)

        return result

    def cancel_transaction(self, params):
        self._require(params, "id")
        txn_id = str(params["id"])
        reason = params.get("reason")

        with transaction.atomic():
            tx = self._locked_tx(txn_id)

            if not tx.is_cancelled():
                if tx.is_performed():
                    # Goods/service already delivered -> cannot auto-refund (-31007).
                    if tx.order.status == OrderStatus.COMPLETED:
                        raise exceptions.UnableToCancelTransaction(txn_id)
                    tx.mark_as_cancelled(reason, PaymeTransaction.CANCELED)
                    mark_order_payment_cancelled(tx.order)
                else:
                    tx.mark_as_cancelled(reason, PaymeTransaction.CANCELED_DURING_INIT)

        return response.CancelTransaction(
            transaction=tx.transaction_id,
            state=tx.state,
            cancel_time=time_to_payme(tx.cancelled_at),
        ).as_resp()

    def check_transaction(self, params):
        self._require(params, "id")
        tx = PaymeTransaction.get_by_transaction_id(str(params["id"]))
        return response.CheckTransaction(
            transaction=tx.transaction_id,
            state=tx.state,
            reason=tx.cancel_reason,
            create_time=time_to_payme(tx.created_at),
            perform_time=time_to_payme(tx.performed_at),
            cancel_time=time_to_payme(tx.cancelled_at),
        ).as_resp()

    def get_statement(self, params):
        self._require(params, "from", "to")
        field = settings.PAYME_ACCOUNT_FIELD
        transactions = PaymeTransaction.objects.filter(
            created_at__range=[time_to_service(params["from"]), time_to_service(params["to"])]
        )

        result = response.GetStatement(transactions=[])
        for t in transactions:
            result.transactions.append(
                {
                    "id": t.transaction_id,
                    "time": time_to_payme(t.created_at),
                    "amount": int(t.amount),
                    "account": {field: str(t.order_id)},
                    "create_time": time_to_payme(t.created_at),
                    "perform_time": time_to_payme(t.performed_at),
                    "cancel_time": time_to_payme(t.cancelled_at),
                    "transaction": t.transaction_id,
                    "state": t.state,
                    "reason": t.cancel_reason,
                }
            )
        return result.as_resp()

    # ------------------------------------------------------------------
    # Result builders
    # ------------------------------------------------------------------

    @staticmethod
    def _perform_result(tx):
        return response.PerformTransaction(
            transaction=tx.transaction_id,
            state=tx.state,
            perform_time=time_to_payme(tx.performed_at),
        ).as_resp()


@extend_schema(tags=["Payme"], summary="Buyurtma uchun Payme checkout havolasi")
class PaymeCheckoutUrlView(APIView):
    """Return the Payme checkout redirect URL/POST-form for the client's order."""

    permission_classes = [IsClient]

    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id, client=request.user)
        amount = order_amount_tiyin(order)
        if amount <= 0:
            raise ValidationError("Buyurtma summasi 0 — to'lov havolasi yaratib bo'lmaydi.")

        return_url = request.data.get("return_url") or settings.PAYME_RETURN_DEEPLINK
        lang = request.data.get("lang") or settings.PAYME_CHECKOUT_LANG

        payme = build_payme_client()
        checkout_url = payme.initializer.generate_pay_link(str(order.id), amount, return_url, lang)
        post_form = payme.initializer.generate_post_params(str(order.id), amount, return_url, lang)

        return success_response(
            {
                "order_id": str(order.id),
                "amount": amount,
                "checkout_url": checkout_url,
                "post": post_form,
            }
        )


@extend_schema(tags=["Payme"], summary="Buyurtma to'lov holati (app poll qiladi)")
class PaymeOrderStatusView(APIView):
    """The app polls this for the server-confirmed payment state of an order."""

    permission_classes = [IsClient]

    def get(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id, client=request.user)
        latest = order.payme_transactions.order_by("-created_at").first()
        return success_response(
            {
                "order_id": str(order.id),
                "is_paid": order.is_paid,
                "paid_at": order.paid_at,
                "amount": order_amount_tiyin(order),
                "transaction_state": latest.state if latest else None,
            }
        )
