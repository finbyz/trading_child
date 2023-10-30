import asyncio
import itertools
import json
import traceback

import pandas as pd
from aiohttp import ClientSession
from django.utils import timezone

from apps.integration.utils.operations import (
    convert_timestamp,
    get_option_instruments_row,
    get_option_ltp,
    quantity_split,
)


class KotakNeoApi(object):
    _PRICE_TYPE_REVERSE_MAP = {
        "L": "LIMIT",
        "M": "MARKET",
    }

    _TRANSACTION_TYPE_MAP = {
        "BUY": "B",
        "SELL": "S",
    }

    _TRANSACTION_TYPE_REVERSE_MAP = {
        "B": "BUY",
        "S": "SELL",
    }

    def __init__(
        self,
        users: list[dict],
        url: str = "https://gw-napi.kotaksecurities.com",
    ):
        self.users = users
        self.url = url

    async def place_order_using_user(
        self,
        session: ClientSession,
        user: dict,
        row: pd.Series,
        transaction_type: str,
        expected_price: float,
        tag_prefix: str,
        quantity: str,
        product: str = "NRML",
        trigger_price: float = 0,
    ):
        data = {
            "jData": json.dumps(
                {
                    "am": "NO",
                    "dq": "0",
                    "es": "nse_fo",
                    "mp": "0",
                    "pc": product,
                    "pf": "N",
                    "pr": str(expected_price),
                    "pt": "L" if expected_price else "MKT",
                    "qt": str(quantity),
                    "rt": "DAY",
                    "tp": trigger_price,
                    "ts": row.tradingsymbol,
                    "tt": transaction_type,
                    # "ig": "tag",
                }
            )
        }

        response = await session.request(
            method="POST",
            url=f"{self.url}/Orders/2.0/quick/order/rule/ms/place",
            data=data,
            headers=user["headers"],
            params=user["query_params"],
        )

        resp = await response.json()

        if response.status == 429:
            await asyncio.sleep(0.25)
            return await self.place_order_using_user(
                session=session,
                user=user,
                row=row,
                transaction_type=transaction_type,
                expected_price=expected_price,
                tag_prefix=tag_prefix,
                quantity=quantity,
                product=product,
                trigger_price=trigger_price,
            )

        try:
            return {"order_id": resp["nOrdNo"]}
        except Exception as e:
            print(resp)
            raise e

    async def modify_order_using_user(
        self,
        session,
        user: dict,
        order_id: str,
        row: pd.Series,
        transaction_type: str,
        price: str,
        quantity: str,
        product: str = "NRML",
        trigger_price: str = "0",
    ):
        body_params = {
            "tk": str(row.kotak_neo_instrument_token),
            "mp": "0",
            "pc": product,
            "dd": "NA",
            "dq": "0",
            "vd": "DAY",
            "ts": row.tradingsymbol,
            "tt": transaction_type,
            "pr": str(price),
            "pt": "L" if price else "M",
            "fq": "0",
            "am": "NO",
            "tp": trigger_price,
            "qt": str(quantity),
            "no": order_id,
            "es": "nse_fo",
        }

        await session.request(
            method="POST",
            url=f"{self.url}/Orders/2.0/quick/order/vr/modify",
            data={"jData": json.dumps(body_params)},
            headers=user["headers"],
            params=user["query_params"],
        )

    async def get_option_order_history_using_user(
        self,
        session,
        user: dict,
        order_id: str,
    ):
        response = await session.request(
            method="POST",
            url=f"{self.url}/Orders/2.0/quick/order/history",
            data={
                "jData": json.dumps(
                    {
                        "nOrdNo": order_id,
                    }
                )
            },
            headers=user["headers"],
            params=user["query_params"],
        )

        resp = await response.json()

        if response.status == 429:
            await asyncio.sleep(0.5)
            return await self.get_option_order_history_using_user(
                session=session,
                user=user,
                order_id=order_id,
            )

        try:
            return resp["data"][0]
        except Exception as e:
            print(resp)
            raise e

    async def option_place_and_chase_order_using_user(
        self,
        session: ClientSession,
        user: dict,
        current_time,
        row: pd.Series,
        transaction_type: str,
        expected_price: float,
        tag_prefix: str,
        quantity: str,
        product: str = "NRML",
        trigger_price: float = 0,
        slippage=5,
        max_price=0,
    ):
        try:
            order = await self.place_order_using_user(
                session=session,
                user=user,
                row=row,
                transaction_type=transaction_type,
                expected_price=expected_price,
                tag_prefix=tag_prefix,
                quantity=quantity,
                product=product,
                trigger_price=trigger_price,
            )

            await asyncio.sleep(0.02)

            order_report = await self.get_option_order_history_using_user(
                session=session,
                user=user,
                order_id=order["order_id"],
            )

            while True:
                if order_report["ordSt"] in ["rejected", "cancelled", "complete"]:
                    break

                modify_quantity = order_report["qty"] - order_report["fldQty"]
                modify_price = get_option_ltp(
                    symbol=row.underlying,
                    tradingsymbol=row.tradingsymbol,
                    websocket_id=row.websocket_id,
                )
                modify_price = (
                    max(modify_price - slippage, 0.05)
                    if transaction_type == "S"
                    else modify_price + slippage
                )

                if max_price:
                    modify_price = (
                        max(modify_price, max_price)
                        if transaction_type == "S"
                        else min(modify_price, max_price)
                    )

                await self.modify_order_using_user(
                    session=session,
                    user=user,
                    order_id=order["order_id"],
                    row=row,
                    transaction_type=transaction_type,
                    price=modify_price,
                    quantity=modify_quantity,
                    product=product,
                    trigger_price=trigger_price,
                )

                await asyncio.sleep(0.25)
                order_report = await self.get_option_order_history_using_user(
                    session=session,
                    user=user,
                    order_id=order["order_id"],
                )

            return {
                "username": user["username"],
                "order_id": order["order_id"],
                "status": order_report["ordSt"],
                "expected_price": expected_price,
                "expected_time": current_time,
                "excepted_quantity": quantity,
            }
        except Exception as e:
            print(e)
            traceback.print_exc()

    async def option_place_and_chase_order(
        self,
        symbol,
        tradingsymbol,
        transaction_type,
        expected_price,
        quantity_map: dict,
        tag_prefix: str,
        websocket_id: str = "1",
    ):
        current_time = timezone.localtime()
        row = get_option_instruments_row(symbol, tradingsymbol, websocket_id)
        max_order_size = int(row.max_order_size)

        async with ClientSession() as session:
            return await asyncio.gather(
                *[
                    self.option_place_and_chase_order_using_user(
                        session=session,
                        user=user,
                        current_time=current_time,
                        row=row,
                        transaction_type=self._TRANSACTION_TYPE_MAP[transaction_type],
                        expected_price=expected_price,
                        quantity=quantity,
                        tag_prefix=tag_prefix,
                    )
                    for user in self.users
                    for quantity in quantity_split(
                        quantity_map.get(user["username"], 0),
                        max_order_size,
                    )
                    if quantity_map.get(user["username"], 0) != 0
                ]
            )

    async def positions_using_user(self, session, user: dict):
        response = await session.request(
            method="GET",
            url=f"{self.url}/Orders/2.0/quick/user/positions",
            headers=user["headers"],
            params=user["query_params"],
        )

        resp = await response.json()

        if resp.get("stat") == "Ok":
            data = []

            for row in resp["data"]:
                dct = {
                    "username": user["username"],
                    "broker": "kotak_neo",
                    "kotak_neo_instrument_token": row["tok"],
                    "tradingsymbol": row["trdSym"],
                    "symbol": row["sym"],
                    "buy_qty": int(row["flBuyQty"]) + int(row["cfBuyQty"]),
                    "sell_qty": int(row["flSellQty"]) + int(row["cfSellQty"]),
                    "buy_value": float(row["buyAmt"]) + float(row["cfBuyAmt"]),
                    "sell_value": float(row["sellAmt"]) + float(row["cfSellAmt"]),
                }
                dct["net_qty"] = dct["buy_qty"] - dct["sell_qty"]

                data.append(dct)

            return data
        elif resp.get("errMsg") == "No Data":
            return []

        print(user["username"], response.status, resp)
        return []

    async def postions(self):
        async with ClientSession() as session:
            return list(
                itertools.chain.from_iterable(
                    await asyncio.gather(
                        *[
                            self.positions_using_user(session=session, user=user)
                            for user in self.users
                        ]
                    )
                )
            )

    async def order_report_using_user(self, session, user: dict):
        response = await session.request(
            method="GET",
            url=f"{self.url}/Orders/2.0/quick/user/orders",
            headers=user["headers"],
            params=user["query_params"],
        )

        resp = await response.json()

        if resp.get("stat") == "Ok":
            data = []

            for row in resp["data"]:
                data.append(
                    {
                        "username": user["username"],
                        "order_id": row["nOrdNo"],
                        "excahange_order_id": row["exOrdId"],
                        "kotak_neo_instrument_token": row["tok"],
                        "tradingsymbol": row["trdSym"],
                        "symbol": row["sym"],
                        "product": row["prod"],
                        "status": row["ordSt"].upper(),
                        "transaction_type": self._TRANSACTION_TYPE_REVERSE_MAP[
                            row["trnsTp"]
                        ],
                        "price": float(row["prc"]),
                        "average_price": float(row["avgPrc"]),
                        "quantity": int(row["qty"]),
                        "filled_quantity": int(row["fldQty"]),
                        "pending_quantity": int(row.get("unFldSz", 0)),
                        "cancelled_quantity": int(row.get("cnclQty", 0)),
                        "order_timestamp": convert_timestamp(row["ordDtTm"]),
                        "price_type": self._PRICE_TYPE_REVERSE_MAP.get(
                            row["prcTp"], row["prcTp"]
                        ),
                        "tag": row["GuiOrdId"],
                    }
                )
            return data
        elif resp.get("errMsg") == "No Data":
            return []

        print(response.status, resp)
        return []

    async def order_report(self):
        async with ClientSession() as session:
            return list(
                itertools.chain.from_iterable(
                    await asyncio.gather(
                        *[
                            self.order_report_using_user(session=session, user=user)
                            for user in self.users
                        ]
                    )
                )
            )

    async def trade_report_using_user(self, session, user: dict):
        response = await session.request(
            method="GET",
            url=f"{self.url}/Orders/2.0/quick/user/trades",
            headers=user["headers"],
            params=user["query_params"],
        )

        resp = await response.json()

        if resp.get("stat") == "Ok":
            data = []

            for row in resp["data"]:
                data.append(
                    {
                        "username": user["username"],
                        "order_id": row["nOrdNo"],
                        "kotak_neo_instrument_token": row["tok"],
                        "tradingsymbol": row["trdSym"],
                        "symbol": row["sym"],
                        "product": row["prod"],
                        "transaction_type": self._TRANSACTION_TYPE_REVERSE_MAP[
                            row["trnsTp"]
                        ],
                        "average_price": float(row["avgPrc"]),
                        "filled_quantity": int(row["fldQty"]),
                        "tag": row["GuiOrdId"],
                        "exchange_timestamp": convert_timestamp(row["exTm"]),
                        "filled_timestamp": convert_timestamp(
                            row["flDt"] + " " + row["flTm"]
                        ),
                    }
                )

            return data
        elif resp.get("errMsg") == "No Data":
            return []

        print(response.status, resp)
        return []

    async def trade_report(self):
        async with ClientSession() as session:
            return list(
                itertools.chain.from_iterable(
                    await asyncio.gather(
                        *[
                            self.trade_report_using_user(session=session, user=user)
                            for user in self.users
                        ]
                    )
                )
            )

    async def margin_using_user(self, session, user: dict):
        response = await session.request(
            method="POST",
            url=f"{self.url}/Orders/2.0/quick/user/limits",
            data={"jData": json.dumps({"seg": "ALL", "exch": "ALL", "prod": "ALL"})},
            headers=user["headers"],
            params=user["query_params"],
        )

        resp = await response.json()

        try:
            return {
                "username": user["username"],
                "margin": float(resp["Net"]) + float(resp["PremiumPrsnt"]),
            }
        except Exception:
            return {
                "username": user["username"],
                "margin": 0,
            }

    async def margin(self):
        async with ClientSession() as session:
            return await asyncio.gather(
                *[
                    self.margin_using_user(session=session, user=user)
                    for user in self.users
                ]
            )
