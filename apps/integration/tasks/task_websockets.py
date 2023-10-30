import time

from dateutil.parser import parse
from django.utils import timezone

from apps.integration.tasks.sockets import run_option_websocket, run_spot_websocket
from trading.settings import UNDERLYINGS


def websockets() -> None:
    tz = timezone.get_current_timezone()
    run_spot_websocket()
    for underlying in UNDERLYINGS:
        run_option_websocket(underlying)

    exit_time = parse(f"{timezone.localdate()} 15:31:00").replace(tzinfo=tz)
    ct = timezone.localtime()

    if ct <= exit_time:
        time.sleep((exit_time - ct).total_seconds())
