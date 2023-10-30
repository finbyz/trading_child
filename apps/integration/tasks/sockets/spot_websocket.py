import datetime as dt
from typing import Any

from django.core.cache import cache

from apps.integration.tasks.sockets.get_kws_object import get_kws_object
from apps.integration.utils.kiteticker import KiteExtTicker, KiteTicker
from trading.settings import UNDERLYING_TOKENS_MAP


def on_connect(ws: KiteTicker | KiteExtTicker, response: Any):
    ws.subscribe(ws.instrument_tokens)
    ws.set_mode(ws.MODE_FULL, ws.instrument_tokens)


def on_ticks(ws: KiteTicker | KiteExtTicker, ticks: list[dict]):
    for i in ticks:
        cache.set(
            f"{UNDERLYING_TOKENS_MAP[i['instrument_token']]}_LTP", i["last_price"]
        )

    if dt.datetime.now().time() > dt.time(15, 30):
        ws.unsubscribe(ws.instrument_tokens)
        ws.close()


def on_close(ws: KiteTicker | KiteExtTicker, code: int, reason: str):
    if not code and not reason:
        ws.stop()


def run_spot_websocket():
    kws: KiteTicker | KiteExtTicker = get_kws_object()
    kws.instrument_tokens: list[int] = [257801, 260105, 256265]
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close

    kws.connect(threaded=True)
