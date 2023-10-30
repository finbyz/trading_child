from django.urls import path

from apps.trade.consumers import (
    DeployedOptionStrategyPositionConsumer,
    LivePnlStrategyConsumer,
    StopLossDifference,
)

websocket_urlpatterns = [
    path(
        "ws/deployed_option_strategy_symbol/<int:pk>",
        DeployedOptionStrategyPositionConsumer.as_asgi(),
    ),
    path(
        "ws/pnl/<int:pk>",
        LivePnlStrategyConsumer.as_asgi(),
    ),
    path("ws/stop_loss_difference/<int:pk>", StopLossDifference.as_asgi()),
]
