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
    elif broker == "dummy":
        positons = await get_dummy_positions()
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
