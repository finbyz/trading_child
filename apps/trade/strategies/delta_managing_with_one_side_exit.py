import asyncio
import datetime as dt
import traceback

import pandas as pd
from colorama import Fore
from dateutil.parser import parse
from django.core.cache import cache
from django.utils import timezone

from apps.integration.utils import (
    divide_and_list,
    get_option_geeks_instruments_row,
    get_option_greeks_instruments,
    get_pe_ce_oi_change,
)
from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel
from apps.trade.strategies import StrategyOrder
from apps.trade.utils import update_positions
from apps.trade.utils.utils_get_dummy_points import get_dummy_points


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

        self.initiate()

        self.min_delta = [
            x["day_wise"][str(self.days_left)]["min_delta"] / 100
            for x in self.parameters
        ]

    def initiate(self):
        tz = timezone.localtime().tzinfo

        self.today = timezone.localdate()
        self.expiry = cache.get(self.option_expiry_cache, {}).get(self.websocket_id)
        self.days_left = (self.expiry - self.today).days
        self.oneside_check_timestamp = dt.datetime.combine(
            self.today, self.oneside_check_time
        ).replace(tzinfo=tz)
        self.expiry_check_timestamp = dt.datetime.combine(
            self.expiry, self.expiry_check_time
        ).replace(tzinfo=tz)
        self.expiry_check_sigma_timestamp = dt.datetime.combine(
            self.expiry, self.expiry_check_sigma_time
        ).replace(tzinfo=tz)

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

    async def find_strike(
        self,
        instruments,
        near,
        option_type,
        query_type,
        near_type,
    ):
        df: pd.DataFrame = instruments
        spot_price = cache.get(self.option_instrument_ltp_cache)
        if option_type == "CE":
            df = df[df["strike"] > spot_price - 45].copy()
        else:
            df = df[df["strike"] < spot_price + 45].copy()

        if near_type == "delta":
            df = (
                (
                    df[(df["option_type"] == option_type) & (df[near_type] >= near)]
                    .sort_values("strike", ascending=False)
                    .copy()
                )
                if query_type == ">"
                else (
                    df[(df["option_type"] == option_type) & (df[near_type] <= near)]
                    .sort_values("strike", ascending=True)
                    .copy()
                )
            )
        elif query_type == ">":
            df = df[(df["option_type"] == option_type) & (df[near_type] >= near)].copy()
            if option_type == "CE":
                df.sort_values(
                    "strike", inplace=True, ignore_index=True, ascending=False
                )
            else:
                df.sort_values(
                    "strike", inplace=True, ignore_index=True, ascending=True
                )
        else:
            df = df[(df["option_type"] == option_type) & (df[near_type] <= near)].copy()

            if option_type == "PE":
                df.sort_values(
                    "strike", inplace=True, ignore_index=True, ascending=False
                )
            else:
                df.sort_values(
                    "strike", inplace=True, ignore_index=True, ascending=True
                )

        if not df.empty:
            return df.iloc[0].strike, df.iloc[0].sigma

        print("STRIKE EMPTY NOT FOUND.")
        return 0, 0

    async def get_ce_exit(
        self,
        idx,
        ce,
    ):
        return (
            [self.pending_list_update(ce, idx, "EXIT CE")],
            None,
            True,
            True,
        )

    async def get_pe_exit(
        self,
        idx,
        pe,
    ):
        return (
            [self.pending_list_update(pe, idx, "EXIT PE")],
            None,
            True,
            True,
        )

    async def get_ce_reentry(self, idx, instruments, pe, now_time=timezone.localtime()):
        instruments = get_option_greeks_instruments(
            symbol=self.symbol,
            websocket_ids=self.websocket_ids,
        )

        buy_pending = []
        sell_pending = []

        pe_reentry_strike, _ = await self.find_strike(
            instruments, -self.shift_min_delta_entry, "PE", "<", "delta"
        )
        if (
            (
                pe["delta"] > -self.shift_min_delta
                and now_time <= self.expiry_check_timestamp
            )
            or pe["delta"] < -self.shift_max_delta
        ) and pe_reentry_strike != pe["strike"]:
            ce_reentry_strike, _ = await self.find_strike(
                instruments, self.shift_min_delta_entry, "CE", "<", "delta"
            )
            if ce_reentry_strike and pe_reentry_strike:
                buy_pending.append(
                    self.pending_list_update(pe, idx, "EXIT PE - RESTRUCTURING")
                )
                ce = instruments[
                    (instruments["strike"] == ce_reentry_strike)
                    & (instruments["option_type"] == "CE")
                ].iloc[0]
                pe = instruments[
                    (instruments["strike"] == pe_reentry_strike)
                    & (instruments["option_type"] == "PE")
                ].iloc[0]

                sell_pending.extend(
                    [
                        self.pending_list_update(
                            pe, idx, "ENTERING PE - RESTRUCTURING"
                        ),
                        self.pending_list_update(
                            ce, idx, "ENTERING CE - RESTRUCTURING"
                        ),
                    ]
                )

                return (
                    buy_pending,
                    sell_pending,
                    ce["tradingsymbol"],
                    pe["tradingsymbol"],
                    False,
                    False,
                )
        else:
            ce_reentry_strike, _ = await self.find_strike(
                instruments, -pe["delta"], "CE", "<", "delta"
            )
            if ce_reentry_strike:
                ce = instruments[
                    (instruments["strike"] == ce_reentry_strike)
                    & (instruments["option_type"] == "CE")
                ].iloc[0]
                sell_pending.append(self.pending_list_update(ce, idx, "ENTERING CE"))

                return (
                    buy_pending,
                    sell_pending,
                    ce["tradingsymbol"],
                    pe["tradingsymbol"],
                    False,
                    False,
                )

        return buy_pending, sell_pending, None, pe["tradingsymbol"], True, True

    async def get_pe_reentry(self, idx, instruments, ce, now_time=timezone.localtime()):
        instruments = get_option_greeks_instruments(
            symbol=self.symbol,
            websocket_ids=self.websocket_ids,
        )

        buy_pending = []
        sell_pending = []

        ce_reentry_strike, _ = await self.find_strike(
            instruments,
            self.shift_min_delta_entry,
            "CE",
            ">",
            "delta",
        )
        if (
            (
                ce["delta"] < self.shift_min_delta
                and now_time <= self.expiry_check_timestamp
            )
            or ce["delta"] > self.shift_max_delta
        ) and ce_reentry_strike != ce["strike"]:
            pe_reentry_strike, _ = await self.find_strike(
                instruments,
                -self.shift_min_delta_entry,
                "PE",
                ">",
                "delta",
            )
            if ce_reentry_strike and pe_reentry_strike:
                buy_pending.append(
                    self.pending_list_update(ce, idx, "EXIT CE - RESTRUCTURING")
                )
                ce = instruments[
                    (instruments["strike"] == ce_reentry_strike)
                    & (instruments["option_type"] == "CE")
                ].iloc[0]
                pe = instruments[
                    (instruments["strike"] == pe_reentry_strike)
                    & (instruments["option_type"] == "PE")
                ].iloc[0]
                sell_pending.extend(
                    [
                        self.pending_list_update(
                            pe, idx, "ENTERING PE - RESTRUCTURING"
                        ),
                        self.pending_list_update(
                            ce, idx, "ENTERING CE - RESTRUCTURING"
                        ),
                    ]
                )

                return (
                    buy_pending,
                    sell_pending,
                    ce["tradingsymbol"],
                    pe["tradingsymbol"],
                    False,
                    False,
                )

        else:
            pe_reentry_strike, _ = await self.find_strike(
                instruments,
                -ce["delta"],
                "PE",
                ">",
                "delta",
            )
            if pe_reentry_strike:
                pe = instruments[
                    (instruments["strike"] == pe_reentry_strike)
                    & (instruments["option_type"] == "PE")
                ].iloc[0]
                sell_pending.append(self.pending_list_update(pe, idx, "ENTERING PE"))

                return (
                    buy_pending,
                    sell_pending,
                    ce["tradingsymbol"],
                    pe["tradingsymbol"],
                    False,
                    False,
                )

        return buy_pending, sell_pending, ce["tradingsymbol"], None, True, True

    async def get_pe_reentry(
        self,
        idx,
        instruments,
        pe,
        now_time=timezone.localtime(),
    ):
        buy_pending = []
        sell_pending = []

        pe_reentry_strike, _ = await self.find_strike(
            instruments,
            -self.shift_min_delta_entry,
            "PE",
            "<",
            "delta",
        )
        if (
            (
                pe["delta"] > -self.shift_min_delta
                and now_time <= self.expiry_check_timestamp
            )
            or pe["delta"] < -self.shift_max_delta
        ) and pe_reentry_strike != pe["strike"]:
            ce_reentry_strike, _ = await self.find_strike(
                instruments,
                self.shift_min_delta_entry,
                "CE",
                "<",
                "delta",
            )

            if ce_reentry_strike and pe_reentry_strike:
                buy_pending.append(
                    self.pending_list_update(pe, idx, "EXIT PE - RESTRUCTURING")
                )

                ce = instruments[
                    (instruments["strike"] == ce_reentry_strike)
                    & (instruments["option_type"] == "CE")
                ].iloc[0]
                pe = instruments[
                    (instruments["strike"] == pe_reentry_strike)
                    & (instruments["option_type"] == "PE")
                ].iloc[0]

                sell_pending.extend(
                    [
                        self.pending_list_update(
                            pe, idx, "ENTERING PE - RESTRUCTURING"
                        ),
                        self.pending_list_update(
                            ce, idx, "ENTERING CE - RESTRUCTURING"
                        ),
                    ]
                )

                return (
                    buy_pending,
                    sell_pending,
                    ce["tradingsymbol"],
                    pe["tradingsymbol"],
                    False,
                    False,
                )
        else:
            ce_reentry_strike, _ = await self.find_strike(
                instruments,
                -pe["delta"],
                "CE",
                "<",
                "delta",
            )
            if ce_reentry_strike:
                ce = instruments[
                    (instruments["strike"] == ce_reentry_strike)
                    & (instruments["option_type"] == "CE")
                ].iloc[0]
                sell_pending.append(self.pending_list_update(ce, idx, "ENTERING CE"))

                return (
                    buy_pending,
                    sell_pending,
                    ce["tradingsymbol"],
                    pe["tradingsymbol"],
                    False,
                    False,
                )

        return buy_pending, sell_pending, None, pe["tradingsymbol"], True, True

    async def get_pe_reentry(
        self,
        idx,
        instruments,
        ce,
        now_time=timezone.localtime(),
    ):
        buy_pending = []
        sell_pending = []

        ce_reentry_strike, _ = await self.find_strike(
            instruments,
            self.shift_min_delta_entry,
            "CE",
            ">",
            "delta",
        )

        if (
            (
                ce["delta"] < self.shift_min_delta
                and now_time <= self.expiry_check_timestamp
            )
            or ce["delta"] > self.shift_max_delta
        ) and ce_reentry_strike != ce["strike"]:
            pe_reentry_strike, _ = await self.find_strike(
                instruments,
                -self.shift_min_delta_entry,
                "PE",
                ">",
                "delta",
            )

            if ce_reentry_strike and pe_reentry_strike:
                buy_pending.append(
                    self.pending_list_update(ce, idx, "EXIT CE - RESTRUCTURING")
                )

                ce = instruments[
                    (instruments["strike"] == ce_reentry_strike)
                    & (instruments["option_type"] == "CE")
                ].iloc[0]
                pe = instruments[
                    (instruments["strike"] == pe_reentry_strike)
                    & (instruments["option_type"] == "PE")
                ].iloc[0]

                sell_pending.extend(
                    [
                        self.pending_list_update(
                            pe, idx, "ENTERING PE - RESTRUCTURING"
                        ),
                        self.pending_list_update(
                            ce, idx, "ENTERING CE - RESTRUCTURING"
                        ),
                    ]
                )

                return (
                    buy_pending,
                    sell_pending,
                    ce["tradingsymbol"],
                    pe["tradingsymbol"],
                    False,
                    False,
                )
        else:
            pe_reentry_strike, _ = await self.find_strike(
                instruments, -ce["delta"], "PE", ">", "delta"
            )
            if pe_reentry_strike:
                pe = instruments[
                    (instruments["strike"] == pe_reentry_strike)
                    & (instruments["option_type"] == "PE")
                ].iloc[0]
                sell_pending.append(self.pending_list_update(pe, idx, "ENTERING PE"))

                return (
                    buy_pending,
                    sell_pending,
                    ce["tradingsymbol"],
                    pe["tradingsymbol"],
                    False,
                    False,
                )

        return buy_pending, sell_pending, ce["tradingsymbol"], None, True, True

    async def check_shifting_orders(
        self,
        instruments,
        idx,
        ce,
        pe,
        multiplier,
        now_time=timezone.localtime(),
    ):
        buy_pending, sell_pending = [], []
        if (
            (pe["delta"] + ce["delta"])
            > (min(abs(pe["delta"]), ce["delta"]) * multiplier)
        ) and ce[
            "last_price"
        ] > self.skip_price:  # Call is Heavy
            if ce.strike - ce["spot_price"] <= self.point_difference:  # Call Shift Out
                if now_time <= self.expiry_check_timestamp:
                    strike, sigma = await self.find_strike(
                        instruments,
                        -pe["delta"],
                        "CE",
                        ">",
                        "delta",
                    )
                else:
                    strike, sigma = await self.find_strike(
                        instruments,
                        pe["last_price"],
                        "CE",
                        ">",
                        "last_price",
                    )

                if (
                    strike
                    and strike != int(ce["strike"])
                    and abs(sigma - ce["sigma"]) < self.sigma_diff
                ):
                    buy_pending.append(
                        self.pending_list_update(
                            ce, idx, "EXIT CE - SHIFTING CALL AWAY"
                        )
                    )
                    ce = instruments[
                        (instruments["strike"] == strike)
                        & (instruments["option_type"] == "CE")
                    ].iloc[0]
                    sell_pending.append(
                        self.pending_list_update(
                            ce, idx, "ENTER CE - SHIFTING CALL AWAY"
                        )
                    )
                elif strike == int(ce["strike"]):
                    print("CALL AWAY SHIFT STRIKE")
                elif not strike:
                    print("CALL AWAY SHIFT STRIKE NOT FOUND")
            else:  # Put Shift In
                if now_time <= self.expiry_check_timestamp:
                    strike, sigma = await self.find_strike(
                        instruments,
                        -ce["delta"],
                        "PE",
                        ">",
                        "delta",
                    )
                else:
                    strike, sigma = await self.find_strike(
                        instruments,
                        ce["last_price"],
                        "PE",
                        "<",
                        "last_price",
                    )

                if (
                    strike
                    and strike != int(pe["strike"])
                    and abs(sigma - ce["sigma"]) < self.sigma_diff
                ):
                    buy_pending.append(
                        self.pending_list_update(pe, idx, "EXIT PE - SHIFTING PUT IN")
                    )
                    pe = instruments[
                        (instruments["strike"] == strike)
                        & (instruments["option_type"] == "PE")
                    ].iloc[0]
                    sell_pending.append(
                        self.pending_list_update(pe, idx, "ENTER PE - SHIFTING PUT IN")
                    )
                elif strike == int(pe["strike"]):
                    print("SHIFTED PUT IN STRIKE")
                elif not strike:
                    print("SHIFTED PUT IN STRIKE NOT FOUND")
        elif (
            (ce["delta"] + pe["delta"])
            < -(min(abs(pe["delta"]), ce["delta"]) * multiplier)
        ) and pe[
            "last_price"
        ] > self.skip_price:  # Put is Heavy
            if pe.strike - pe["spot_price"] >= -self.point_difference:  # Put Shift Out
                if now_time <= self.expiry_check_timestamp:
                    strike, sigma = await self.find_strike(
                        instruments,
                        -ce["delta"],
                        "PE",
                        "<",
                        "delta",
                    )
                else:
                    strike, sigma = await self.find_strike(
                        instruments,
                        ce["last_price"],
                        "PE",
                        ">",
                        "last_price",
                    )

                if (
                    strike
                    and strike != pe["strike"]
                    and abs(sigma - pe["sigma"]) < self.sigma_diff
                ):
                    buy_pending.append(
                        self.pending_list_update(pe, idx, "EXIT PE - SHIFTING PUT AWAY")
                    )
                    pe = instruments[
                        (instruments["strike"] == strike)
                        & (instruments["option_type"] == "PE")
                    ].iloc[0]
                    sell_pending.append(
                        self.pending_list_update(
                            pe, idx, "ENTER PE - SHIFTING PUT AWAY"
                        )
                    )
                elif strike == int(pe["strike"]):
                    print("PUT AWAY SHIFT STIKE")
                elif not strike:
                    print("PUT AWAY SHIFT STIKE NOT FOUND")
            else:  # Call Shift In
                if now_time <= self.expiry_check_timestamp:
                    strike, sigma = await self.find_strike(
                        instruments,
                        -pe["delta"],
                        "CE",
                        "<",
                        "delta",
                    )
                else:
                    strike, sigma = await self.find_strike(
                        instruments,
                        pe["last_price"],
                        "CE",
                        "<",
                        "last_price",
                    )

                if (
                    strike
                    and strike != ce["strike"]
                    and abs(sigma - ce["sigma"]) < self.sigma_diff
                ):
                    buy_pending.append(
                        self.pending_list_update(ce, idx, "EXIT CE - SHIFTING CALL IN")
                    )
                    ce = instruments[
                        (instruments["strike"] == strike)
                        & (instruments["option_type"] == "CE")
                    ].iloc[0]
                    sell_pending.append(
                        self.pending_list_update(
                            ce, idx, "ENTER PE - SHIFTING PUT AWAY"
                        )
                    )
                elif not ce["last_price"] > self.skip_price:
                    print("CALL IN SHIFT STRIKE")
                elif not strike:
                    print("PUT AWAY SHIFT STIKE NOT FOUND")

        return (
            buy_pending,
            sell_pending,
            ce["tradingsymbol"],
            pe["tradingsymbol"],
        )

    def one_side_without_check_exit(
        self,
        idx,
        row,
        exited_one_side,
        ce_exit_one_side,
        pe_exit_one_side,
        parameters,
    ):
        change = parameters["change"] / 100
        reentry_oi = parameters["reentry_oi"] / 100
        one_side_exit_change_param = parameters["one_side_exit_change_param"] * 12
        one_side_reentry_change_param = parameters["one_side_reentry_change_param"] * 12
        make_ce_exit = make_pe_exit = False
        ce_reentry = pe_reentry = False
        if (
            not exited_one_side
            and row["timestamp"] < self.oneside_check_timestamp
            and row["timestamp"] < self.expiry_check_timestamp
            and not cache.get(f"ONE_SIDE_EXIT_HOLD_{self.str_strategy_id}_{idx}", 0)
        ):
            ce_exit_signal = (
                row[f"pe_minus_ce_oi_change_{one_side_exit_change_param}_update"]
                > change
            ) and (
                (
                    row["pe_oi_abs_change_72"] > 0
                    and row["ce_oi_abs_change_72"] > 0
                    and row["pe_by_ce_oi_abs_change_72"] > 1.4
                )
                or (row["pe_oi_abs_change_72"] <= 0 or row["ce_oi_abs_change_72"] <= 0)
            )

            pe_exit_signal = (
                row[f"ce_minus_pe_oi_change_{one_side_exit_change_param}_update"]
                > change
            ) and (
                (
                    row["pe_oi_abs_change_72"] > 0
                    and row["ce_oi_abs_change_72"] > 0
                    and row["pe_by_ce_oi_abs_change_72"] < 1 / 1.4
                )
                or (row["pe_oi_abs_change_72"] <= 0 or row["ce_oi_abs_change_72"] <= 0)
            )

            if ce_exit_signal:
                make_ce_exit = True

            elif pe_exit_signal:
                make_pe_exit = True

        else:
            if (
                ce_exit_one_side
                and row[f"ce_minus_pe_oi_change_{one_side_reentry_change_param}_update"]
                > reentry_oi
            ):
                ce_reentry = True
            elif (
                pe_exit_one_side
                and row[f"pe_minus_ce_oi_change_{one_side_reentry_change_param}_update"]
                > reentry_oi
            ):
                pe_reentry = True

        return make_ce_exit, make_pe_exit, ce_reentry, pe_reentry

    def one_side_check_exit(
        self,
        idx,
        row,
        exited_one_side,
        ce_exit_one_side,
        pe_exit_one_side,
        parameters,
    ):
        change = parameters["change"] / 100
        reentry_oi = parameters["reentry_oi"] / 100
        less_than = parameters["less_than"] / 100
        one_side_exit_change_param = parameters["one_side_exit_change_param"] * 12
        one_side_reentry_change_param = parameters["one_side_reentry_change_param"] * 12
        make_ce_exit = make_pe_exit = False
        ce_reentry = pe_reentry = False
        if (
            not exited_one_side
            and row["timestamp"] < self.oneside_check_timestamp
            and row["timestamp"] < self.expiry_check_timestamp
            and not cache.get(f"ONE_SIDE_EXIT_HOLD_{self.str_strategy_id}_{idx}", 0)
        ):
            ce_exit_signal = (
                (
                    row[f"pe_minus_ce_oi_change_{one_side_exit_change_param}_update"]
                    > change
                )
                and (row[f"ce_oi_change_{one_side_exit_change_param}"] <= less_than)
            ) and (
                (
                    row["pe_oi_abs_change_72"] > 0
                    and row["ce_oi_abs_change_72"] > 0
                    and row["pe_by_ce_oi_abs_change_72"] > 1.4
                )
                or (row["pe_oi_abs_change_72"] <= 0 or row["ce_oi_abs_change_72"] <= 0)
            )

            pe_exit_signal = (
                (
                    row[f"ce_minus_pe_oi_change_{one_side_exit_change_param}_update"]
                    > change
                )
                and (row[f"pe_oi_change_{one_side_exit_change_param}"] <= less_than)
                and (
                    (
                        row["pe_oi_abs_change_72"] > 0
                        and row["ce_oi_abs_change_72"] > 0
                        and row["pe_by_ce_oi_abs_change_72"] < 1 / 1.4
                    )
                    or (
                        row["pe_oi_abs_change_72"] <= 0
                        or row["ce_oi_abs_change_72"] <= 0
                    )
                )
            )

            if ce_exit_signal:
                make_ce_exit = True

            elif pe_exit_signal:
                make_pe_exit = True
        else:
            if (
                ce_exit_one_side
                and row[f"ce_minus_pe_oi_change_{one_side_reentry_change_param}_update"]
                > reentry_oi
            ):
                ce_reentry = True
            elif (
                pe_exit_one_side
                and row[f"pe_minus_ce_oi_change_{one_side_reentry_change_param}_update"]
                > reentry_oi
            ):
                pe_reentry = True

        return make_ce_exit, make_pe_exit, ce_reentry, pe_reentry

    async def run_strategy(
        self,
        strategies: list[str],
        conditions: list,
    ):
        exit_trigger = False
        while (
            timezone.localtime().time() < self.exit_time
            and self.str_strategy_id in (cache.get("DEPLOYED_STRATEGIES", {})).keys()
        ):
            for idx, (func, cond) in enumerate(zip(strategies, conditions)):
                if (
                    self.str_strategy_id
                    not in (cache.get("DEPLOYED_STRATEGIES", {})).keys()
                ):
                    break

                self.user_params = (cache.get("DEPLOYED_STRATEGIES", {}))[
                    self.str_strategy_id
                ]["user_params"]

                tradingsymbols = cache.get(self.strategy_tradingsymbol_cache, {})
                now_time = timezone.localtime()

                instruments = get_option_greeks_instruments(
                    symbol=self.symbol,
                    websocket_ids=[self.websocket_id],
                )

                live_pcr_df = get_pe_ce_oi_change(
                    underlying=self.symbol,
                    websocket_id=self.websocket_id,
                    difference_list=self.difference_list,
                )

                ce_tradingsymbol = tradingsymbols[idx]["ce_tradingsymbol"]
                pe_tradingsymbol = tradingsymbols[idx]["pe_tradingsymbol"]

                make_ce_exit = make_pe_exit = ce_reentry = pe_reentry = False
                buy_pending, sell_pending = [], []

                tradingsymbols = cache.get(self.strategy_tradingsymbol_cache, {})
                tradingsymbol_temp = tradingsymbols.copy()

                ce, pe = None, None

                if ce_tradingsymbol:
                    ce = get_option_geeks_instruments_row(
                        symbol=self.symbol,
                        tradingsymbol=ce_tradingsymbol,
                        websocket_id=self.websocket_id,
                    )

                if pe_tradingsymbol:
                    pe = get_option_geeks_instruments_row(
                        symbol=self.symbol,
                        tradingsymbol=pe_tradingsymbol,
                        websocket_id=self.websocket_id,
                    )

                exited_one_side = tradingsymbol_temp[idx]["exited_one_side"]
                ce_exit_one_side = tradingsymbol_temp[idx]["ce_exit_one_side"]
                pe_exit_one_side = tradingsymbol_temp[idx]["pe_exit_one_side"]

                if not live_pcr_df.empty:
                    row = live_pcr_df.iloc[-1]
                    make_ce_exit, make_pe_exit, ce_reentry, pe_reentry = func(
                        idx,
                        row,
                        exited_one_side,
                        ce_exit_one_side,
                        pe_exit_one_side,
                        cond,
                    )

                if exited_one_side:
                    if ce_reentry and ce_exit_one_side:
                        (
                            buy_pending_temp,
                            sell_pending_temp,
                            ce_tradingsymbol,
                            pe_tradingsymbol,
                            exited_one_side,
                            ce_exit_one_side,
                        ) = await self.get_ce_reentry(idx, instruments, pe, now_time)

                        buy_pending.extend(buy_pending_temp)
                        sell_pending.extend(sell_pending_temp)

                        ce, pe = None, None

                        if ce_tradingsymbol:
                            ce = get_option_geeks_instruments_row(
                                symbol=self.symbol,
                                tradingsymbol=ce_tradingsymbol,
                                websocket_id=self.websocket_id,
                            )

                        if pe_tradingsymbol:
                            pe = get_option_geeks_instruments_row(
                                symbol=self.symbol,
                                tradingsymbol=pe_tradingsymbol,
                                websocket_id=self.websocket_id,
                            )

                    elif pe_reentry and pe_exit_one_side:
                        (
                            buy_pending_temp,
                            sell_pending_temp,
                            ce_tradingsymbol,
                            pe_tradingsymbol,
                            exited_one_side,
                            pe_exit_one_side,
                        ) = await self.get_pe_reentry(idx, instruments, ce, now_time)

                        buy_pending.extend(buy_pending_temp)
                        sell_pending.extend(sell_pending_temp)

                        ce, pe = None, None

                        if ce_tradingsymbol:
                            ce = get_option_geeks_instruments_row(
                                symbol=self.symbol,
                                tradingsymbol=ce_tradingsymbol,
                                websocket_id=self.websocket_id,
                            )

                        if pe_tradingsymbol:
                            pe = get_option_geeks_instruments_row(
                                symbol=self.symbol,
                                tradingsymbol=pe_tradingsymbol,
                                websocket_id=self.websocket_id,
                            )
                else:
                    if make_ce_exit:
                        (
                            buy_pending_temp,
                            ce_tradingsymbol,
                            exited_one_side,
                            ce_exit_one_side,
                        ) = await self.get_ce_exit(idx, ce)

                        buy_pending.extend(buy_pending_temp)

                        ce = None

                        if ce_tradingsymbol:
                            ce = get_option_geeks_instruments_row(
                                symbol=self.symbol,
                                tradingsymbol=ce_tradingsymbol,
                                websocket_id=self.websocket_id,
                            )

                    elif make_pe_exit:
                        (
                            buy_pending_temp,
                            pe_tradingsymbol,
                            exited_one_side,
                            pe_exit_one_side,
                        ) = await self.get_pe_exit(idx, pe)

                        buy_pending.extend(buy_pending_temp)

                        pe = None

                        if pe_tradingsymbol:
                            pe = get_option_geeks_instruments_row(
                                symbol=self.symbol,
                                tradingsymbol=pe_tradingsymbol,
                                websocket_id=self.websocket_id,
                            )

                    else:
                        (
                            buy_pending_temp,
                            sell_pending_temp,
                            ce_tradingsymbol,
                            pe_tradingsymbol,
                        ) = await self.check_shifting_orders(
                            instruments=instruments,
                            idx=idx,
                            ce=ce,
                            pe=pe,
                            multiplier=self.multiplier,
                            now_time=now_time,
                        )

                        buy_pending.extend(buy_pending_temp)
                        sell_pending.extend(sell_pending_temp)

                        ce, pe = None, None

                        if ce_tradingsymbol:
                            ce = get_option_geeks_instruments_row(
                                symbol=self.symbol,
                                tradingsymbol=ce_tradingsymbol,
                                websocket_id=self.websocket_id,
                            )

                        if pe_tradingsymbol:
                            pe = get_option_geeks_instruments_row(
                                symbol=self.symbol,
                                tradingsymbol=pe_tradingsymbol,
                                websocket_id=self.websocket_id,
                            )

                        del buy_pending_temp, sell_pending_temp

                tradingsymbols[idx] = {
                    "ce_tradingsymbol": ce_tradingsymbol,
                    "pe_tradingsymbol": pe_tradingsymbol,
                    "exited_one_side": exited_one_side,
                    "ce_exit_one_side": ce_exit_one_side,
                    "pe_exit_one_side": pe_exit_one_side,
                    "position_type": -1 if self.entry_type == "SELL" else 1,
                    "websocket_id": self.websocket_id,
                    "strategy_name": cond["name"],
                }
                cache.set(self.strategy_tradingsymbol_cache, tradingsymbols)

                if buy_pending or sell_pending:
                    await self.place_order(
                        buy_pending=buy_pending,
                        sell_pending=sell_pending,
                    )

                    try:
                        await update_positions(broker=self.broker)
                    except Exception as e:
                        traceback.print_exc()
                        print("GET POSITION ERROR", e)

                stop_loss = cache.get("OPTION_STRATEGIES_STOP_LOSSES", {}).get(
                    self.strategy_id, 0
                )

                dummy_points = await get_dummy_points(self.strategy_id)
                difference_points = dummy_points + stop_loss
                print("Difference", difference_points)

                call_sigma = put_sigma = call_delta = put_delta = 0
                ce_print = pe_print = "NONE"

                total_delta = 0
                if ce_tradingsymbol:
                    call_delta = ce.delta * 100
                    call_sigma = ce.sigma * 100
                    ce_print = ce_tradingsymbol
                if pe_tradingsymbol:
                    put_delta = pe.delta * 100
                    put_sigma = pe.sigma * 100
                    pe_print = pe_tradingsymbol

                total_delta = call_delta + put_delta
                total_sigma = call_sigma + put_sigma

                print(timezone.localtime().replace(microsecond=0))
                if cache.get(f"ONE_SIDE_EXIT_HOLD_{self.str_strategy_id}_{idx}", 0):
                    print("Hold Marked")
                print("INDEX:", idx)
                print(f"{Fore.GREEN}{ce_print} {Fore.RED}{pe_print}{Fore.WHITE}")
                print(
                    f"{Fore.GREEN}CALL DELTA: {round(call_delta, 2)} {Fore.RED}PUT DELTA: {round(put_delta, 2)} {Fore.WHITE}= Total: {round(total_delta, 2)}"  # noqa: E501
                )
                print(
                    f"{Fore.GREEN}CALL IV: {round(call_sigma, 2)} {Fore.RED}PUT IV: {round(put_sigma, 2)} {Fore.WHITE}= Total: {round(total_sigma, 2)}"  # noqa: E501
                )
                if difference_points <= 0 and stop_loss > 0:
                    exit_trigger = True
                    print("STOP LOSS")
                    break

                if idx == self.parameters_len - 1:
                    total_call_delta = 0
                    total_put_delta = 0

                    for v in tradingsymbols:
                        if v["ce_tradingsymbol"]:
                            total_call_delta += (
                                instruments[
                                    instruments["tradingsymbol"]
                                    == v["ce_tradingsymbol"]
                                ]
                                .iloc[0]
                                .delta
                            )
                        if v["pe_tradingsymbol"]:
                            total_put_delta += (
                                instruments[
                                    instruments["tradingsymbol"]
                                    == v["pe_tradingsymbol"]
                                ]
                                .iloc[0]
                                .delta
                            )

                    total_call_delta = total_call_delta / self.parameters_len
                    total_put_delta = total_put_delta / self.parameters_len

                    print()
                    print(
                        Fore.GREEN
                        + f"TOTAL CALL DELTA: {round(total_call_delta * 100, 2)}",
                        Fore.RED
                        + f"TOTAL PUT DELTA: {round(total_put_delta * 100 ,2)}"
                        + Fore.WHITE,
                        f"CE + PE TOTAL DELTA: {round((total_call_delta + total_put_delta) * 100, 2)}",
                    )
                    print()
                    del total_call_delta, total_put_delta
                del ce_tradingsymbol, pe_tradingsymbol

                if (
                    timezone.localtime().time() > self.exit_time
                    or self.str_strategy_id
                    not in cache.get("DEPLOYED_STRATEGIES", {}).keys()
                ):
                    exit_trigger = True
                    break

                ct = timezone.localtime()
                if ct.second % self.sleep_time == 0:
                    diff = (
                        ct.replace(microsecond=0)
                        + dt.timedelta(seconds=self.sleep_time)
                        - timezone.localtime()
                    ).total_seconds()
                else:
                    diff = (
                        ct.replace(
                            second=((ct.second // self.sleep_time) * self.sleep_time),
                            microsecond=0,
                        )
                        + dt.timedelta(seconds=self.sleep_time)
                        - timezone.localtime()
                    ).total_seconds()
                await asyncio.sleep(diff)

            print()
            if exit_trigger:
                break

    async def run_initialization(self):
        if timezone.localtime().time() <= dt.time(9, 15, 12):
            await asyncio.sleep(
                (
                    timezone.localtime().replace(
                        hour=9, minute=15, second=12, microsecond=0
                    )
                    - timezone.localtime()
                ).total_seconds()
            )

        self.initiate()

    async def get_conditions_and_strategies(self):
        strategies = []
        for row in self.parameters:
            if self.days_left in row["one_side_without_check_exit"]:
                strategies.append(self.one_side_without_check_exit)
            elif self.days_left in row["one_side_check_exit"]:
                strategies.append(self.one_side_check_exit)

        conditions = [row["day_wise"][str(self.days_left)] for row in self.parameters]

        return strategies, conditions

    async def get_entry_symbols(self, instruments: pd.DataFrame, delta: float):
        ce, pe = None, None
        # spot_price = cache.get(self.option_instrument_ltp_cache)

        ce_df = instruments[
            (instruments["delta"] > delta)
            & (instruments["delta"] < self.max_delta)
            & (instruments["option_type"] == "CE")
        ].sort_values("delta")

        if not ce_df.empty:
            ce = ce_df.iloc[0]

        pe_df = instruments[
            (instruments["delta"] < -delta)
            & (instruments["delta"] > -self.max_delta)
            & (instruments["option_type"] == "PE")
        ].sort_values("delta")

        print("CE DF")
        print(ce_df)

        print()

        print("PE DF")
        print(pe_df)

        if not pe_df.empty:
            pe = pe_df.iloc[-1]

        if pe.strike > ce.strike:
            ce_df = instruments[
                (instruments["strike"] == pe.strike)
                & (instruments["option_type"] == "CE")
            ]

            pe_df = instruments[
                (instruments["strike"] == ce.strike)
                & (instruments["option_type"] == "PE")
            ]

            ce = ce_df.iloc[0]
            pe = pe_df.iloc[0]

        return ce, pe

    async def place_entry_order(self, conditions):
        strategy_list = cache.get("DEPLOYED_STRATEGIES", {})
        strategy_list[self.str_strategy_id] = {
            "user_params": self.user_params,
            "no_of_strategy": self.parameters_len,
        }
        cache.set("DEPLOYED_STRATEGIES", strategy_list)

        while True:
            instruments = get_option_greeks_instruments(
                symbol=self.symbol,
                websocket_ids=self.websocket_ids,
            )
            tradingsymbols = [{} for _ in conditions]
            orders = []
            for idx, cond in enumerate(conditions):
                sell_pending, buy_pending = [], []
                # Setting CE and PE for entering based on delta
                ce, pe = await self.get_entry_symbols(
                    instruments, cond["min_delta"] / 100
                )

                if ce is None or pe is None:
                    print("ENTRY STRIKE NOT FOUND TRYING AFTER 10 SECONDS.")
                    await asyncio.sleep(10)
                    break

                sell_pending.extend(
                    [
                        self.pending_list_update(pe, idx, "ENTERING PE"),
                        self.pending_list_update(ce, idx, "ENTERING CE"),
                    ]
                )
                orders.append((sell_pending, buy_pending))
                ce_tradingsymbol, pe_tradingsymbol = ce.tradingsymbol, pe.tradingsymbol

                tradingsymbols[idx] = {
                    "ce_tradingsymbol": ce_tradingsymbol,
                    "pe_tradingsymbol": pe_tradingsymbol,
                    "exited_one_side": False,
                    "ce_exit_one_side": False,
                    "pe_exit_one_side": False,
                    "position_type": -1 if self.entry_type == "SELL" else 1,
                    "websocket_id": self.websocket_id,
                    "strategy_name": cond["name"],
                }
            else:
                cache.set(self.strategy_tradingsymbol_cache, tradingsymbols)
                for sell_pending, buy_pending in orders:
                    await self.place_order(
                        sell_pending=sell_pending,
                        buy_pending=buy_pending,
                    )
                # await send_notifications(
                #     self.opt_strategy.strategy_name.upper(),
                #     f"{self.opt_strategy.strategy_name} ALGO ENTERED!",
                #     "alert-success",
                # )
                break

        return True

    async def wait_before_execution(self):
        if timezone.localtime().time() <= self.entry_time:
            await asyncio.sleep(
                (
                    timezone.localtime().replace(
                        hour=self.entry_time.hour,
                        minute=self.entry_time.minute,
                        second=self.entry_time.second,
                        microsecond=0,
                    )
                    - timezone.localtime()
                ).total_seconds()
            )

        print(timezone.localtime().replace(microsecond=0))

    async def sleep_on_initial_run(self):
        ct = timezone.localtime()
        st = self.sleep_time * self.parameters_len
        if ct.second % st == 0:
            diff = (
                ct.replace(microsecond=0)
                + dt.timedelta(seconds=st)
                - timezone.localtime()
            ).total_seconds()
        else:
            diff = (
                ct.replace(second=((ct.second // st) * st), microsecond=0)
                + dt.timedelta(seconds=st)
                - timezone.localtime()
            ).total_seconds()
        del st, ct
        await asyncio.sleep(diff)

    async def run(self):
        await self.run_initialization()
        strategies, conditions = await self.get_conditions_and_strategies()

        if not self.entered:
            await self.wait_before_execution()
            self.entered = await self.place_entry_order(conditions)

        await self.sleep_on_initial_run()
        await self.run_strategy(strategies, conditions)
        await self.exit_algo()

    async def exit_algo(self):
        instruments = get_option_greeks_instruments(
            symbol=self.symbol,
            websocket_ids=self.websocket_ids,
        )
        if self.str_strategy_id in (cache.get("DEPLOYED_STRATEGIES", {})).keys():
            buy_pending, sell_pending = [], []

            tradingsymbols: dict = cache.get(self.strategy_tradingsymbol_cache, [])

            for idx, row in enumerate(tradingsymbols):
                if row["ce_tradingsymbol"] is not None:
                    ce = instruments[
                        (instruments["tradingsymbol"] == row["ce_tradingsymbol"])
                    ].iloc[0]
                    buy_pending.append(
                        self.pending_list_update(ce, idx, "EXIT CE - EXIT ALGO")
                    )

                if row["pe_tradingsymbol"] is not None:
                    ce = instruments[
                        (instruments["tradingsymbol"] == row["pe_tradingsymbol"])
                    ].iloc[0]
                    buy_pending.append(
                        self.pending_list_update(ce, idx, "EXIT CE - EXIT ALGO")
                    )

        cache.set(self.strategy_tradingsymbol_cache, {})
        strategy_list = cache.get("DEPLOYED_STRATEGIES", {})
        del strategy_list[self.str_strategy_id]
        cache.set("DEPLOYED_STRATEGIES", strategy_list)
        cache.delete(self.strategy_tradingsymbol_cache)

        await self.place_order(
            sell_pending=sell_pending,
            buy_pending=buy_pending,
        )

        try:
            await update_positions(broker=self.broker)
        except Exception as e:
            traceback.print_exc()
            print("GET POSITION ERROR", e)

        # await send_notifications(
        #     self.opt_strategy.strategy_name.upper(),
        #     "ALGO EXITED!",
        #     "alert-danger",
        # )

    # Manual
    async def manual_exit(self, idx, option_type):
        self.initiate()

        tradingsymbol = cache.get(self.strategy_tradingsymbol_cache, {})
        instruments = get_option_greeks_instruments(
            symbol=self.symbol,
            websocket_ids=self.websocket_ids,
        )
        row = tradingsymbol[idx]

        buy_pending = []
        sell_pending = []

        if option_type == "CE" and not row["exited_one_side"]:
            ce = instruments[
                (instruments["tradingsymbol"] == row["ce_tradingsymbol"])
            ].iloc[0]

            (
                buy_pending,
                ce_tradingsymbol,
                exited_one_side,
                ce_exit_one_side,
            ) = await self.get_ce_exit(idx, ce)

            tradingsymbol[idx]["ce_tradingsymbol"] = ce_tradingsymbol
            tradingsymbol[idx]["exited_one_side"] = exited_one_side
            tradingsymbol[idx]["ce_exit_one_side"] = ce_exit_one_side

        elif option_type == "PE" and not row["exited_one_side"]:
            pe = instruments[
                (instruments["tradingsymbol"] == row["pe_tradingsymbol"])
            ].iloc[0]

            (
                buy_pending,
                pe_tradingsymbol,
                exited_one_side,
                pe_exit_one_side,
            ) = await self.get_pe_exit(idx, pe)

            tradingsymbol[idx]["pe_tradingsymbol"] = pe_tradingsymbol
            tradingsymbol[idx]["exited_one_side"] = exited_one_side
            tradingsymbol[idx]["pe_exit_one_side"] = pe_exit_one_side

        cache.set(self.strategy_tradingsymbol_cache, tradingsymbol)

        await self.place_order(
            sell_pending=sell_pending,
            buy_pending=buy_pending,
        )
        try:
            await update_positions(broker=self.broker)
        except Exception:
            pass

    async def manual_reentry(self, idx):
        self.initiate()

        tradingsymbol = cache.get(self.strategy_tradingsymbol_cache, {})
        instruments = get_option_greeks_instruments(
            symbol=self.symbol,
            websocket_ids=self.websocket_ids,
        )
        row = tradingsymbol[idx]
        now_time = timezone.localtime()

        if row["exited_one_side"]:
            if row["ce_exit_one_side"]:
                pe = instruments[
                    (instruments["tradingsymbol"] == row["pe_tradingsymbol"])
                ].iloc[0]

                (
                    buy_pending,
                    sell_pending,
                    ce_tradingsymbol,
                    pe_tradingsymbol,
                    exited_one_side,
                    ce_exit_one_side,
                ) = await self.get_ce_reentry(idx, instruments, pe, now_time)

                await self.place_order(
                    sell_pending=sell_pending,
                    buy_pending=buy_pending,
                )

                tradingsymbol[idx]["ce_tradingsymbol"] = ce_tradingsymbol
                tradingsymbol[idx]["pe_tradingsymbol"] = pe_tradingsymbol
                tradingsymbol[idx]["exited_one_side"] = exited_one_side
                tradingsymbol[idx]["ce_exit_one_side"] = ce_exit_one_side
                cache.set(self.strategy_tradingsymbol_cache, tradingsymbol)
                cache.set(f"ONE_SIDE_EXIT_HOLD_{self.str_strategy_id}_{idx}", 1)

            elif row["pe_exit_one_side"]:
                ce = instruments[
                    (instruments["tradingsymbol"] == row["ce_tradingsymbol"])
                ].iloc[0]

                (
                    buy_pending,
                    sell_pending,
                    ce_tradingsymbol,
                    pe_tradingsymbol,
                    exited_one_side,
                    pe_exit_one_side,
                ) = await self.get_pe_reentry(idx, instruments, ce, now_time)

                tradingsymbol[idx]["ce_tradingsymbol"] = ce_tradingsymbol
                tradingsymbol[idx]["pe_tradingsymbol"] = pe_tradingsymbol
                tradingsymbol[idx]["exited_one_side"] = exited_one_side
                tradingsymbol[idx]["pe_exit_one_side"] = pe_exit_one_side
                cache.set(self.strategy_tradingsymbol_cache, tradingsymbol)
                cache.set(f"ONE_SIDE_EXIT_HOLD_{self.str_strategy_id}_{idx}", 1)

                await self.place_order(
                    sell_pending=sell_pending,
                    buy_pending=buy_pending,
                )

                try:
                    await update_positions(broker=self.broker)
                except Exception:
                    pass

    async def manual_shifting(self, idx):
        self.initiate()

        tradingsymbol = cache.get(self.strategy_tradingsymbol_cache, {})
        instruments = get_option_greeks_instruments(
            symbol=self.symbol,
            websocket_ids=self.websocket_ids,
        )
        row = tradingsymbol[idx]
        now_time = timezone.localtime()

        if not row["exited_one_side"]:
            pe = instruments[
                (instruments["tradingsymbol"] == row["pe_tradingsymbol"])
            ].iloc[0]
            ce = instruments[
                (instruments["tradingsymbol"] == row["ce_tradingsymbol"])
            ].iloc[0]
            (
                buy_pending,
                sell_pending,
                ce_tradingsymbol,
                pe_tradingsymbol,
            ) = await self.check_shifting_orders(
                instruments, idx, ce, pe, 0.1, now_time
            )

            tradingsymbol[idx]["ce_tradingsymbol"] = ce_tradingsymbol
            tradingsymbol[idx]["pe_tradingsymbol"] = pe_tradingsymbol
            cache.set(self.strategy_tradingsymbol_cache, tradingsymbol)

            await self.place_order(
                sell_pending=sell_pending,
                buy_pending=buy_pending,
            )

            try:
                await update_positions(broker=self.broker)
            except Exception:
                pass

    async def manual_shift_single_strike(self, idx, option_type, points):
        tradingsymbol = cache.get(self.strategy_tradingsymbol_cache, {})
        instruments = get_option_greeks_instruments(
            symbol=self.symbol,
            websocket_ids=self.websocket_ids,
        )
        row = tradingsymbol[idx]

        buy_pending, sell_pending = [], []

        if option_type == "CE" and not row["ce_exit_one_side"]:
            ce = instruments[
                (instruments["tradingsymbol"] == row["ce_tradingsymbol"])
            ].iloc[0]
            buy_pending.append(
                self.pending_list_update(ce, idx, "MANUAL SINGLE SIDE SHIFT - EXIT")
            )
            ce = instruments[
                (instruments["strike"] == (ce["strike"] - points))
                & (instruments["option_type"] == "CE")
            ].iloc[0]
            sell_pending.append(
                self.pending_list_update(ce, idx, "MANUAL SINGLE SIDE SHIFT - ENTRY")
            )

            tradingsymbol[idx]["ce_tradingsymbol"] = ce["tradingsymbol"]

        elif option_type == "PE" and not row["pe_exit_one_side"]:
            pe = instruments[
                (instruments["tradingsymbol"] == row["pe_tradingsymbol"])
            ].iloc[0]
            buy_pending.append(
                self.pending_list_update(pe, idx, "MANUAL SINGLE SIDE SHIFT - EXIT")
            )
            pe = instruments[
                (instruments["strike"] == (pe["strike"] + points))
                & (instruments["option_type"] == "PE")
            ].iloc[0]
            sell_pending.append(
                self.pending_list_update(pe, idx, "MANUAL SINGLE SIDE SHIFT - ENTRY")
            )

            tradingsymbol[idx]["pe_tradingsymbol"] = pe["tradingsymbol"]
        cache.set(self.strategy_tradingsymbol_cache, tradingsymbol)

        await self.place_order(
            sell_pending=sell_pending,
            buy_pending=buy_pending,
        )

        try:
            await update_positions(broker=self.broker)
        except Exception:
            pass

    async def release_one_side_exit_hold(self, idx):
        cache.set(f"ONE_SIDE_EXIT_HOLD_{self.str_strategy_id}_{idx}", 0)

    async def one_side_exit_hold(self, idx):
        cache.set(f"ONE_SIDE_EXIT_HOLD_{self.str_strategy_id}_{idx}", 1)

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

        # for user_param_user_obj in user_param_user_obj_list:
        #     await send_notifications(
        #         self.opt_strategy.strategy_name.upper(),
        #         f"{user_param_user_obj['user'].username} ALGO ENTRED!".upper(),
        #         "alert-success",
        #     )

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

        # for user_param_user_obj in user_param_user_obj_list:
        #     await send_notifications(
        #         self.opt_strategy.strategy_name.upper(),
        #         f"{user_param_user_obj['user'].username} ALGO ENTRED!".upper(),
        #         "alert-success",
        #     )
