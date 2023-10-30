import csv
import hashlib
import re
from functools import lru_cache
from typing import Any

import pyotp
from aiohttp import ClientSession
from dateutil.parser import parse
from six import StringIO


class KiteLoginError(Exception):
    def __init__(self, message: Any) -> None:
        self.message = message

        return super().__init__(self.message)


class KiteApi(object):
    def __init__(
        self,
        user_id: str,
        url: str = "https://api.kite.trade",
    ) -> None:
        self.user_id = user_id
        self.url = url

    async def login_first_step(
        self,
        session: ClientSession,
        password: str,
    ) -> None:
        response = await session.request(
            method="POST",
            url=f"{self.url}/api/login",
            data={
                "user_id": self.user_id,
                "password": password,
            },
        )

        response_json = await response.json()

        if response_json["status"] == "error":
            raise KiteLoginError(response_json)

        self.request_id = response_json["data"]["request_id"]

    async def login_second_step(
        self,
        session: ClientSession,
        request_id: str,
        twofa: str,
    ) -> None:
        response = await session.request(
            method="POST",
            url=f"{self.url}/api/twofa",
            data={
                "request_id": request_id,
                "twofa_value": twofa,
                "user_id": self.user_id,
            },
        )

        response_json = await response.json()

        if response_json["status"] == "error":
            raise KiteLoginError(response_json)

        self.enctoken = response.cookies.get("enctoken").value

    async def login(
        self,
        password: str,
        twofa: str,
    ) -> None:
        async with ClientSession() as session:
            await self.login_first_step(session, password)
            await self.login_second_step(
                session,
                self.request_id,
                pyotp.TOTP(twofa).now(),
            )

    async def instruments(self, enctoken: str, exchange=None):
        self.enctoken = enctoken
        exchange = "" if exchange is None else f"/{exchange}"

        async with ClientSession() as session:
            response = await session.request(
                method="GET",
                url=f"{self.url}/instruments{exchange}",
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {self.enctoken}",
                },
            )

            if re.search("csv", response.headers["Content-Type"], re.IGNORECASE):
                resp = await response.text()
                return self._parse_instruments(resp)

        raise KiteLoginError(await response.text())

    def _parse_instruments(self, data):
        # Decode unicode data
        if isinstance(data, bytes):
            data = data.decode("utf-8").strip()

        records = []
        reader = csv.DictReader(StringIO(data))

        for row in reader:
            self._set_insreument_records(row, records)
        return records

    def _set_insreument_records(self, row, records):
        row["instrument_token"] = int(row["instrument_token"])
        row["strike"] = float(row["strike"])
        row["tick_size"] = float(row["tick_size"])
        row["lot_size"] = int(row["lot_size"])
        row["option_type"] = row.pop("instrument_type")
        row["expiry"] = self._parse_date(row["expiry"])
        row.pop("last_price")

        records.append(row)

    @lru_cache(maxsize=128)
    def _parse_date(self, date):
        return parse(date).date() if len(date) == 10 else date


class KiteRealApi(object):
    def __init__(
        self,
        api_key: str,
        url: str = "https://api.kite.trade",
    ) -> None:
        self.api_key = api_key
        self.url = url

    async def generate_session(self, request_token, api_secret):
        h = hashlib.sha256(
            self.api_key.encode("utf-8")
            + request_token.encode("utf-8")
            + api_secret.encode("utf-8")
        )
        checksum = h.hexdigest()
        url = f"{self.url}/session/token"

        async with ClientSession() as session:
            response = await session.request(
                method="POST",
                url=url,
                data={
                    "api_key": self.api_key,
                    "request_token": request_token,
                    "checksum": checksum,
                },
            )

            response_json = await response.json()

            if response_json["status"] == "error":
                raise KiteLoginError(response_json)

            self.access_token = response_json["data"]["access_token"]
