from decimal import Decimal, InvalidOperation
from math import asin, cos, radians, sin, sqrt


def to_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def distance_km(lat1, lng1, lat2, lng2):
    lat1 = to_decimal(lat1)
    lng1 = to_decimal(lng1)
    lat2 = to_decimal(lat2)
    lng2 = to_decimal(lng2)
    if None in (lat1, lng1, lat2, lng2):
        return None
    lat1, lng1, lat2, lng2 = map(float, (lat1, lng1, lat2, lng2))
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return round(6371 * 2 * asin(sqrt(a)), 2)


def eta_minutes(distance, average_speed_kmh=30):
    if distance is None:
        return None
    if average_speed_kmh <= 0:
        average_speed_kmh = 30
    return max(int(round((float(distance) / average_speed_kmh) * 60)), 1)
