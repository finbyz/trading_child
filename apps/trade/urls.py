from django.urls import path

from apps.trade.api_views import (
    AdjustPosition,
    DailyPnlApi,
    EnterUsersAlgo,
    ExitUsersAlgo,
    UpdatePosition,
    UpdateStrategyQuantity,
    UpdateStrategyQuantityPercentage,
)
from apps.trade.views import DailyPnl, DeployeOptionStrategyDetailView

urlpatterns = [
    path(
        "deployed_option_strategy/<int:pk>/",
        DeployeOptionStrategyDetailView.as_view(),
        name="deployed_option_strategy_detail_view",
    ),
    path("daily_pnl", DailyPnl.as_view(), name="daily_pnl"),
    # Api urls
    path("update_position", UpdatePosition.as_view(), name="update_position"),
    path("adjust_all_position", AdjustPosition.as_view(), name="adjust_all_position"),
    path("entry_users_algo", EnterUsersAlgo.as_view(), name="entry_users_algo"),
    path("exit_users_algo", ExitUsersAlgo.as_view(), name="exit_users_algo"),
    path(
        "update_strategy_qty",
        UpdateStrategyQuantity.as_view(),
        name="update_strategy_qty",
    ),
    path(
        "update_strategy_qty_percentage",
        UpdateStrategyQuantityPercentage.as_view(),
        name="update_strategy_qty_percentage",
    ),
    path("api/daily_pnl", DailyPnlApi.as_view(), name="daily_pnl_api"),
]
