import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trading.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
http = get_asgi_application()

from apps.integration import routing as integration_routing  # noqa E401
from apps.master import routing as master_routing  # noqa E401
from apps.trade import routing as trade_routing  # noqa E401

application = ProtocolTypeRouter(
    {
        "http": http,
        "websocket": AuthMiddlewareStack(
            URLRouter(
                master_routing.websocket_urlpatterns
                + integration_routing.websocket_urlpatterns
                + trade_routing.websocket_urlpatterns,
            ),
        ),
    }
)
