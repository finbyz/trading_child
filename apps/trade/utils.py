import asyncio
import itertools

import numpy as np
import pandas as pd
from django.core.cache import cache

from apps.integration.utils import get_option_instruments


async def get_kotak_positons():
    return cache.get("KOTAK_NEO_POSITIONS", [])


async def get_dummy_positions():
    return cache.get("DUMMY_POSITIONS", [])


async def calculate_pnl(symbol, websocket_ids: list | None = None, broker=None):
    columns = [
        "username",
        "broker",
        "tradingsymbol",
        "sell_value",
        "buy_value",
        "net_qty",
    ]
    instruments = get_option_instruments(symbol, websocket_ids)

    if broker == "kotak_neo":
        positons = itertools.chain.from_iterable(
            await asyncio.gather(
                get_dummy_positions(),
                get_kotak_positons(),
            )
        )

        df = pd.DataFrame(positons, columns=columns)
    else:
        df = pd.DataFrame(columns=columns)

    if instruments.empty:
        return pd.DataFrame(
            columns=[
                "username",
                "broker",
                "tradingsymbol",
                "sell_value",
                "buy_value",
                "net_qty",
                "broker",
                "pnl",
                "ce_buy_qty",
                "pe_buy_qty",
                "ce_sell_qty",
                "pe_sell_qty",
            ]
        )

    df = pd.merge(df, instruments, on="tradingsymbol")
    df["pnl"] = df["sell_value"] - df["buy_value"] + (df["net_qty"] * df["last_price"])
    df["ce_buy_qty"] = np.where(
        df["tradingsymbol"].str.contains("CE") & (df["net_qty"] > 0),
        df["net_qty"],
        0,
    )
    df["pe_buy_qty"] = np.where(
        df["tradingsymbol"].str.contains("PE") & (df["net_qty"] > 0),
        df["net_qty"],
        0,
    )
    df["ce_sell_qty"] = np.where(
        df["tradingsymbol"].str.contains("CE") & (df["net_qty"] < 0),
        df["net_qty"] * -1,
        0,
    )
    df["pe_sell_qty"] = np.where(
        df["tradingsymbol"].str.contains("PE") & (df["net_qty"] < 0),
        df["net_qty"] * -1,
        0,
    )
    df["tradingsymbol"] = df["tradingsymbol"].fillna("")
    df.fillna(0, inplace=True)

    return df


async def get_user_margin(broker=None):
    if broker == "kotak_neo":
        df = pd.DataFrame(cache.get("KOTAK_NEO_MARGIN"))
        df["broker"] = broker
        return df


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
