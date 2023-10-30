from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.trade.utils import (
    adjust_positions,
    calculate_daily_initial_margin_for_all_users,
    calculate_option_strategy_stop_loss,
    update_daily_order_book,
    update_daily_pnl,
    update_positions,
)
from trading import celery_app as app


@app.task(name="Adjust Positions", bind=True)
def adjust_positions_task(
    self,
    symbol: str,
    broker: str | None = None,
    username: str | None = None,
    websocket_ids: list[str] | None = None,
):
    return async_to_sync(adjust_positions)(
        symbol=symbol,
        broker=broker,
        username=username,
        websocket_ids=websocket_ids,
    )


@app.task(name="Calculate Daily Initial Margin For All Users", bind=True)
def calculate_daily_initial_margin_for_all_users_task(self):
    return async_to_sync(calculate_daily_initial_margin_for_all_users)()


@app.task(name="Calculate Option Strategy Stoploss", bind=True)
def calculate_option_strategy_stop_loss_task(self):
    return calculate_option_strategy_stop_loss()


@app.task(name="Update Daily Order Book", bind=True)
def update_daily_order_book_task(self):
    return async_to_sync(update_daily_order_book)()


@app.task(name="Update Daily Pnl", bind=True)
def update_daily_pnl_task(self):
    return update_daily_pnl(date=timezone.localdate())


@app.task(name="Update Positions", bind=True)
def update_positions_task(self, broker: str | None = None):
    return async_to_sync(update_positions)(broker=broker)
