from django.urls import path

from apps.integration.consumers import PCRConsumer

websocket_urlpatterns = [
    path("ws/pcr/", PCRConsumer.as_asgi()),
]
