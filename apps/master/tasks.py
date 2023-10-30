from apps.master.utils.telegram import send_telegram_message
from trading import celery_app as app


@app.task(name="Send Telegram Message", bind=True)
def send_telegram_message_task(self, message):
    return send_telegram_message(message)
