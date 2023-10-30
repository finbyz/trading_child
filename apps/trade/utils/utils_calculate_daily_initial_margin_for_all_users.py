import asyncio

from django.core.cache import cache

from apps.integration.models import BrokerApi as BrokerApiModel
from apps.integration.models import InitialMargin as InitialMarginModel


async def calculate_initial_margin_for_user(broker_api: BrokerApiModel):
    if (
        initial_margin_obj := InitialMarginModel.objects.filter(broker_api=broker_api)
        .order_by("-date")
        .first()
    ):
        return {
            "username": broker_api.user.get_username(),
            "broker": broker_api.broker,
            "initial_margin": round(float(initial_margin_obj.margin), 2),
        }

    return {
        "username": broker_api.user.get_username(),
        "broker": broker_api.broker,
        "initial_margin": 0.0,
    }


async def calculate_daily_initial_margin_for_all_users():
    data = []

    data = await asyncio.gather(
        *[
            calculate_initial_margin_for_user(broker_api)
            for broker_api in BrokerApiModel.objects.filter(
                is_active=True,
            )
        ]
    )

    cache.set("USERS_MARGIN", data)
