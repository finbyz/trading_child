import os

from django.core.cache import cache

from apps.integration.models import KiteApi as KiteApiModel
from apps.integration.utils.kiteticker import KiteExtTicker, KiteTicker


def get_kws_object(websocket_id: str = "1") -> KiteTicker | KiteExtTicker:
    """
    This is a function to get KiteTicker or KiteExtTicker object based on the environment variables.
    Thus Function help to get ticker object to connect to kite websocket.

    Args:
        websocket_id (str, optional): Websocket id. Defaults to "1".

    Returns:
        KiteTicker | KiteExtTicker: Websocket Object
    """

    # If From Kite Api Login method
    if os.getenv(f"KITE_API_LOGIN_{websocket_id}", "False") == "True":
        return KiteTicker(
            api_key=os.environ[f"KITE_API_KEY_{websocket_id}"],
            access_token=cache.get(f"KITE_API_ACCESS_TOKEN_{websocket_id}"),
        )

    # If From KiteExt Api Login method
    user = os.environ[f"KITE_WEBSOCKET_USER_{websocket_id}"]
    kite = KiteApiModel.objects.get(broker_api__user__username=user)
    return KiteExtTicker(user_id=kite.user_id, enctoken=kite.enctoken)
