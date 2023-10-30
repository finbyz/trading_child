import datetime as dt
import warnings

import numpy as np
import pandas as pd
from asgiref.sync import async_to_sync
from dateutil.parser import parse
from django.core.cache import cache
from django.utils import timezone

from apps.integration.tasks.sockets.get_kws_object import get_kws_object

warnings.filterwarnings("ignore")


def get_instrument(underlying: str) -> pd.DataFrame:
    df = cache.get("OPTION_INSTRUMENTS")
    return df[df["underlying"] == underlying].reset_index(drop=True)


def set_initial_fields_for_instruments(instrument, instruments):
    tz = timezone.get_current_timezone()

    instruments["last_price"] = np.nan
    instruments["exchange_timestamp"] = np.nan
    instruments["last_trade_time"] = np.nan
    instruments["oi"] = np.nan
    instruments["expiry"] = instruments["expiry"].apply(
        lambda x: parse(f"{x} 15:30:00").replace(tzinfo=tz)
    )
    instruments["str_expiry"] = instruments["expiry"].apply(
        lambda y: y.strftime("%d-%b-%Y").upper()
    )
    cache.set(f"{instrument}_OPTION_INSTRUMENTS", instruments)


def set_instrument_cache(df, instruments, instrument):
    df = df[
        [
            "instrument_token",
            "last_price",
            "exchange_timestamp",
            "last_trade_time",
            "oi",
        ]
    ].copy()
    df.rename(columns={"instrument_token": "kite_instrument_token"}, inplace=True)
    instruments = instruments.merge(df, how="left", on="kite_instrument_token")
    instruments["last_price"] = instruments["last_price_y"].fillna(
        instruments["last_price_x"]
    )
    instruments["exchange_timestamp"] = instruments["exchange_timestamp_y"].fillna(
        instruments["exchange_timestamp_x"]
    )
    instruments["last_trade_time"] = instruments["last_trade_time_y"].fillna(
        instruments["last_trade_time_x"]
    )
    instruments["oi"] = instruments["oi_y"].fillna(instruments["oi_x"])
    instruments.drop(
        columns=[
            "last_price_x",
            "last_price_y",
            "exchange_timestamp_x",
            "exchange_timestamp_y",
            "last_trade_time_x",
            "last_trade_time_y",
            "oi_x",
            "oi_y",
        ],
        inplace=True,
    )
    cache.set(f"{instrument}_OPTION_INSTRUMENTS", instruments)

    for websocket_id, instruments_buffer in instruments.groupby("websocket_id"):
        cache.set(
            f"{instrument}_{websocket_id}_OPTION_INSTRUMENTS",
            instruments_buffer.sort_values(
                ["strike", "option_type"], ignore_index=True
            ),
        )


def on_connect(ws, response):
    ws.subscribe(ws.instrument_tokens)
    ws.set_mode(ws.MODE_FULL, ws.instrument_tokens)


def on_ticks(ws, ticks):
    instruments = cache.get(f"{ws.instrument}_OPTION_INSTRUMENTS")
    df = pd.DataFrame(ticks)
    if not df.empty:
        set_instrument_cache(df, instruments, ws.instrument)
    if timezone.localtime().time() > dt.time(15, 30):
        ws.unsubscribe(ws.instrument_tokens)
        ws.close()


def on_close(ws, code, reason):
    if not code and not reason:
        ws.stop()


def run_option_websocket(instrument: str) -> None:
    instruments = get_instrument(instrument)
    if instruments.empty:
        return

    set_initial_fields_for_instruments(instrument, instruments)

    kws = get_kws_object()
    kws.instrument = instrument
    kws.instrument_tokens = instruments["kite_instrument_token"].to_list()

    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close

    kws.connect(threaded=True)
