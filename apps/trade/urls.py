from django.urls import path

from apps.trade.api_views import (
    AdjustPosition,
    DailyPnlApi,
    EnterUsersAlgo,
    ExitOneSide,
    ExitUsersAlgo,
    OneSideExitHold,
    RebalanceView,
    ReentryOneSide,
    ReleaseOneSideExitHold,
    ShiftSingleStrike,
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
    path("rebalance_position", RebalanceView.as_view(), name="rebalance_position"),
    path("reentry_one_side", ReentryOneSide.as_view(), name="reentry_one_side"),
    path("exit_one_side", ExitOneSide.as_view(), name="exit_one_side"),
    path(
        "shift_single_strike",
        ShiftSingleStrike.as_view(),
        name="shift_single_strike",
    ),
    path("one_side_exit_hold", OneSideExitHold.as_view(), name="one_side_exit_hold"),
    path(
        "release_one_side_exit_hold",
        ReleaseOneSideExitHold.as_view(),
        name="release_one_side_exit_hold",
    ),
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
