import asyncio
import datetime as dt

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from trading.celery import app


class CeleryTaskStatusConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        if self.scope["user"].is_anonymous:
            await self.close(code=4004)
            return

        await self.send_celery_task_list()

    async def send_celery_task_list(self):
        while True:
            i = app.control.inspect()

            active_tasks = i.active()
            reserved_tasks = i.reserved()

            active_tasks_list = []
            reserved_tasks_list = []

            for _, row in active_tasks.items():
                for d in row:
                    d["time_start"] = str(dt.datetime.fromtimestamp(d["time_start"]))
                active_tasks_list.extend(row)

            active_tasks_list = sorted(
                active_tasks_list, key=lambda x: x["hostname"], reverse=False
            )

            for _, row in reserved_tasks.items():
                reserved_tasks_list.extend(row)

            reserved_tasks_list = sorted(
                reserved_tasks_list, key=lambda x: x["hostname"], reverse=False
            )

            await self.send_json(
                {
                    "active_tasks": active_tasks_list,
                    "reserved_tasks": reserved_tasks_list,
                }
            )

            await asyncio.sleep(1)
