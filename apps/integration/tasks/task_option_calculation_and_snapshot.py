import asyncio
import contextlib
import datetime as dt
import threading
import time

import numpy as np
import pandas as pd
from asgiref.sync import async_to_sync
from dateutil.parser import parse
from django.core.cache import cache
from django.utils import timezone

from apps.integration.models import Holiday as HolidayModel
from apps.integration.utils import caclulate_option_greeks
from trading.settings import UNDERLYING_STRIKES, UNDERLYINGS, WEBSOCKET_IDS


def get_option_websocket_cache_map():
    return [
        (
            underlying,
            f"{underlying}_{websocket_id}_OPTION_INSTRUMENTS",
            f"{underlying}_{websocket_id}_OPTION_GREEKS_INSTRUMENTS",
        )
        for websocket_id in WEBSOCKET_IDS
        for underlying in UNDERLYINGS
    ]


def set_option_greeks_in_cache(
    ct,
    underlying,
    get_cache_id,
    set_cache_id,
):
    instruments = cache.get(get_cache_id, pd.DataFrame())
    if not instruments.empty:
        print(cache.get(f"{underlying}_LTP"))
        instruments["spot_price"] = cache.get(f"{underlying}_LTP")
        instruments["timestamp"] = ct.replace(microsecond=0)
        instruments["time_left"] = (
            (instruments["expiry"] - instruments["timestamp"]).dt.total_seconds()
            / 86400
        ) / 365
        (
            instruments["sigma"],
            instruments["delta"],
            instruments["theta"],
            instruments["gamma"],
            instruments["vega"],
        ) = np.vectorize(caclulate_option_greeks)(
            instruments["last_price"],
            instruments["spot_price"],
            instruments["strike"],
            instruments["time_left"],
            0.10,
            instruments["option_type"],
        )

        cache.set(set_cache_id, instruments)


async def set_options_greeks(ct, option_websocket_cache_map):
    await asyncio.gather(
        *[
            asyncio.to_thread(
                set_option_greeks_in_cache,
                ct=ct,
                underlying=underlying,
                get_cache_id=get_cache_id,
                set_cache_id=set_cache_id,
            )
            for underlying, get_cache_id, set_cache_id in option_websocket_cache_map
        ]
    )


def calculate_live_option_greeks():
    option_websocket_cache_map = get_option_websocket_cache_map()

    if timezone.localtime().time() < dt.time(9, 15, 2):
        ct = timezone.localtime()
        time.sleep(
            (
                ct.replace(hour=9, minute=15, second=2, microsecond=0) - ct
            ).total_seconds()
        )
    print("here")
    while True:
        ct = timezone.localtime().replace(microsecond=0)
        if ct.time() >= dt.time(15, 30):
            break

        async_to_sync(set_options_greeks)(ct, option_websocket_cache_map)

        with contextlib.suppress(Exception):
            diff = (
                ct.replace(microsecond=0)
                + dt.timedelta(seconds=1)
                - timezone.localtime()
            ).total_seconds()
            time.sleep(diff)


def save_initital_option_snapshot(underlying, columns, websocket_id="1"):
    cache.set(
        f"{underlying}_{websocket_id}_SNAPSHOT_5SEC", pd.DataFrame(columns=columns)
    )

    cache.set(
        f"LIVE_{underlying}_{websocket_id}_PCR",
        pd.DataFrame(
            columns=[
                "timestamp",
                "pe_total_oi",
                "ce_total_oi",
                "pcr",
                "strike",
                "ce_iv",
                "pe_iv",
                "total_iv",
                "ce_premium",
                "pe_premium",
                "total_premium",
            ]
        ),
    )


