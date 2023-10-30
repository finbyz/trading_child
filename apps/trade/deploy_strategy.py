import math
import traceback

from django.core.cache import cache
from django.db.models import Q
from django.utils.module_loading import import_string

from apps.integration.utils import divide_and_list
from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel
from apps.trade.strategies.short_long_straddle_strangle import (
    Strategy as ShortLongStraddleStrangleStrategy,
)


# Straddle Strangle Strategy - Entry
async def entry_straddle_strangle(strategy_name, tradingsymbols):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy: ShortLongStraddleStrangleStrategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy
            await strategy.place_entry_order(tradingsymbols)
    except Exception as e:
        traceback.print_exc()


# Straddle Strangle Strategy - Exit
async def exit_straddle_strangle(strategy_name):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy: ShortLongStraddleStrangleStrategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy
            await strategy.place_exit_order()
    except Exception as e:
        traceback.print_exc()


async def run_delta_management_strategy(strategy_name):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy

            await strategy.run()
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def shift_single_strike_delta_management_strategy(
    strategy_name,
    idx,
    option_type,
    points,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy

            await strategy.manual_shift_single_strike(idx, option_type, points)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def rebalance_delta_management_strategy(
    strategy_name,
    idx,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy

            await strategy.manual_shifting(idx)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def exit_one_side_delta_management_strategy(
    strategy_name,
    idx,
    option_type,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy

            await strategy.manual_exit(idx, option_type)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def reentry_one_side_delta_management_strategy(
    strategy_name,
    idx,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy

            await strategy.manual_reentry(idx)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def release_one_side_exit_hold_delta_management_strategy(
    strategy_name,
    idx,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy

            await strategy.release_one_side_exit_hold(idx)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def one_side_exit_hold_delta_management_strategy(
    strategy_name,
    idx,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy

            await strategy.one_side_exit_hold(idx)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def exit_delta_management_strategy(
    strategy_name,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            del opt_strategy

            await strategy.exit_algo()
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def users_entry_delta_management_strategy(
    strategy_name,
    data,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            data = [(row["username"], row["broker"]) for row in data]

            del opt_strategy

            await strategy.users_entry(data)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def users_entry_single_straddle_strangle(
    strategy_name,
    data,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            data = [(row["username"], row["broker"]) for row in data]

            del opt_strategy

            await strategy.users_entry(data)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def users_exit_delta_management_strategy(
    strategy_name,
    data,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            data = [(row["username"], row["broker"]) for row in data]

            del opt_strategy

            await strategy.users_exit(data)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def users_exit_single_straddle_strangle(
    strategy_name,
    data,
):
    try:
        opt_strategy = DeployedOptionStrategyModel.objects.get(
            strategy_name=strategy_name
        )
        Strategy = import_string(
            f"apps.trade.strategies.{opt_strategy.strategy.file_name}.Strategy"
        )

        if opt_strategy.is_active:
            strategy = Strategy(
                strategy_id=opt_strategy.pk,
            )

            data = [(row["username"], row["broker"]) for row in data]

            del opt_strategy

            await strategy.users_exit(data)
    except Exception as e:
        traceback.print_exc()
        # await send_alert_notifications(str(e), traceback.format_exc())


async def update_strategy_quantity(strategy_name, username, broker, qty):
    opt_strategy = DeployedOptionStrategyModel.objects.get(strategy_name=strategy_name)

    if user_obj := opt_strategy.users.filter(
        broker_api__user__username=username, broker_api__broker=broker
    ).first():
        user_obj.lots = math.ceil(float(qty) / float(opt_strategy.lot_size))
        user_obj.save()

        if opt_strategy.is_active:
            parameters_count = (
                opt_strategy.parameters.filter(is_active=True).count() or 1
            )

            user_params = (
                cache.get("DEPLOYED_STRATEGIES", {})
                .get(str(opt_strategy.pk), {})
                .get("user_params", [])
            )
            user_exists = False

            for user_idx, row in enumerate(user_params):
                if row["user"].username == username and row["broker"] == broker:
                    user_exists = True
                    user_index = user_idx
                    break

            if user_exists:
                strategy_list = cache.get("DEPLOYED_STRATEGIES", {})

                user_params[user_index]["quantity_multiple"] = [
                    item * opt_strategy.lot_size
                    for item in divide_and_list(parameters_count, user_obj.lots)
                ]
                strategy_list[str(opt_strategy.pk)]["user_params"] = user_params

                cache.set("DEPLOYED_STRATEGIES", strategy_list)


async def update_strategy_quantity_percentage(strategy_name, qty_percentage):
    opt_strategy = DeployedOptionStrategyModel.objects.get(strategy_name=strategy_name)

    users = opt_strategy.users.filter(
        Q(is_active=True) & ~Q(broker_api__broker="dummy")
    )

    qty_percentage = int(qty_percentage) / 100
    parameters_count = opt_strategy.parameters.filter(is_active=True).count() or 1

    user_update_qty_map = {}

    for user in users:
        user_update_qty_map[user.broker_api.user.username] = (
            int((user.lots * qty_percentage))
        ) or parameters_count

    strategy_list = cache.get("DEPLOYED_STRATEGIES", {})
    user_params = strategy_list[str(opt_strategy.pk)]["user_params"]

    for user_param in user_params:
        updated_qty = (
            user_update_qty_map.get(user_param["user"].username) or parameters_count
        )
        user_param["quantity_multiple"] = [
            item * opt_strategy.lot_size
            for item in divide_and_list(parameters_count, updated_qty)
        ]

    cache.set("DEPLOYED_STRATEGIES", strategy_list)
