import numpy as np
import pandas as pd
from django.core.cache import cache


def get_pe_ce_oi_change(
    underlying: str,
    websocket_id: str,
    difference_list: list,
):
    extra_columns = []
    df = cache.get(
        f"LIVE_{underlying}_{websocket_id}_PCR",
        pd.DataFrame(columns=["timestamp", "pe_total_oi", "ce_total_oi", "pcr"]),
    )
    for diff in difference_list:
        df[f"ce_oi_change_{diff}"] = df["ce_total_oi"].pct_change(periods=diff)
        df[f"pe_oi_change_{diff}"] = df["pe_total_oi"].pct_change(periods=diff)
        df[f"ce_minus_pe_oi_change_{diff}"] = (
            df[f"ce_oi_change_{diff}"] - df[f"pe_oi_change_{diff}"]
        )
        df[f"pe_minus_ce_oi_change_{diff}"] = (
            df[f"ce_oi_change_{diff}"] - df[f"pe_oi_change_{diff}"]
        )
        df[f"ce_minus_pe_oi_change_{diff}_update"] = np.where(
            (df[f"ce_minus_pe_oi_change_{diff}"].diff().abs() > 0.001),
            np.nan,
            df[f"ce_minus_pe_oi_change_{diff}"],
        )
        df[f"ce_minus_pe_oi_change_{diff}_update"] = (
            df[f"ce_minus_pe_oi_change_{diff}_update"].fillna(method="ffill").fillna(0)
        )
        df[f"pe_minus_ce_oi_change_{diff}_update"] = (
            df[f"ce_minus_pe_oi_change_{diff}_update"] * -1
        )
        df[f"ce_oi_abs_change_{diff}"] = df[f"ce_total_oi"].diff(periods=diff)
        df[f"pe_oi_abs_change_{diff}"] = df[f"pe_total_oi"].diff(periods=diff)
        df[f"pe_by_ce_oi_abs_change_{diff}"] = (
            df[f"pe_oi_abs_change_{diff}"]
            / df[f"ce_oi_abs_change_{diff}"].replace(0, np.nan)
        ).fillna(0.0)

        extra_columns.extend(
            [
                f"ce_oi_change_{diff}",
                f"pe_oi_change_{diff}",
                f"ce_minus_pe_oi_change_{diff}",
                f"pe_minus_ce_oi_change_{diff}",
                f"ce_minus_pe_oi_change_{diff}_update",
                f"pe_minus_ce_oi_change_{diff}_update",
                f"ce_oi_abs_change_{diff}",
                f"pe_oi_abs_change_{diff}",
                f"pe_by_ce_oi_abs_change_{diff}",
            ]
        )

    return df[
        [
            "timestamp",
            "pe_total_oi",
            "ce_total_oi",
            "pcr",
            "strike",
            "pe_iv",
            "ce_iv",
            "total_iv",
            "pe_premium",
            "ce_premium",
            "total_premium",
        ]
        + extra_columns
    ]
