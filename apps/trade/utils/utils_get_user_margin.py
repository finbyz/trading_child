import pandas as pd
from django.core.cache import cache


async def get_user_margin(broker=None):
    if broker == "kotak_neo":
        df = pd.DataFrame(cache.get("KOTAK_NEO_MARGIN"))
        df["broker"] = broker
        return df
