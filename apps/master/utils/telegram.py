import contextlib

import requests

from trading.settings import TELEGRAM_API_TOKEN, TELEGRAM_CHAT_ID


def send_telegram_message(message):
    if TELEGRAM_API_TOKEN and TELEGRAM_CHAT_ID:
        apiURL = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"

        with contextlib.suppress(Exception):
            requests.post(apiURL, json={"chat_id": TELEGRAM_CHAT_ID, "text": message})
