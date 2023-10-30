from django.urls import path

from apps.trade.api_views import (
    SaveDeployedOptionStrategyView,
    SaveOptionStrategiesView,
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
]
