import json
from datetime import date, datetime

from apps.integration.models import BrokerApi as BrokerApiModel
from apps.integration.models import KotakNeoApi as KotakNeoApiModel
from apps.integration.utils.broker.kotak_neo import KotakNeoApi
from apps.trade.models import Order as OrderModel


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


async def update_daily_order_book():
    users = [
        {
            "username": row.broker_api.user.username,
            "headers": {
                "Authorization": f"Bearer {row.access_token}",
                "Sid": row.sid,
                "Auth": row.auth,
                "neo-fin-key": row.neo_fin_key,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            "query_params": {"sId": row.hs_server_id},
        }
        for row in KotakNeoApiModel.objects.all()
    ]

    knapi = KotakNeoApi(users=users)

    order_book = await knapi.order_report()
    trade_book = await knapi.trade_report()

    # return trade_book

    for ob in sorted(
        order_book,
        key=lambda d: (d["order_timestamp"], d["order_id"], d["username"]),
    ):
        obj = OrderModel.objects.filter(
            order_id=ob["order_id"], broker_api__user__username=ob["username"]
        ).first()

        if not obj:
            obj = OrderModel()
            obj.broker_api = BrokerApiModel.objects.filter(
                user__username=ob["username"], broker="kotak_neo"
            ).first()
            obj.order_id = ob["order_id"]

        obj.tradingsymbol = ob["tradingsymbol"]
        obj.product = ob["product"]
        obj.status = ob["status"]
        obj.transaction_type = ob["transaction_type"]
        obj.price = ob["price"]
        obj.average_price = ob["average_price"]
        obj.quantity = ob["quantity"]
        obj.filled_quantity = ob["filled_quantity"]
        obj.pending_quantity = ob["pending_quantity"]
        obj.cancelled_quantity = ob["cancelled_quantity"]
        obj.order_timestamp = ob["order_timestamp"]
        obj.tag = ob["tag"]

        trade_report = list(
            filter(
                lambda d: d["order_id"] == ob["order_id"]
                and d["username"] == ob["username"],
                trade_book,
            )
        )
        obj.trade_report = json.loads(json.dumps(trade_report, cls=DateTimeEncoder))
        obj.is_order_updated = True
        obj.save()
