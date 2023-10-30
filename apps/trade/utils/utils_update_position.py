import asyncio

from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.integration.models import BrokerApi as BrokerApiModel
from apps.integration.models import KotakNeoApi as KotakNeoApiModel
from apps.integration.utils.broker.dummy import DummyApi
from apps.integration.utils.broker.kotak_neo import KotakNeoApi

User = get_user_model()


async def update_dummy_positions():
    users = [
        row.user
        for row in BrokerApiModel.objects.filter(broker="dummy", is_active=True)
    ]

    dummyapi = DummyApi(users=users)
    positions = await dummyapi.positions()
    cache.set("DUMMY_POSITIONS", positions)


async def update_kotak_neo_positions():
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
        for row in KotakNeoApiModel.objects.filter(broker_api__is_active=True)
    ]

    knapi = KotakNeoApi(users=users)

    positions = await knapi.postions()
    margin = await knapi.margin()

    cache.set("KOTAK_NEO_POSITIONS", positions)
    cache.set("KOTAK_NEO_MARGIN", margin)


async def update_positions(
    broker: str | None = None,
):
    match broker:
        case "kotak_neo":
            await asyncio.gather(
                update_dummy_positions(),
                update_kotak_neo_positions(),
            )

        case _:
            await asyncio.gather(
                update_dummy_positions(),
                update_kotak_neo_positions(),
            )
