import asyncio
import traceback

import pandas as pd
from django.contrib.auth import get_user_model

from apps.integration.models import KotakNeoApi as KotakNeoApiModel
from apps.integration.utils import get_option_instruments, get_option_ltp
from apps.integration.utils.broker.dummy import DummyApi
from apps.integration.utils.broker.kotak_neo import KotakNeoApi
from apps.trade.utils.utils_quantity_mistmatch import quantity_mistmatch
from apps.trade.utils.utils_update_position import update_positions

User = get_user_model()


async def place_dummy_order(
    symbol,
    transaction_type,
    symbol_quantity_map: dict,
    users,
):
    dummyapi = DummyApi(users=list(User.objects.filter(username__in=users)))

    await asyncio.gather(
        *[
            dummyapi.option_place_and_chase_order(
                symbol=symbol,
                tradingsymbol=tradingsymbol,
                transaction_type=transaction_type,
                price=get_option_ltp(
                    symbol=symbol,
                    tradingsymbol=tradingsymbol,
                    websocket_id=websocket_id,
                ),
                quantity_map=quantity_map,
                tag_prefix="A",
                websocket_id=websocket_id,
            )
            for (
                tradingsymbol,
                websocket_id,
            ), quantity_map in symbol_quantity_map.items()
        ]
    )


async def place_kotak_neo_order(
    symbol,
    transaction_type,
    symbol_quantity_map: dict,
    users,
    slippage=5,
):
    users = [
        {
            "username": row.broker_api.user.username,
            "headers": {
                "Authorization": f"Bearer {row.access_token}",
                "Sid": row.sid,
                "Auth": row.auth,
                "neo-fin-key": row.neo_fin_key,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            "query_params": {"sId": row.hs_server_id},
        }
        for row in KotakNeoApiModel.objects.filter(broker_api__user__username__in=users)
    ]
    knapi = KotakNeoApi(users=users)

    await asyncio.gather(
        *[
            knapi.option_place_and_chase_order(
                symbol=symbol,
                tradingsymbol=tradingsymbol,
                transaction_type=transaction_type,
                expected_price=max(
                    0,
                    get_option_ltp(
                        symbol=symbol,
                        tradingsymbol=tradingsymbol,
                        websocket_id=websocket_id,
                    )
                    - slippage,
                )
                if transaction_type == "BUY"
                else get_option_ltp(
                    symbol=symbol,
                    tradingsymbol=tradingsymbol,
                    websocket_id=websocket_id,
                )
                + slippage,
                quantity_map=quantity_map,
                tag_prefix="A",
                websocket_id=websocket_id,
            )
            for (
                tradingsymbol,
                websocket_id,
            ), quantity_map in symbol_quantity_map.items()
        ]
    )


async def place_orders(
    broker,
    symbol,
    transaction_type,
    symbol_quantity_map: dict,
    users,
    slippage=5,
):
    match broker:
        case "kotak_neo":
            await place_kotak_neo_order(
                symbol=symbol,
                transaction_type=transaction_type,
                symbol_quantity_map=symbol_quantity_map,
                users=users,
                slippage=slippage,
            )
        case "dummy":
            await place_dummy_order(
                symbol=symbol,
                transaction_type=transaction_type,
                symbol_quantity_map=symbol_quantity_map,
                users=users,
            )


async def adjust_positions(
    symbol: str,
    broker: str | None = None,
    username: str | None = None,
    websocket_ids: list[str] | None = None,
):
    print("here")
    try:
        await update_positions(broker=broker)
    except Exception as e:
        traceback.print_exc()

    _, df = await quantity_mistmatch(
        symbol=symbol,
        websocket_ids=websocket_ids,
        broker=broker,
    )

    if df.empty:
        return

    if broker:
        df = df[df["broker"].isin(["dummy", broker])].copy()

    if username:
        df = df[df["username"] == username].copy()

    if df.empty:
        return

    instruments = get_option_instruments(symbol=symbol, websocket_ids=websocket_ids)

    df["difference_qty"] = df["expected_qty"] - df["net_qty"]

    df = pd.merge(
        df, instruments[["tradingsymbol", "websocket_id"]], on="tradingsymbol"
    )

    df = df[df["tradingsymbol"].isin(instruments["tradingsymbol"].unique())]

    df = df[df["difference_qty"] != 0].reset_index(drop=True)
    buy = df[df["difference_qty"] > 0].copy()
    sell = df[df["difference_qty"] < 0].copy()

    if not buy.empty:
        buy_order = []
        for broker, broker_buy in buy.groupby("broker"):
            symbol_quantity_map = {}
            kotak_neo_users = broker_buy.username.unique()

            for tradingsymbol, df_buffer in broker_buy.groupby("tradingsymbol"):
                symbol_quantity_map[(tradingsymbol, df_buffer.iloc[0].websocket_id)] = {
                    row["username"]: int(row["difference_qty"])
                    for _, row in df_buffer.iterrows()
                }

            buy_order.append(
                place_orders(
                    broker,
                    symbol,
                    "BUY",
                    symbol_quantity_map,
                    kotak_neo_users,
                )
            )

        await asyncio.gather(*buy_order)

    if not sell.empty:
        sell_order = []
        for broker, broker_sell in sell.groupby("broker"):
            symbol_quantity_map = {}
            kotak_neo_users = broker_sell.username.unique()

            for tradingsymbol, df_buffer in broker_sell.groupby("tradingsymbol"):
                symbol_quantity_map[(tradingsymbol, df_buffer.iloc[0].websocket_id)] = {
                    row["username"]: abs(int(row["difference_qty"]))
                    for _, row in df_buffer.iterrows()
                }

            sell_order.append(
                place_orders(
                    broker,
                    symbol,
                    "SELL",
                    symbol_quantity_map,
                    kotak_neo_users,
                )
            )

        await asyncio.gather(*sell_order)

    if not buy.empty or not sell.empty:
        try:
            await update_positions(broker=broker)
        except Exception as e:
            traceback.print_exc()
