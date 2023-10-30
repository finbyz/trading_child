import asyncio
import datetime as dt

import numpy as np
import pandas as pd
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache
from django.utils import timezone

from apps.integration.utils import get_option_greeks_instruments
from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel
from apps.trade.models import (
    DeployedOptionStrategyUser as DeployedOptionStrategyUserModel,
)
from apps.trade.utils import calculate_pnl, get_user_margin, quantity_mistmatch
from apps.trade.utils.utils_get_dummy_points import get_dummy_points


class DeployedOptionStrategyPositionConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        if self.scope["user"].is_anonymous:
            await self.close(code=4004)
            return
        self.pk = self.scope["url_route"]["kwargs"]["pk"]

        deployed_option_strategy = await DeployedOptionStrategyModel.objects.filter(
            pk=self.pk
        ).afirst()

        if not deployed_option_strategy:
            await self.close(code=1011)
            return

        await self.channel_layer.group_add(
            str(self.pk),
            self.channel_name,
        )

        self.websocket_ids = deployed_option_strategy.websocket_ids.split(",")
        self.symbol = deployed_option_strategy.instrument.symbol

        if deployed_option_strategy.strategy.strategy_type in (
            "single_straddle_strangle",
            "delta_management",
        ):
            while True:
                await self.send_strategy_position_data()
                await asyncio.sleep(1)

    async def send_strategy_position_data(self, *args, **kwargs):
        if cache.get("DEPLOYED_STRATEGIES", {}).get(str(self.pk)):
            tradingsymbols = cache.get(f"TRADINGSYMBOLS_{self.pk}", []).copy()
            insturments = get_option_greeks_instruments(
                symbol=self.symbol,
                websocket_ids=self.websocket_ids,
            )
            for idx, row in enumerate(tradingsymbols):
                ce_strike = pe_strike = None
                ce_delta = pe_delta = 0
                ce_price = pe_price = 0

                if row["ce_tradingsymbol"]:
                    ce = insturments[
                        insturments["tradingsymbol"] == row["ce_tradingsymbol"]
                    ].iloc[0]
                    ce_strike = ce.strike
                    ce_delta = ce["delta"]
                    ce_price = ce["last_price"]

                if row["pe_tradingsymbol"]:
                    pe = insturments[
                        insturments["tradingsymbol"] == row["pe_tradingsymbol"]
                    ].iloc[0]
                    pe_strike = pe.strike
                    pe_delta = pe["delta"]
                    pe_price = pe["last_price"]

                row["ce_strike"] = ce_strike
                row["ce_delta"] = ce_delta
                row["ce_price"] = ce_price
                row["pe_strike"] = pe_strike
                row["pe_delta"] = pe_delta
                row["pe_price"] = pe_price
                row["idx"] = idx
                row["one_side_exit_hold"] = cache.get(
                    f"ONE_SIDE_EXIT_HOLD_{self.pk}_{idx}", 0
                )
                row["strategy_name"] = row.get("strategy_name", "")

            await self.send_json(tradingsymbols)


class LivePnlStrategyConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()
        if self.scope["user"].is_anonymous:
            await self.close(code=4004)
            return
        self.pk = self.scope["url_route"]["kwargs"]["pk"]

        deployed_option_strategy = await DeployedOptionStrategyModel.objects.aget(
            pk=self.pk
        )

        self.symbol = deployed_option_strategy.instrument.symbol
        self.websocket_ids = deployed_option_strategy.websocket_ids.split(",")
        self.broker = deployed_option_strategy.broker

        initial_margin_df = pd.DataFrame(
            cache.get("USERS_MARGIN", []),
            columns=["username", "broker", "initial_margin"],
        )

        self.quantity_df = pd.DataFrame(
            [
                {
                    "broker_api": str(row.broker_api),
                    "alternate_broker_api": str(row.alternate_broker_api or ""),
                    "quantity": (row.parent.lot_size * row.lots),
                    "username": row.broker_api.user.username,
                    "broker": row.broker_api.broker,
                    "alternate_username": row.alternate_broker_api.user.username
                    if row.alternate_broker_api
                    else "",
                    "alternate_broker": row.alternate_broker_api.broker
                    if row.alternate_broker_api
                    else "",
                }
                async for row in DeployedOptionStrategyUserModel.objects.filter(
                    parent__id=self.pk
                ).order_by("order_seq")
            ]
        )
        self.quantity_df = pd.merge(
            self.quantity_df, initial_margin_df, on=["username", "broker"], how="left"
        )
        self.quantity_df["initial_margin"] = self.quantity_df["initial_margin"].fillna(
            0.0
        )
        self.quantity_df["index"] = self.quantity_df.index + 1
        await self.return_pnl()

    async def disconnect(self, close_code):
        pass

    async def return_pnl(self):
        while True:
            margin_df = await get_user_margin(broker=self.broker)
            pnl_df, quantity_mismatch_df = await quantity_mistmatch(
                symbol=self.symbol,
                websocket_ids=self.websocket_ids,
                broker=self.broker,
            )

            quantity_mismatch_df = quantity_mismatch_df.groupby(
                ["username", "broker"]
            ).agg({"mismatch": "max"})

            if not margin_df.empty:
                df = pd.merge(
                    self.quantity_df, margin_df, on=["username", "broker"], how="left"
                )
            else:
                df = self.quantity_df.copy()
                df["margin"] = 0

            df["margin"] = np.where(
                df["broker"] == "dummy", df["quantity"] * 7000, df["margin"]
            )

            if not pnl_df.empty:
                pnl_df = (
                    pnl_df.groupby(["username", "broker"])
                    .agg(
                        {
                            "pnl": "sum",
                            "ce_buy_qty": "sum",
                            "ce_sell_qty": "sum",
                            "pe_buy_qty": "sum",
                            "pe_sell_qty": "sum",
                        }
                    )
                    .reset_index()
                )
                df = pd.merge(df, pnl_df, on=["username", "broker"], how="left")
            else:
                df["pnl"] = 0
                df["ce_buy_qty"] = 0
                df["ce_sell_qty"] = 0
                df["pe_buy_qty"] = 0
                df["pe_sell_qty"] = 0

            df = pd.merge(
                df, quantity_mismatch_df, on=["username", "broker"], how="left"
            ).fillna(0)

            df["in_cache"] = df["username"].apply(
                lambda x: x
                in [
                    x["user"].username
                    for x in cache.get("DEPLOYED_STRATEGIES", {})
                    .get(str(self.pk), {})
                    .get("user_params", [])
                ]
            )

            df["pnl_points"] = df["pnl"] / df["quantity"]
            df["initial_margin"] = np.where(
                df["initial_margin"] == 0, df["margin"], df["initial_margin"]
            )
            df.drop_duplicates(["username", "broker"], inplace=True)

            await self.send_json(df.to_dict("records"))
            await asyncio.sleep(1)


class StopLossDifference(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()

        if self.scope["user"].is_anonymous:
            await self.close(code=4004)
            return
        self.pk = self.scope["url_route"]["kwargs"]["pk"]

        deployed_option_strategy = await DeployedOptionStrategyModel.objects.filter(
            pk=self.pk
        ).afirst()

        if not deployed_option_strategy:
            await self.close(code=1011)
            return
        entry_time = deployed_option_strategy.options.get(
            "entry_time", dt.time(9, 15, 59)
        )

        while True:
            dummy_pts = await get_dummy_points(self.pk)
            stop_loss = cache.get("OPTION_STRATEGIES_STOP_LOSSES", {}).get(self.pk, 0)
            entry_time = cache.get("OPTION_STRATEGIES_ENTRY_TIMES", {}).get(
                self.pk, entry_time
            )
            await self.send_json(
                {
                    "entry_time": str(entry_time),
                    "stop_loss": stop_loss,
                    "stop_loss_difference": round(dummy_pts + stop_loss),
                }
            )
            await asyncio.sleep(1)
