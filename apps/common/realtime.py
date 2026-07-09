import json

from django.core.serializers.json import DjangoJSONEncoder


def json_safe(payload):
    """Normalize a payload to JSON-native types before a channel ``group_send``.

    channels_redis serializes group messages with msgpack, which cannot encode
    UUID / Decimal / datetime. Model-derived payloads (order.id UUID, lat/lng
    Decimal, ``PrimaryKeyRelatedField`` UUIDs) carry exactly those types, so we
    round-trip through DjangoJSONEncoder. InMemoryChannelLayer passes objects
    through untouched, which is why this only surfaces with a Redis channel layer.
    """
    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
