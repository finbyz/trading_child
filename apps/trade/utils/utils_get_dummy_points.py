from functools import lru_cache

import pandas as pd

from apps.trade.models import (
    DeployedOptionStrategyUser as DeployedOptionStrategyUserModel,
)
from apps.trade.utils.utils_calculate_pnl import calculate_pnl


@lru_cache
def get_dummy_user(strategy_id):
    broker = DeployedOptionStrategyUserModel.objects.filter(
        parent__pk=strategy_id, broker_api__broker="dummy"
    ).first()

    if broker:
        return (
            broker.broker_api.user.get_username(),
            broker.parent.instrument.symbol,
            broker.parent.websocket_ids.split(","),
            broker.parent.lot_size * broker.lots,
        )

    return None, None


async def get_dummy_points(strategy_id):
    username, symbol, websocket_ids, quantity = get_dummy_user(strategy_id)

    if username:
        df = await calculate_pnl(
            symbol=symbol,
            websocket_ids=websocket_ids,
            broker="dummy",
        )

        df_square_of_positions = df[df["net_qty"] == 0].sort_values(
            [
                "username",
                "net_qty",
                "tradingsymbol",
            ]
        )

        df_open_positions = df[df["net_qty"] != 0].sort_values(
            [
                "username",
                "net_qty",
                "tradingsymbol",
            ]
        )

        df = pd.concat([df_open_positions, df_square_of_positions], ignore_index=True)

        return round(df[df["username"] == username].pnl.sum() / quantity, 2)

    return 0
