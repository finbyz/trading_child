from apps.integration.models import KiteApi as KiteApiModel
from apps.integration.models import KotakNeoApi as KotakNeoApiModel


def save_broker_models() -> None:
    for kite in KiteApiModel.objects.filter(broker_api__is_active=True):
        kite.save()

    for kotak_neo in KotakNeoApiModel.objects.filter(broker_api__is_active=True):
        kotak_neo.save()
