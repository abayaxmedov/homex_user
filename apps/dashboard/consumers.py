import json

from channels.generic.websocket import AsyncWebsocketConsumer

from apps.dashboard.realtime import dashboard_orders_group


def _is_dashboard_user(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_staff", False)
    )


class DashboardOrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not _is_dashboard_user(user):
            await self.close()
            return
        self.group_name = dashboard_orders_group()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def dashboard_order_event(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": event["event"],
                    "data": event["payload"],
                }
            )
        )
