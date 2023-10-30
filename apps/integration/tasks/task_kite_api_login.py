import os
import time
from urllib.parse import parse_qs, urlparse

import pyotp
from asgiref.sync import async_to_sync
from django.core.cache import cache
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

from apps.integration.utils.broker_login import KiteRealApi


def kite_api_login():
    for websocket_id in os.getenv("WEBSOCKET_IDS", "").split(","):
        if os.getenv(f"KITE_API_LOGIN_{websocket_id}", "False") == "True":
            api_key = os.getenv(f"KITE_API_KEY_{websocket_id}")
            api_secret = os.getenv(f"KITE_API_SECRET_{websocket_id}")
            kite_username = os.getenv(f"KITE_API_USERNAME_{websocket_id}")
            kite_password = os.getenv(f"KITE_API_PASSWORD_{websocket_id}")
            kite_twofa = os.getenv(f"KITE_API_TWOFA_{websocket_id}")

            service = Service("/usr/bin/chromedriver")

            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.binary_location = "/usr/bin/chromium-browser"
            driver = webdriver.Chrome(service=service, options=options)
            driver.get(f"https://kite.zerodha.com/connect/login?api_key={api_key}")
            driver.implicitly_wait(2)
            username = driver.find_element(value="userid")
            password = driver.find_element(value="password")
            username.send_keys(kite_username)
            password.send_keys(kite_password)
            driver.find_element(
                By.XPATH,
                "/html/body/div[1]/div/div[2]/div[1]/div/div/div[2]/form/div[4]/button",
            ).click()
            pin = driver.find_element(By.XPATH, '//input[@label="External TOTP"]')
            pin.send_keys(str(pyotp.TOTP(kite_twofa).now()))
            driver.implicitly_wait(10)
            time.sleep(5)
            request_token = parse_qs(urlparse(driver.current_url).query)[
                "request_token"
            ][0]

            kite = KiteRealApi(api_key=api_key)
            async_to_sync(kite.generate_session)(request_token, api_secret=api_secret)

            cache.set(f"KITE_API_ACCESS_TOKEN_{websocket_id}", kite.access_token)

            driver.close()
