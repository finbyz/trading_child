import asyncio
import datetime as dt
import traceback

import pandas as pd
from colorama import Fore
from dateutil.parser import parse
from django.core.cache import cache
from django.utils import timezone

from apps.integration.utils import divide_and_list, get_option_greeks_instruments
from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel
from apps.trade.strategies import StrategyOrder
from apps.trade.utils import adjust_positions, update_positions


class Strategy(StrategyOrder):
    def __init__(
        self,
        strategy_id: int,
    ):
        super(Strategy, self).__init__(
            opt_strategy=DeployedOptionStrategyModel.objects.get(pk=strategy_id)
        )

        self.entry_time = parse(
            str(
                cache.get("OPTION_STRATEGIES_ENTRY_TIMES", {}).get(
                    self.strategy_id, self.options["entry_time"]
                )
            )
        ).time()
        self.exit_time = parse(self.options["exit_time"]).time()
        self.max_delta = self.options["max_delta"] / 100
        self.shift_min_delta = self.options["shift_min_delta"] / 100
        self.shift_max_delta = self.options["shift_max_delta"] / 100
        self.shift_min_delta_entry = self.options["shift_min_delta_entry"] / 100
        self.shift_max_delta_entry = self.options["shift_max_delta_entry"] / 100
        self.multiplier = self.options["multiplier"]
        self.point_difference = self.options["point_difference"]
        self.sigma_diff = self.options["sigma_diff"] / 100
        self.entry_sigma = self.options["entry_sigma"] / 100
        self.oneside_check_time = parse(self.options["oneside_check_time"]).time()
        self.expiry_check_time = parse(self.options["expiry_check_time"]).time()
        self.expiry_check_sigma_time = parse(
            self.options["expiry_check_sigma_time"]
        ).time()
        self.difference_list = [row * 12 for row in self.options["difference_list"]]

        self.skip_price = self.options["skip_price"]
        self.sleep_time = self.options["sleep_time"]
        self.websocket_id = self.websocket_ids[0]
        self.option_expiry_cache = f"{self.symbol}_EXPIRY_MAP"
        self.option_instrument_ltp_cache = f"{self.symbol}_LTP"

    async def place_entry_order(self, tradingsymbols):
        deployed_strategy = cache.get("DEPLOYED_STRATEGIES", {})

        if deployed_strategy.get(self.str_strategy_id, {}) and cache.get(
            self.strategy_tradingsymbol_cache
        ):
            return

        deployed_strategy[self.str_strategy_id] = {"user_params": self.user_params}
        cache.set("DEPLOYED_STRATEGIES", deployed_strategy)
        cache.set(self.strategy_tradingsymbol_cache, tradingsymbols)

        await adjust_positions(
            symbol=self.symbol,
            broker=self.broker,
            websocket_ids=self.websocket_ids,
        )

    async def place_exit_order(self):
        tradingsymbols = cache.get(self.strategy_tradingsymbol_cache, [])

        if not tradingsymbols:
            return

        cache.delete(self.strategy_tradingsymbol_cache)
        deployed_strategy = cache.get("DEPLOYED_STRATEGIES", {})
        del deployed_strategy[self.str_strategy_id]
        cache.set("DEPLOYED_STRATEGIES", deployed_strategy)

        await adjust_positions(
            symbol=self.symbol,
            broker=self.broker,
            websocket_ids=self.websocket_ids,
        )

    def pending_list_update(
        self,
        row,
        idx,
        reason,
    ):
        return {
            "tradingsymbol": row.tradingsymbol,
            "websocket_id": row.websocket_id,
            "idx": idx,
            "reason": reason,
        }

    # Manual
    async def users_exit(self, data):
        user_param_user_obj_list = []
        user_params = []

        for user_param in self.user_params:
            if (user_param["user"].username, user_param["broker"]) not in data:
                user_params.append(user_param)
            else:
                user_param_user_obj_list.append(user_param)

        if (
            self.str_strategy_id in (cache.get("DEPLOYED_STRATEGIES", {})).keys()
            and user_param_user_obj_list
        ):
            instruments = get_option_greeks_instruments(
                symbol=self.symbol,
                websocket_ids=self.websocket_ids,
            )

            self.user_params = user_params

            strategy_list = cache.get("DEPLOYED_STRATEGIES", {})
            strategy_list[self.str_strategy_id] = {
                "user_params": self.user_params,
                "no_of_strategy": self.parameters_len,
            }
            cache.set("DEPLOYED_STRATEGIES", strategy_list)
            buy_pending, sell_pending = [], []

            tradingsymbols: dict = cache.get(self.strategy_tradingsymbol_cache, {})

            for idx, row in enumerate(tradingsymbols):
                if row["ce_tradingsymbol"]:
                    ce = instruments[
                        (instruments["tradingsymbol"] == row["ce_tradingsymbol"])
                    ].iloc[0]
                    buy_pending.append(
                        self.pending_list_update(ce, idx, "ENTER CE USER")
                    )

                if row["pe_tradingsymbol"]:
                    pe = instruments[
                        (instruments["tradingsymbol"] == row["pe_tradingsymbol"])
                    ].iloc[0]
                    buy_pending.append(
                        self.pending_list_update(pe, idx, "ENTER PE USER")
                    )

            await self.place_order(
                buy_pending=buy_pending,
                sell_pending=sell_pending,
                user_params=user_param_user_obj_list,
            )

            try:
                await update_positions(broker=self.broker)
            except Exception:
                pass

    async def users_entry(self, data):
        self.opt_strategy.refresh_from_db()
        user_param_user_obj_list = [
            {
                "broker_api": user.broker_api,
                "user": user.broker_api.user,
                "broker": user.broker_api.broker,
                "quantity_multiple": [
                    item * self.opt_strategy.lot_size
                    for item in divide_and_list(self.parameters_len, user.lots)
                ],
            }
            for user in self.opt_strategy.users.filter(
                is_active=True,
                broker_api__user__username__in=[
                    x[0]
                    for x in list(
                        set(data).difference(
                            [
                                (row["user"].username, row["broker"])
                                for row in self.user_params
                            ]
                        )
                    )
                ],
            )
        ]

        if (
            self.str_strategy_id in (cache.get("DEPLOYED_STRATEGIES", {})).keys()
            and user_param_user_obj_list
        ):
            instruments = get_option_greeks_instruments(
                symbol=self.symbol,
                websocket_ids=self.websocket_ids,
            )

            self.user_params.extend(user_param_user_obj_list)

            strategy_list = cache.get("DEPLOYED_STRATEGIES", {})
            strategy_list[self.str_strategy_id] = {
                "user_params": self.user_params,
                "no_of_strategy": self.parameters_len,
            }
            cache.set("DEPLOYED_STRATEGIES", strategy_list)
            buy_pending, sell_pending = [], []

            tradingsymbols: dict = cache.get(self.strategy_tradingsymbol_cache, {})

            for idx, row in enumerate(tradingsymbols):
                if row["ce_tradingsymbol"]:
                    ce = instruments[
                        (instruments["tradingsymbol"] == row["ce_tradingsymbol"])
                    ].iloc[0]
                    sell_pending.append(
                        self.pending_list_update(ce, idx, "ENTER CE USER")
                    )

                if row["pe_tradingsymbol"]:
                    pe = instruments[
                        (instruments["tradingsymbol"] == row["pe_tradingsymbol"])
                    ].iloc[0]
                    sell_pending.append(
                        self.pending_list_update(pe, idx, "ENTER PE USER")
                    )

            await self.place_order(
                buy_pending=buy_pending,
                sell_pending=sell_pending,
                user_params=user_param_user_obj_list,
            )

            try:
                await update_positions(broker=self.broker)
            except Exception:
                pass
