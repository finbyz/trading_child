from apps.integration.models import KiteApi as KiteApiModel
from apps.integration.models import KotakNeoApi as KotakNeoApiModel


def save_broker_models() -> None:
    for kite in KiteApiModel.objects.filter(broker_api__is_active=True):
        kite.save()

    for kotak_neo in KotakNeoApiModel.objects.filter(broker_api__is_active=True):
        kotak_neo.save()


def update_kotak_neo_token():
    for kotak_neo in KotakNeoApiModel.objects.filter(broker_api__is_active=True):
        kotak_neo.update_auth_token = True
        kotak_neo.save()
