from channels.generic.websocket import AsyncJsonWebsocketConsumer


class AlertNotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()

        if self.scope["user"].is_anonymous:
            await self.close(code=4004)
            return

        await self.channel_layer.group_add(
            "alert_notifications",
            self.channel_name,
        )

    async def send_notifications(self, event):
        data = event.copy()
        del data["type"]
        await self.send_json(data)


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()

        if self.scope["user"].is_anonymous:
            await self.close(code=4004)
            return

        await self.channel_layer.group_add(
            "notifications",
            self.channel_name,
        )

    async def send_notifications(self, event):
        data = event.copy()
        del data["type"]
        await self.send_json(data)
