import asyncio

import pandas as pd
from django.core.cache import cache

from apps.integration.models import KiteApi as KiteApiModel
from apps.integration.models import KotakNeoApi as KotakNeoApiModel
from apps.integration.utils.broker_login import KiteLoginApi, KotakNeoLoginApi
from trading.settings import UNDERLYINGS, WEBSOCKET_IDS


async def get_kite_instruments() -> pd.DataFrame:
    if kite := await KiteApiModel.objects.filter(
        broker_api__broker="kite", broker_api__is_active=True
    ).afirst():
        kite_api = KiteLoginApi(user_id=kite.user_id)
        df = pd.DataFrame(await kite_api.instruments(kite.enctoken))
        df = df.rename(columns={"instrument_token": "kite_instrument_token"})
        return df

    return pd.DataFrame()


async def get_kotak_neo_instruments() -> pd.DataFrame:
    if kotak_neo := await KotakNeoApiModel.objects.filter(
        broker_api__broker="kotak_neo", broker_api__is_active=True
    ).afirst():
        kotak_neo_api = KotakNeoLoginApi(
            neo_fin_key=kotak_neo.neo_fin_key,
            consumer_key=kotak_neo.decrypt_consumer_key(),
            consumer_secret=kotak_neo.decrypt_consumer_secret(),
            access_token=kotak_neo.access_token,
            auth=kotak_neo.auth,
            sid=kotak_neo.sid,
            hs_server_id=kotak_neo.hs_server_id,
        )
        df = pd.DataFrame(await kotak_neo_api.instruments())
        df = df.rename(columns={"instrument_token": "kotak_neo_instrument_token"})
        return df[
            [
                "kotak_neo_instrument_token",
                "tradingsymbol",
                "max_order_size",
            ]
        ].copy()

    return pd.DataFrame()


async def map_option_instruments() -> list[dict]:
    (
        kite_instruments,
        kotak_neo_instruments,
    ) = await asyncio.gather(
        get_kite_instruments(),
        get_kotak_neo_instruments(),
    )

    df = pd.merge(kite_instruments, kotak_neo_instruments, on="tradingsymbol")
    df = df[
        (df["name"].isin(UNDERLYINGS)) & (df["option_type"].isin(["CE", "PE"]))
    ].reset_index(drop=True)

    df = df[
        [
            "kite_instrument_token",
            "kotak_neo_instrument_token",
            "tradingsymbol",
            "exchange",
            "name",
            "expiry",
            "option_type",
            "strike",
            "tick_size",
            "lot_size",
            "max_order_size",
        ]
    ].copy()
    df = df.rename(columns={"name": "underlying"})

    final_df = pd.DataFrame()
    websocket_ids_len = len(WEBSOCKET_IDS)

    for underlying in UNDERLYINGS:
        df_buffer = df[(df["underlying"] == underlying)].reset_index(drop=True)
        expiries = sorted(df_buffer["expiry"].unique())[:websocket_ids_len]
        df_buffer = df_buffer[df_buffer["expiry"].isin(expiries)].sort_values(
            [
                "expiry",
                "strike",
                "option_type",
            ],
            ignore_index=True,
        )
        websocket_id_expiry_map = dict(zip(expiries, WEBSOCKET_IDS))
        underlying_expiry_map = dict(zip(WEBSOCKET_IDS, expiries))
        df_buffer["websocket_id"] = df_buffer["expiry"].map(websocket_id_expiry_map)
        final_df = pd.concat([final_df, df_buffer], ignore_index=True)
        cache.set(f"{underlying}_EXPIRY_MAP", underlying_expiry_map)

    cache.set("OPTION_INSTRUMENTS", final_df)

    return final_df.to_dict(orient="records")
