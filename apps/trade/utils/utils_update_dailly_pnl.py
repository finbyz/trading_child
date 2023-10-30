from django.utils import timezone
from django_pandas.io import read_frame

from apps.integration.models import BrokerApi as BrokerApiModel
from apps.integration.models import InitialMargin as InitialMarginModel
from apps.trade.models import DailyPnl as DailyPnlModel
from apps.trade.models import Order as OrderModel


def caclulate_option_brokerage(buy, sell, brokerage):
    stt = round((0.0625 / 100) * sell)
    stamp_duty = round((0.003 / 100) * buy)

    transaction_charges = round((0.05 / 100) * (sell + buy), 2)
    sebi_fees = round((0.0001 / 100) * (sell + buy), 2)
    ipft = round((0.0005 / 100) * (sell + buy), 2)

    charges = round(transaction_charges + sebi_fees + ipft, 2)

    gst = round(round((brokerage * 18 / 100), 2) + round(((charges) * 18 / 100), 2), 2)

    total_brokerage = charges + brokerage + gst + stt + stamp_duty

    return total_brokerage


def update_daily_pnl(date):
    for broker_api in BrokerApiModel.objects.filter(broker__in=["kotak_neo"]):
        df = read_frame(
            OrderModel.objects.filter(
                broker_api=broker_api,
                order_timestamp__date=date,
            )
        )

        df = df[
            (df["tradingsymbol"].str.contains("BANKNIFTY"))
            & (
                df["tradingsymbol"].str.contains("CE")
                | df["tradingsymbol"].str.contains("PE")
            )
        ].copy()

        if not df.empty:
            brokerage = 0.01 * len(df["tradingsymbol"].unique())
            buy = float(df[df["transaction_type"] == "BUY"].trade_value.sum())
            sell = float(df[df["transaction_type"] == "SELL"].trade_value.sum())
            gross_pnl = sell - buy
            charges = caclulate_option_brokerage(buy, sell, brokerage)

            daily_pnl_obj = DailyPnlModel.objects.filter(
                broker_api=broker_api, date=date
            ).first()

            if not daily_pnl_obj:
                daily_pnl_obj = DailyPnlModel()
                daily_pnl_obj.broker_api = broker_api
                daily_pnl_obj.date = date

            daily_pnl_obj.gross_pnl = gross_pnl
            daily_pnl_obj.charges = charges

            if (
                initial_margin := InitialMarginModel.objects.filter(
                    broker_api=broker_api, date__lte=date
                )
                .order_by("-date")
                .first()
            ):
                initial_margin = initial_margin.margin
            else:
                initial_margin = 0
            daily_pnl_obj.initial_margin = initial_margin

            daily_pnl_obj.save()
