import asyncio
import itertools
import random
import string

import numpy as np
from django.utils import timezone
from django_pandas.io import read_frame

from apps.integration.utils.operations import (
    get_option_instruments_row,
    get_option_ltp,
    quantity_split,
)
from apps.trade.models import DummyOrder as DummyOrderModel


class DummyApi(object):
    def __init__(
        self,
        users: list[dict],
    ):
        self.users = users

    def generate_token(self, n=7):
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))

    async def option_place_and_chase_order_using_user(
        self,
        current_time,
        user,
        row,
        quantity,
        transaction_type,
        price,
        tag_prefix,
    ):
        while True:
            order_id = self.generate_token(12)
            if not DummyOrderModel.objects.filter(order_id=order_id).exists():
                break

        obj = DummyOrderModel.objects.create(
            user=user,
            tradingsymbol=row.tradingsymbol,
            order_id=order_id,
            order_timestamp=timezone.localtime(),
            quantity=quantity,
            transaction_type=transaction_type,
            price=price,
            tag=f"{tag_prefix}_{self.generate_token(7)}",
        )

        return {
            "username": user.username,
            "order_id": order_id,
            "status": obj.status,
            "expected_price": price,
            "expected_time": current_time,
            "excepted_quantity": quantity,
        }

    async def option_place_and_chase_order(
        self,
        symbol,
        tradingsymbol,
        transaction_type,
        price,
        quantity_map: dict,
        tag_prefix: str,
        websocket_id: str = "1",
    ):
        current_time = timezone.localtime()
        row = get_option_instruments_row(symbol, tradingsymbol, websocket_id)
        max_order_size = int(row.max_order_size)

        return await asyncio.gather(
            *[
                self.option_place_and_chase_order_using_user(
                    user=user,
                    current_time=current_time,
                    row=row,
                    transaction_type=transaction_type,
                    price=price,
                    quantity=quantity,
                    tag_prefix=tag_prefix,
                )
                for user in self.users
                for quantity in quantity_split(
                    quantity_map[user.username],
                    max_order_size,
                )
                if quantity_map.get(user.username, 0)
            ]
        )

    def apply_slippage(self, rate, slippage=4):
        return round(rate * abs((rate ** (1 / ((max(rate, 0.05)) * slippage))) - 1), 2)

    async def positions_using_user(self, user):
        qs = DummyOrderModel.objects.filter(
            user=user,
            order_timestamp__date=timezone.localdate(),
        )
        df = read_frame(qs)
        df["price"] = df["price"].astype(float)
        df["slippage"] = df["price"].apply(self.apply_slippage)

        df["price"] = np.where(
            df["transaction_type"] == "BUY",
            df["price"] + df["slippage"],
            df["price"] - df["slippage"],
        )
        df["total_value"] = df["price"] * df["quantity"]
        df = (
            df.groupby(["tradingsymbol", "transaction_type"])
            .agg(
                {
                    "quantity": "sum",
                    "price": "mean",
                    "total_value": "sum",
                }
            )
            .reset_index()
        )

        buy_df = df[df["transaction_type"] == "BUY"]
        sell_df = df[df["transaction_type"] == "SELL"]

        buy_df = buy_df.rename(
            columns={
                "quantity": "buy_qty",
                "price": "buy_avg",
                "total_value": "buy_value",
            }
        )
        buy_df.drop(columns=["transaction_type"], inplace=True)
        sell_df = sell_df.rename(
            columns={
                "quantity": "sell_qty",
                "price": "sell_avg",
                "total_value": "sell_value",
            }
        )
        sell_df.drop(columns=["transaction_type"], inplace=True)

        df = buy_df.merge(sell_df, on="tradingsymbol", how="outer").fillna(0)
        df["net_qty"] = df["buy_qty"] - df["sell_qty"]

        df["username"] = user.username
        df["broker"] = "dummy"

        df = df[
            [
                "username",
                "broker",
                "tradingsymbol",
                "sell_value",
                "buy_value",
                "net_qty",
            ]
        ]

        return df.to_dict("records")

    async def positions(self):
        return list(
            itertools.chain.from_iterable(
                await asyncio.gather(
                    *[self.positions_using_user(user=user) for user in self.users]
                )
            )
        )