def save_option_snapshot(underlying, ct, columns, strike_diff, websocket_id=1):
    instruments = cache.get(
        f"{underlying}_{websocket_id}_OPTION_INSTRUMENTS", pd.DataFrame()
    )
    if not instruments.empty:
        ltp = cache.get(f"{underlying}_LTP")
        instruments["spot_price"] = ltp
        instruments["timestamp"] = ct.replace(microsecond=0)
        instruments["time_left"] = (
            (instruments["expiry"] - instruments["timestamp"]).dt.total_seconds()
            / 86400
        ) / 365
        (
            instruments["sigma"],
            instruments["delta"],
            instruments["theta"],
            instruments["gamma"],
            instruments["vega"],
        ) = np.vectorize(caclulate_option_greeks)(
            instruments["last_price"],
            instruments["spot_price"],
            instruments["strike"],
            instruments["time_left"],
            0.10,
            instruments["option_type"],
        )
        instruments["atm"] = (instruments["spot_price"] / strike_diff).round(
            0
        ) * strike_diff
        # snapshot_df = cache.get(
        #     f"{underlying}_{websocket_id}_SNAPSHOT_5SEC", pd.DataFrame(columns=columns)
        # )
        # snapshot_df = pd.concat([snapshot_df, instruments[columns]], ignore_index=True)

        pe_total_oi = int(instruments[instruments["option_type"] == "PE"].oi.sum())
        ce_total_oi = int(instruments[instruments["option_type"] == "CE"].oi.sum())

        live_pcr = cache.get(
            f"LIVE_{underlying}_{websocket_id}_PCR",
            pd.DataFrame(columns=["timestamp", "pe_total_oi", "ce_total_oi", "pcr"]),
        )

        atm = float(round(ltp / strike_diff) * strike_diff)
        ce = instruments[
            (instruments["option_type"] == "CE") & (instruments["strike"] == atm)
        ].iloc[0]
        pe = instruments[
            (instruments["option_type"] == "PE") & (instruments["strike"] == atm)
        ].iloc[0]
        ce_iv = ce.sigma
        pe_iv = pe.sigma
        ce_premium = ce.last_price
        pe_premium = pe.last_price

        df = pd.DataFrame(
            [
                {
                    "timestamp": ct,
                    "pe_total_oi": pe_total_oi,
                    "ce_total_oi": ce_total_oi,
                    "pcr": pe_total_oi / ce_total_oi if ce_total_oi > 0 else np.inf,
                    "strike": atm,
                    "ce_iv": ce_iv,
                    "pe_iv": pe_iv,
                    "total_iv": ce_iv + pe_iv,
                    "ce_premium": ce_premium,
                    "pe_premium": pe_premium,
                    "total_premium": round(ce_premium + pe_premium, 2),
                }
            ]
        )

        # cache.set(f"{underlying}_{websocket_id}_SNAPSHOT_5SEC", snapshot_df)
        cache.set(
            f"LIVE_{underlying}_{websocket_id}_PCR",
            pd.concat([live_pcr, df], ignore_index=True),
        )


def save_option_snapshot_every_five_seconds():
    if HolidayModel.objects.filter(date=timezone.localdate()).exists():
        return

    columns = [
        "timestamp",
        "kotak_neo_instrument_token",
        "kite_instrument_token",
        "tradingsymbol",
        "expiry",
        "strike",
        "option_type",
        "last_price",
        "exchange_timestamp",
        "last_trade_time",
        "oi",
        "spot_price",
        "atm",
        "sigma",
        "delta",
    ]

    weboscket_ids = WEBSOCKET_IDS
    underlyings = UNDERLYINGS
    option_strikes = [float(i) for i in UNDERLYING_STRIKES]
    underlyings_strikes_map = list(zip(underlyings, option_strikes))

    # for weboscket_id in weboscket_ids:
    #     for underlying in underlyings:
    #         save_initital_option_snapshot(
    #             underlying=underlying,
    #             columns=columns,
    #             websocket_id=weboscket_id,
    #         )
    print(timezone.localtime().time() < dt.time(9, 15, 4))
    if timezone.localtime().time() < dt.time(9, 15, 4):
        ct = timezone.localtime()
        time.sleep(
            (
                ct.replace(hour=9, minute=15, second=4, microsecond=0) - ct
            ).total_seconds()
        )
    else:
        ct = timezone.localtime()
        if (ct + dt.timedelta(seconds=1)).second % 5 == 0:
            diff = (
                ct.replace(microsecond=0)
                + dt.timedelta(seconds=9)
                - timezone.localtime()
            ).total_seconds()
        else:
            diff = (
                ct.replace(second=((ct.second // 5) * 5), microsecond=0)
                + dt.timedelta(seconds=4)
                - timezone.localtime()
            ).total_seconds()

        with contextlib.suppress(Exception):
            time.sleep(diff)

    while True:
        ct = timezone.localtime().replace(microsecond=0)
        if ct.time() >= dt.time(15, 30):
            break

        for weboscket_id in weboscket_ids:
            for underlying, strike_diff in underlyings_strikes_map:
                save_option_snapshot(
                    underlying=underlying,
                    ct=ct,
                    columns=columns,
                    strike_diff=strike_diff,
                    websocket_id=weboscket_id,
                )

        if (ct + dt.timedelta(seconds=1)).second % 5 == 0:
            diff = (
                ct.replace(second=((ct.second // 5) * 5), microsecond=0)
                + dt.timedelta(seconds=9)
                - timezone.localtime()
            ).total_seconds()
        else:
            diff = (
                ct.replace(second=((ct.second // 5) * 5), microsecond=0)
                + dt.timedelta(seconds=4)
                - timezone.localtime()
            ).total_seconds()

        with contextlib.suppress(Exception):
            time.sleep(diff)


def option_calculation_and_snapshot():
    if HolidayModel.objects.filter(date=timezone.localdate()).exists():
        return

    tz = timezone.get_current_timezone()

    option_live_greeks_thread = threading.Thread(target=calculate_live_option_greeks)
    option_save_snapshot_every_five_second_thread = threading.Thread(
        target=save_option_snapshot_every_five_seconds
    )

    option_live_greeks_thread.daemon = True
    option_save_snapshot_every_five_second_thread.daemon = True

    option_live_greeks_thread.start()
    option_save_snapshot_every_five_second_thread.start()

    exit_time = parse(f"{dt.date.today()} 15:31:00").replace(tzinfo=tz)
    ct = timezone.localtime()

    if ct <= exit_time:
        time.sleep((exit_time - ct).total_seconds())

    return True
