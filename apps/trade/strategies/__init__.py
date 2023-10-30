import asyncio

from django.core.cache import cache

from apps.integration.models import KotakNeoApi as KotakNeoApiModel
from apps.integration.utils import divide_and_list, get_option_ltp
from apps.integration.utils.broker.dummy import DummyApi
from apps.integration.utils.broker.kotak_neo import KotakNeoApi
from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel


class StrategyOrder(object):
    def __init__(self, opt_strategy: DeployedOptionStrategyModel):
        self.opt_strategy = opt_strategy
        self.symbol = opt_strategy.instrument.symbol
        self.websocket_ids = self.opt_strategy.websocket_ids.split(",")
        self.strategy_id = self.opt_strategy.pk
        self.str_strategy_id = str(self.opt_strategy.pk)
        self.options = self.opt_strategy.options.copy()
        self.parameters = [
            p.parameters
            for p in self.opt_strategy.parameters.filter(is_active=True).order_by(
                "name"
            )
        ]
        self.parameters_len = len(self.parameters) or 1
        self.entry_type = self.opt_strategy.strategy_type
        self.exit_type = "BUY" if self.entry_type == "SELL" else "SELL"
        self.strategy_tradingsymbol_cache = f"TRADINGSYMBOLS_{self.opt_strategy.pk}"
        self.broker = self.opt_strategy.broker
        self.slippage = float(self.opt_strategy.slippage)
        user_params = (
            cache.get("DEPLOYED_STRATEGIES", {})
            .get(self.str_strategy_id, {})
            .get("user_params", [])
        )
        if user_params and cache.get(self.strategy_tradingsymbol_cache):
            self.user_params = user_params
            self.entered = True
        else:
            self.entered = False
            self.user_params = []
            for user in self.opt_strategy.users.filter(is_active=True).order_by(
                "order_seq"
            ):
                self.user_params.append(
                    {
                        "broker_api": user.broker_api,
                        "user": user.broker_api.user,
                        "broker": user.broker_api.broker,
                        "quantity_multiple": [
                            item * self.opt_strategy.lot_size
                            for item in divide_and_list(self.parameters_len, user.lots)
                        ],
                    }
                )

    async def get_kotak_neo_parameters(self, user):
        row = KotakNeoApiModel.objects.get(broker_api__user=user)

        return {
            "username": user.username,
            "headers": {
                "Authorization": f"Bearer {row.access_token}",
                "Sid": row.sid,
                "Auth": row.auth,
                "neo-fin-key": row.neo_fin_key,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            "query_params": {"sId": row.hs_server_id},
        }

    async def quantity_wise_strategy_map(self, user_params):
        quantity_map_list = []

        for idx in range(self.parameters_len):
            quantity_map_list.append(
                {
                    user_param["user"].username: user_param["quantity_multiple"][idx]
                    for user_param in user_params
                }
            )

        return quantity_map_list

    async def place_dummy_order(self, buy_pending, sell_pending, user_params):
        quantity_map_list = await self.quantity_wise_strategy_map(user_params)
        users = [user_param["user"] for user_param in user_params]

        if not user_params:
            return

        dummyapi = DummyApi(users=users)

        if buy_pending:
            await asyncio.gather(
                *[
                    dummyapi.option_place_and_chase_order(
                        symbol=self.symbol,
                        tradingsymbol=row["tradingsymbol"],
                        quantity_map=quantity_map_list[row.get("idx", 0)],
                        transaction_type="BUY",
                        price=get_option_ltp(
                            symbol=self.symbol,
                            tradingsymbol=row["tradingsymbol"],
                            websocket_id=row["websocket_id"],
                        ),
                        tag_prefix=self.str_strategy_id,
                        websocket_id=row["websocket_id"],
                    )
                    for row in buy_pending
                ]
            )

        if sell_pending:
            await asyncio.gather(
                *[
                    dummyapi.option_place_and_chase_order(
                        symbol=self.symbol,
                        tradingsymbol=row["tradingsymbol"],
                        quantity_map=quantity_map_list[row.get("idx", 0)],
                        transaction_type="SELL",
                        price=get_option_ltp(
                            symbol=self.symbol,
                            tradingsymbol=row["tradingsymbol"],
                            websocket_id=row["websocket_id"],
                        ),
                        tag_prefix=self.str_strategy_id,
                        websocket_id=row["websocket_id"],
                    )
                    for row in sell_pending
                ]
            )

    async def place_kotak_neo_order(self, buy_pending, sell_pending, user_params):
        quantity_map_list = await self.quantity_wise_strategy_map(user_params)
        users = [
            await self.get_kotak_neo_parameters(user_param["user"])
            for user_param in user_params
        ]
        if not users:
            return

        knapi = KotakNeoApi(users=users)

        if buy_pending:
            await asyncio.gather(
                *[
                    knapi.option_place_and_chase_order(
                        symbol=self.symbol,
                        tradingsymbol=row["tradingsymbol"],
                        quantity_map=quantity_map_list[row.get("idx", 0)],
                        transaction_type="BUY",
                        expected_price=get_option_ltp(
                            symbol=self.symbol,
                            tradingsymbol=row["tradingsymbol"],
                            websocket_id=row["websocket_id"],
                        )
                        + self.slippage,
                        tag_prefix=self.str_strategy_id,
                        websocket_id=row["websocket_id"],
                    )
                    for row in buy_pending
                ]
            )

        if sell_pending:
            await asyncio.gather(
                *[
                    knapi.option_place_and_chase_order(
                        symbol=self.symbol,
                        tradingsymbol=row["tradingsymbol"],
                        quantity_map=quantity_map_list[row.get("idx", 0)],
                        transaction_type="SELL",
                        expected_price=get_option_ltp(
                            symbol=self.symbol,
                            tradingsymbol=row["tradingsymbol"],
                            websocket_id=row["websocket_id"],
                        )
                        - self.slippage,
                        tag_prefix=self.str_strategy_id,
                        websocket_id=row["websocket_id"],
                    )
                    for row in sell_pending
                ]
            )

    async def place_order(
        self,
        sell_pending: list,
        buy_pending: list,
        user_params: list | None = None,
    ):
        if buy_pending or sell_pending:
            if not user_params:
                user_params = self.user_params

            if self.broker == "kotak_neo":
                kotak_neo_users_params = [
                    user_param
                    for user_param in user_params
                    if user_param["broker"] == "kotak_neo"
                ]

                dummy_users_params = [
                    user_param
                    for user_param in user_params
                    if user_param["broker"] == "dummy"
                ]

                await asyncio.gather(
                    self.place_dummy_order(
                        buy_pending,
                        sell_pending,
                        user_params=dummy_users_params,
                    ),
                    self.place_kotak_neo_order(
                        buy_pending,
                        sell_pending,
                        user_params=kotak_neo_users_params,
                    ),
                )
