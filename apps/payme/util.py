from datetime import datetime, timezone


def time_to_payme(value) -> int:
    """Convert a datetime to Payme's millisecond epoch timestamp.

    Returns ``0`` when the value is falsy (Payme uses 0 for "not set").
    """
    if not value:
        return 0

    return int(value.timestamp() * 1000)


def time_to_service(milliseconds: int) -> datetime:
    """Convert a Payme millisecond epoch timestamp back to an aware datetime (UTC)."""
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
