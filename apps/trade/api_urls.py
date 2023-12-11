from django.urls import path

from apps.trade.api_views import (
    ExitAlgoView,
    SaveDeployedOptionStrategyView,
    SaveOptionStrategiesView,
    StartAlgoView,
    UpdateTradingSymbolsView,
)

urlpatterns = [
    path(
        "save_option_strategies",
        SaveOptionStrategiesView.as_view(),
        name="save_option_strategies",
    ),
    path(
        "save_deployed_option_strategy",
        SaveDeployedOptionStrategyView.as_view(),
        name="save_deployed_option_strategy",
    ),
    path("start_algo", StartAlgoView.as_view(), name="start_algo"),
    path("exit_algo", ExitAlgoView.as_view(), name="exit_algo"),
    path(
        "update_tradingsymbols",
        UpdateTradingSymbolsView.as_view(),
        name="update_tradingsymbols",
    ),
]
