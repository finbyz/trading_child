from django.core.cache import cache

from apps.integration.utils import (
    divide_and_list,
    get_option_greeks_instruments,
    get_option_instruments_row,
    get_spot_ltp,
)
from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel
from apps.trade.strategies import StrategyOrder
from apps.trade.utils import update_positions


class Strategy(StrategyOrder):
    def __init__(
        self,
        strategy_id: int,
    ):
        super(Strategy, self).__init__(
            opt_strategy=DeployedOptionStrategyModel.objects.get(pk=strategy_id)
        )

        self.is_delta_based = self.options["is_delta_based"]
        self.delta = self.options["delta"] / 100
        self.is_straddle = self.options["is_straddle"]
        self.max_points = self.options["max_points"]
        self.slippage = self.options["slippage"]

    async def place_entry_order(self):
        buy_pending, sell_pending = [], []
        ltp = get_spot_ltp(self.symbol)
        instruments = get_option_greeks_instruments(self.symbol, self.websocket_ids)

        deployed_strategy = cache.get("DEPLOYED_STRATEGIES", {})

        if deployed_strategy.get(self.str_strategy_id, {}) and cache.get(
            self.strategy_tradingsymbol_cache
        ):
            return

        deployed_strategy[self.str_strategy_id] = {"user_params": self.user_params}
        cache.set("DEPLOYED_STRATEGIES", deployed_strategy)

        pe = (
            instruments[
                (instruments["delta"] < -self.delta)
                & (instruments["option_type"] == "PE")
                & (instruments["strike"] >= ltp - 2000)
            ]
            .sort_values("strike")
            .iloc[0]
        )

        ce = (
            instruments[
                (instruments["delta"] > self.delta)
                & (instruments["option_type"] == "CE")
                & (instruments["strike"] <= ltp + 2000)
            ]
            .sort_values("strike")
            .iloc[-1]
        )

        if self.entry_type == "SELL":
            sell_pending.extend(
                [
                    {
                        "tradingsymbol": ce.tradingsymbol,
                        "websocket_id": ce.websocket_id,
                        "idx": 0,
                    },
                    {
                        "tradingsymbol": pe.tradingsymbol,
                        "websocket_id": pe.websocket_id,
                        "idx": 0,
                    },
                ]
            )
        else:
            buy_pending.extend(
                [
                    {
                        "tradingsymbol": ce.tradingsymbol,
                        "websocket_id": ce.websocket_id,
                        "idx": 0,
                    },
                    {
                        "tradingsymbol": pe.tradingsymbol,
                        "websocket_id": pe.websocket_id,
                        "idx": 0,
                    },
                ]
            )

        tradingsymbols = [
            {
                "ce_tradingsymbol": ce["tradingsymbol"],
                "pe_tradingsymbol": pe["tradingsymbol"],
                "position_type": -1 if self.entry_type == "SELL" else 1,
                "websocket_id": ce.websocket_id if ce is not None else pe.websocket_id,
            }
        ]

        await self.place_order(sell_pending, buy_pending)
        cache.set(self.strategy_tradingsymbol_cache, tradingsymbols)

    async def place_exit_order(self):
        buy_pending, sell_pending = [], []

        tradingsymbols = cache.get(self.strategy_tradingsymbol_cache, [])

        if not tradingsymbols:
            return

        ce = get_option_instruments_row(
            symbol=self.symbol,
            tradingsymbol=tradingsymbols[0]["ce_tradingsymbol"],
            websocket_id=tradingsymbols[0]["websocket_id"],
        )

        pe = get_option_instruments_row(
            symbol=self.symbol,
            tradingsymbol=tradingsymbols[0]["pe_tradingsymbol"],
            websocket_id=tradingsymbols[0]["websocket_id"],
        )

        if self.exit_type == "SELL":
            sell_pending.extend(
                [
                    {
                        "tradingsymbol": ce.tradingsymbol,
                        "websocket_id": ce.websocket_id,
                        "idx": 0,
                    },
                    {
                        "tradingsymbol": pe.tradingsymbol,
                        "websocket_id": pe.websocket_id,
                        "idx": 0,
                    },
                ]
            )
        else:
            buy_pending.extend(
                [
                    {
                        "tradingsymbol": ce.tradingsymbol,
                        "websocket_id": ce.websocket_id,
                        "idx": 0,
                    },
                    {
                        "tradingsymbol": pe.tradingsymbol,
                        "websocket_id": pe.websocket_id,
                        "idx": 0,
                    },
                ]
            )

        cache.delete(self.strategy_tradingsymbol_cache)
        deployed_strategy = cache.get("DEPLOYED_STRATEGIES", {})
        del deployed_strategy[self.str_strategy_id]
        cache.set("DEPLOYED_STRATEGIES", deployed_strategy)

        await self.place_order(sell_pending, buy_pending)

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
                if self.entry_type == "SELL":
                    sell_pending.extend(
                        [
                            {
                                "tradingsymbol": row["ce_tradingsymbol"],
                                "websocket_id": self.websocket_ids[0],
                                "idx": 0,
                            },
                            {
                                "tradingsymbol": row["pe_tradingsymbol"],
                                "websocket_id": self.websocket_ids[0],
                                "idx": 0,
                            },
                        ]
                    )
                else:
                    buy_pending.extend(
                        [
                            {
                                "tradingsymbol": row["ce_tradingsymbol"],
                                "websocket_id": self.websocket_ids[0],
                                "idx": 0,
                            },
                            {
                                "tradingsymbol": row["pe_tradingsymbol"],
                                "websocket_id": self.websocket_ids[0],
                                "idx": 0,
                            },
                        ]
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

        # for user_param_user_obj in user_param_user_obj_list:
        #     await send_notifications(
        #         self.opt_strategy.strategy_name.upper(),
        #         f"{user_param_user_obj['user'].username} ALGO ENTRED!".upper(),
        #         "alert-success",
        #     )

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
                if self.exit_type == "SELL":
                    sell_pending.extend(
                        [
                            {
                                "tradingsymbol": row["ce_tradingsymbol"],
                                "websocket_id": self.websocket_ids[0],
                                "idx": 0,
                            },
                            {
                                "tradingsymbol": row["pe_tradingsymbol"],
                                "websocket_id": self.websocket_ids[0],
                                "idx": 0,
                            },
                        ]
                    )
                else:
                    buy_pending.extend(
                        [
                            {
                                "tradingsymbol": row["ce_tradingsymbol"],
                                "websocket_id": self.websocket_ids[0],
                                "idx": 0,
                            },
                            {
                                "tradingsymbol": row["pe_tradingsymbol"],
                                "websocket_id": self.websocket_ids[0],
                                "idx": 0,
                            },
                        ]
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
