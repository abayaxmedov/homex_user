"""Payme network constants."""
from enum import Enum


class Networks(str, Enum):
    """Payme API base URLs (server-to-server SDK / receipts)."""

    PROD_NET = "https://checkout.paycom.uz/api"
    TEST_NET = "https://checkout.test.paycom.uz/api"


# Payme fixes the created-transaction lifetime at 12 hours. A state-1 transaction
# older than this must be auto-cancelled on the next Create/Perform call.
TRANSACTION_TIMEOUT_MS = 43_200_000  # 12 * 60 * 60 * 1000
