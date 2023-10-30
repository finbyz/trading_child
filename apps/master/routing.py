from django.urls import path

from apps.master.consumers import (
    AlertNotificationConsumer,
    CeleryTaskStatusConsumer,
    NotificationConsumer,
)

websocket_urlpatterns = [
    path("ws/celery_task/", CeleryTaskStatusConsumer.as_asgi()),
    path("ws/read_notifications", NotificationConsumer.as_asgi()),
    path("ws/alert_notifications", AlertNotificationConsumer.as_asgi()),
]
