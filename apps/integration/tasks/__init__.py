from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.integration.tasks.task_broker_models import (
    save_broker_models,
    update_kotak_neo_token,
)
from apps.integration.tasks.task_kite_api_login import kite_api_login
from apps.integration.tasks.task_map_option_instruments import map_option_instruments
from apps.integration.tasks.task_option_calculation_and_snapshot import (
    option_calculation_and_snapshot,
)
from apps.integration.tasks.task_update_weekend_of_year import update_weekend_of_year
from apps.integration.tasks.task_websockets import websockets
from trading import celery_app as app


@app.task(name="Update Weekends in Holiday List", bind=True)
def update_weekend_of_year_task(self):
    return update_weekend_of_year()


@app.task(name="Kite Login Api", bind=True)
def kite_api_login_task(self):
    return kite_api_login()


@app.task(name="Save Broker Models", bind=True)
def save_broker_models_task(self):
    return save_broker_models()


@app.task(name="Update Kotak Neo Token", bind=True)
def update_kotak_neo_token_task(self):
    return update_kotak_neo_token()


@app.task(name="Map Option Instruments", bind=True)
def map_option_instruments_task(self):
    return async_to_sync(map_option_instruments)()


@app.task(name="Websocket", bind=True, queue="websockets")
def websockets_task(self):
    return websockets()


@app.task(
    name="Option Calculation and Snapshot",
    bind=True,
    queue="option_calculation_and_snapshot",
)
def option_calculation_and_snapshot_task(self):
    return option_calculation_and_snapshot()
