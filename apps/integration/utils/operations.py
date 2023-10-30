from functools import lru_cache

import pandas as pd
from dateutil.parser import parse
from django.core.cache import cache

from trading.settings import UNDERLYINGS, WEBSOCKET_IDS


def divide_and_list(list_size, x):
    equal = x // list_size
    remaining = x - (equal * list_size)

    lst = [equal for _ in range(list_size)]

    for i in range(list_size):
        if remaining <= 0:
            break

        lst[i] = lst[i] + 1
        remaining = remaining - 1

    return lst


def get_option_instruments_row(symbol: str, tradingsymbol: str, websocket_id: str):
    if tradingsymbol is not None:
        df = cache.get(f"{symbol}_{websocket_id}_OPTION_INSTRUMENTS")
        return df[df["tradingsymbol"] == tradingsymbol].iloc[0]


def get_option_geeks_instruments_row(
    symbol: str,
    tradingsymbol: str,
    websocket_id: str,
):
    if tradingsymbol is not None:
        df = cache.get(f"{symbol}_{websocket_id}_OPTION_GREEKS_INSTRUMENTS")
        return df[df["tradingsymbol"] == tradingsymbol].iloc[0]


def get_option_ltp(symbol: str, tradingsymbol: str, websocket_id: str):
    df = cache.get(f"{symbol}_{websocket_id}_OPTION_INSTRUMENTS")
    return float(df[df["tradingsymbol"] == tradingsymbol].iloc[0]["last_price"])


def quantity_split(quantity, freeze_qty):
    chunks = quantity // freeze_qty
    quantity_split_list = [int(freeze_qty) for _ in range(chunks)]

    if remaining_qty := quantity % freeze_qty:
        quantity_split_list.append(int(remaining_qty))

    return quantity_split_list


@lru_cache(maxsize=128)
def convert_timestamp(timestamp: str):
    return parse(timestamp + "+05:30")


def get_all_option_instruments():
    final_df = pd.DataFrame()
    for websocket_id in WEBSOCKET_IDS:
        for underlying in UNDERLYINGS:
            final_df = pd.concat(
                [
                    final_df,
                    cache.get(
                        f"{underlying}_{websocket_id}_OPTION_INSTRUMENTS",
                        pd.DataFrame(),
                    ),
                ],
                ignore_index=True,
            )

    return final_df


def get_option_instruments(symbol: str, websocket_ids: list | None = None):
    final_df = pd.DataFrame()
    for websocket_id in websocket_ids:
        final_df = pd.concat(
            [
                final_df,
                cache.get(
                    f"{symbol}_{websocket_id}_OPTION_GREEKS_INSTRUMENTS",
                    pd.DataFrame(),
                ),
            ],
            ignore_index=True,
        )

    return final_df


def get_option_greeks_instruments(symbol: str, websocket_ids: list | None = None):
    final_df = pd.DataFrame()
    for websocket_id in websocket_ids:
        final_df = pd.concat(
            [
                final_df,
                cache.get(
                    f"{symbol}_{websocket_id}_OPTION_GREEKS_INSTRUMENTS",
                    pd.DataFrame(),
                ),
            ],
            ignore_index=True,
        )

    return final_df


def get_spot_ltp(symbol):
    return cache.get(f"{symbol}_LTP")
