import datetime as dt

import pandas as pd
from django.core.cache import cache
from django.utils import timezone

from apps.trade.models import DeployedOptionStrategy as DeployedOptionStrategyModel


def get_premium(stop_loss_delta, df):
    ce_df = df[df["option_type"] == "CE"]
    pe_df = df[df["option_type"] == "PE"]

    ce_premium = (
        ce_df[ce_df["delta"] >= stop_loss_delta]
        .sort_values("delta", ascending=True)
        .iloc[0]
        .last_price
    )
    pe_premium = (
        pe_df[pe_df["delta"] <= -stop_loss_delta]
        .sort_values("delta", ascending=False)
        .iloc[0]
        .last_price
    )

    return ce_premium + pe_premium


def get_df(instrument, websocket_id=1):
    df = cache.get(
        f"{instrument}_{websocket_id}_OPTION_GREEKS_INSTRUMENTS", pd.DataFrame()
    )

    return df


def caclulate_stop_loss(expiry, max_stop_loss, stop_loss_percent, total_premium):
    today = timezone.localdate()

    return (
        min(
            round(total_premium * stop_loss_percent[(expiry - today).days]),
            max_stop_loss[(expiry - today).days],
        )
        if max_stop_loss
        else round(total_premium * stop_loss_percent[(expiry - today).days])
    ) + 15


def get_stop_loss(expiry, max_stop_loss, stop_loss_percent, stop_loss_delta, df):
    if (not expiry and max_stop_loss) or df.empty:
        return max(max_stop_loss)

    elif expiry and (max_stop_loss and not stop_loss_percent):
        return max_stop_loss[(expiry - timezone.localdate()).days]

    elif expiry and stop_loss_percent:
        if not df.empty:
            return caclulate_stop_loss(
                expiry,
                max_stop_loss,
                stop_loss_percent,
                get_premium(stop_loss_delta, df),
            )


def set_stop_loss(pk, expiry, max_stop_loss, stop_loss_percent, stop_loss_delta, df):
    stop_losses = cache.get("OPTION_STRATEGIES_STOP_LOSSES", {})
    stop_losses[pk] = get_stop_loss(
        expiry,
        max_stop_loss,
        stop_loss_percent,
        stop_loss_delta,
        df,
    )
    cache.set("OPTION_STRATEGIES_STOP_LOSSES", stop_losses)


def calculate_option_strategy_stop_loss():
    for deployed_strategy in DeployedOptionStrategyModel.objects.filter(is_active=True):
        match deployed_strategy.strategy.strategy_type:
            case "delta_management":
                webocket_id = deployed_strategy.websocket_ids.split(",")[0]
                set_stop_loss(
                    deployed_strategy.pk,
                    cache.get(
                        f"{deployed_strategy.instrument.symbol}_EXPIRY_MAP", {}
                    ).get(webocket_id),
                    deployed_strategy.options.get("max_stop_loss", []),
                    deployed_strategy.options.get("stop_loss_percent", []),
                    deployed_strategy.options.get("stop_loss_delta", 45) / 100,
                    get_df(deployed_strategy.instrument, websocket_id=1),
                )
