import numpy as np
import pandas as pd
from django.core.cache import cache

from apps.trade.utils.utils_calculate_pnl import calculate_pnl


async def quantity_mistmatch(symbol, websocket_ids: list | None = None, broker=None):
    df = await calculate_pnl(symbol, websocket_ids, broker)

    if not df.empty:
        quantity_map = (
            df.groupby(["username", "tradingsymbol"])
            .agg({"net_qty": "sum", "broker": "first"})
            .reset_index()
        )
    else:
        quantity_map = pd.DataFrame(
            columns=[
                "username",
                "broker",
                "tradingsymbol",
                "net_qty",
            ]
        )
    tradingsymbol_map = []

    deployed_strategies = cache.get("DEPLOYED_STRATEGIES", {})

    for strategy_id, _ in deployed_strategies.items():
        tradingsymbols = cache.get(f"TRADINGSYMBOLS_{strategy_id}", {})

        user_in_cache = [
            x["user"].username
            for x in deployed_strategies.get(str(strategy_id), {}).get(
                "user_params", []
            )
        ]
        user_in_cache_quantity = {
            x["user"].username: [x["quantity_multiple"], x["broker"]]
            for x in deployed_strategies.get(str(strategy_id), {}).get(
                "user_params", []
            )
        }

        for idx, row in enumerate(tradingsymbols):
            for user in user_in_cache:
                data = []
                qty = user_in_cache_quantity[user][0][idx]
                broker = user_in_cache_quantity[user][1]
                if row["pe_tradingsymbol"]:
                    data.append(
                        {
                            "username": user,
                            "broker": broker,
                            "expected_qty": row["position_type"] * qty,
                            "tradingsymbol": row["pe_tradingsymbol"],
                        }
                    )

                if row["ce_tradingsymbol"]:
                    data.append(
                        {
                            "username": user,
                            "broker": broker,
                            "expected_qty": row["position_type"] * qty,
                            "tradingsymbol": row["ce_tradingsymbol"],
                        }
                    )

                tradingsymbol_map.extend(data)

    expected_qty_df = pd.DataFrame(
        tradingsymbol_map,
        columns=[
            "username",
            "broker",
            "expected_qty",
            "tradingsymbol",
        ],
    )
    expected_qty_df = (
        expected_qty_df.groupby(
            [
                "username",
                "broker",
                "tradingsymbol",
            ]
        )
        .agg({"expected_qty": "sum"})
        .reset_index()
    )

    quantity_map_df = pd.merge(
        quantity_map,
        expected_qty_df,
        on=[
            "username",
            "broker",
            "tradingsymbol",
        ],
        how="outer",
    ).fillna(0)

    quantity_map_df["mismatch"] = np.where(
        quantity_map_df["expected_qty"] != quantity_map_df["net_qty"], 1, 0
    )

    return df, quantity_map_df
