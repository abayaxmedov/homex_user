"""Inbound merchant-webhook JSON-RPC exceptions.

Each exception renders itself as a Payme JSON-RPC error body
(``{"error": {"code", "message", "data"}}``) with HTTP 200, per the Merchant
API protocol: https://developer.help.paycom.uz/
"""
import logging

from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class BasePaymeException(APIException):
    """Base JSON-RPC merchant error. Always HTTP 200 with an ``error`` body."""

    status_code = 200
    error_code = None
    message = None

    # pylint: disable=super-init-not-called
    def __init__(self, message: str = None):
        detail: dict = {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "data": message,
            }
        }
        logger.error(f"Payme error detail: {detail}")
        self.detail = detail


class PermissionDenied(BasePaymeException):
    """Raised when the client is not allowed to access the server."""

    status_code = 200
    error_code = -32504
    message = "Permission denied."


class MethodNotFound(BasePaymeException):
    """Raised when the requested method does not exist."""

    status_code = 200
    error_code = -32601
    message = "Method not found."


class InternalServiceError(BasePaymeException):
    """Raised when an unexpected error occurs while handling a transaction."""

    status_code = 200
    error_code = -32400
    message = {
        "uz": "Tizimda xatolik yuzaga keldi.",
        "ru": "Внутренняя ошибка сервиса.",
        "en": "Internal service error.",
    }


class TransportError(BasePaymeException):
    """Raised when the request is not a POST (transport-level error)."""

    status_code = 200
    error_code = -32300
    message = {
        "uz": "Transport xatosi.",
        "ru": "Ошибка транспорта.",
        "en": "Transport error.",
    }


class ParseError(BasePaymeException):
    """Raised when the request body is not valid JSON."""

    status_code = 200
    error_code = -32700
    message = {
        "uz": "JSON xatosi.",
        "ru": "Ошибка разбора JSON.",
        "en": "Parse error.",
    }


class InvalidRequest(BasePaymeException):
    """Raised when required JSON-RPC fields are missing or malformed."""

    status_code = 200
    error_code = -32600
    message = {
        "uz": "So'rov noto'g'ri.",
        "ru": "Неверный запрос.",
        "en": "Invalid request.",
    }


class AccountDoesNotExist(BasePaymeException):
    """Raised when the account (order) does not exist or was deleted."""

    status_code = 200
    error_code = -31050
    message = {
        "uz": "Hisob topilmadi.",
        "ru": "Счет не найден.",
        "en": "Account does not exist.",
    }


class IncorrectAmount(BasePaymeException):
    """Raised when the provided amount does not match the order total."""

    status_code = 200
    error_code = -31001
    message = {
        "ru": "Неверная сумма.",
        "uz": "Noto'g'ri summa.",
        "en": "Incorrect amount.",
    }


class TransactionAlreadyExists(BasePaymeException):
    """Raised when an active transaction already exists for the account."""

    status_code = 200
    error_code = -31099
    message = {
        "uz": "Tranzaksiya allaqachon mavjud.",
        "ru": "Транзакция уже существует.",
        "en": "Transaction already exists.",
    }


class TransactionNotFound(BasePaymeException):
    """Raised when the transaction id is unknown on the merchant side."""

    status_code = 200
    error_code = -31003
    message = {
        "uz": "Tranzaksiya topilmadi.",
        "ru": "Транзакция не найдена.",
        "en": "Transaction not found.",
    }


class UnableToPerformOperation(BasePaymeException):
    """Raised when a transaction cannot be performed (e.g. timed out)."""

    status_code = 200
    error_code = -31008
    message = {
        "uz": "Operatsiyani bajarib bo'lmaydi.",
        "ru": "Невозможно выполнить операцию.",
        "en": "Unable to perform operation.",
    }


class UnableToCancelTransaction(BasePaymeException):
    """Raised when a performed transaction cannot be cancelled."""

    status_code = 200
    error_code = -31007
    message = {
        "uz": "Tranzaksiyani bekor qilib bo'lmaydi.",
        "ru": "Невозможно отменить транзакцию.",
        "en": "Unable to cancel transaction.",
    }


class InvalidFiscalParams(BasePaymeException):
    """Raised when the provided fiscal parameters are invalid."""

    status_code = 200
    error_code = -32602
    message = {
        "uz": "Fiskal parametrlarida kamchiliklar bor.",
        "ru": "Неверные фискальные параметры.",
        "en": "Invalid fiscal parameters.",
    }


class InvalidAccount(BasePaymeException):
    """Raised when the provided account payload is malformed."""

    status_code = 200
    error_code = -31050
    message = {
        "uz": "Hisob nomida kamchilik bor.",
        "ru": "Неверный номер счета.",
        "en": "Invalid account.",
    }


exception_whitelist = (
    IncorrectAmount,
    MethodNotFound,
    PermissionDenied,
    TransportError,
    ParseError,
    InvalidRequest,
    AccountDoesNotExist,
    TransactionAlreadyExists,
    TransactionNotFound,
    UnableToPerformOperation,
    UnableToCancelTransaction,
    InvalidFiscalParams,
    InvalidAccount,
    InternalServiceError,
)
