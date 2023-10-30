import base64
import csv
import datetime as dt
import json
from functools import lru_cache
from typing import Any
from urllib.request import urlopen

from aiohttp import ClientSession
from dateutil.relativedelta import relativedelta


class GenerateAccessTokenError(Exception):
    def __init__(self, message: Any) -> None:
        self.message = message

        return super().__init__(self.message)


class KotakNeoLoginError(Exception):
    def __init__(self, message: Any) -> None:
        self.message = message

        return super().__init__(self.message)


class KotakNeoUpdateTokenError(Exception):
    def __init__(self, message: Any) -> None:
        self.message = message

        return super().__init__(self.message)


class KotakNeoApi(object):
    __slots__ = (
        "neo_fin_key",
        "consumer_key",
        "consumer_secret",
        "access_token",
        "url",
        "auth",
        "sid",
        "hs_server_id",
        "rid",
    )

    def __init__(
        self,
        neo_fin_key: str,
        consumer_key: str,
        consumer_secret: str,
        access_token: str | None = None,
        auth: str | None = None,
        sid: str | None = None,
        hs_server_id: str | None = None,
        url: str = "https://gw-napi.kotaksecurities.com",
    ) -> None:
        self.neo_fin_key = neo_fin_key
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.access_token = access_token
        self.sid = sid
        self.auth = auth
        self.neo_fin_key = neo_fin_key
        self.hs_server_id = hs_server_id
        self.url = url

    async def generate_access_token(self, session: ClientSession) -> None:
        """Generate access token for the session."""

        response = await session.request(
            method="POST",
            url="https://napi.kotaksecurities.com/oauth2/token",
            headers={
                "Authorization": f'Basic {base64.b64encode(f"{self.consumer_key}:{self.consumer_secret}".encode()).decode()}',
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data="grant_type=client_credentials",
        )
        resp = await response.json()

        if response.status in [200, 201]:
            self.access_token = resp["access_token"]

            return

        raise GenerateAccessTokenError(resp)

    async def login_first_step(
        self,
        session: ClientSession,
        url: str,
        mobile_number: str | None,
        pan_number: str | None,
        password: str,
    ) -> None:
        """Login first step. With Password"""

        headers = {
            "accept": "*/*",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        payload = (
            json.dumps(
                {
                    "pan": pan_number,
                    "password": password,
                }
            )
            if pan_number
            else json.dumps(
                {
                    "mobileNumber": mobile_number,
                    "password": password,
                }
            )
        )

        response = await session.request(
            method="POST",
            url=url,
            headers=headers,
            data=payload,
        )

        resp = await response.json()

        if response.status in [200, 201]:
            self.auth = resp["data"]["token"]
            self.sid = resp["data"]["sid"]
            return

        raise KotakNeoLoginError(resp)

    async def login_second_step(
        self,
        session: ClientSession,
        url: str,
        mobile_number: str | None,
        pan_number: str | None,
        mpin: str,
    ) -> None:
        """Login second step. With MPIN"""

        headers = {
            "accept": "*/*",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "Auth": self.auth,
            "sid": self.sid,
        }
        payload = (
            json.dumps(
                {
                    "pan": pan_number,
                    "mpin": mpin,
                }
            )
            if pan_number
            else json.dumps(
                {
                    "mobileNumber": mobile_number,
                    "mpin": mpin,
                }
            )
        )

        response = await session.request(
            method="POST",
            url=url,
            headers=headers,
            data=payload,
        )

        resp = await response.json()

        if response.status in [200, 201]:
            self.sid = resp["data"]["sid"]
            self.auth = resp["data"]["token"]
            self.hs_server_id = resp["data"]["hsServerId"]
            self.rid = resp["data"]["rid"]
            return

        raise KotakNeoLoginError(resp)

    async def login(
        self,
        mobile_number: str,
        pan_number: str,
        password: str,
        mpin: str,
        generate_access_token: bool = False,
    ) -> None:
        async with ClientSession() as session:
            if not self.access_token or generate_access_token:
                await self.generate_access_token(session=session)

            url = f"{self.url}/login/1.0/login/v2/validate"

            await self.login_first_step(
                session=session,
                url=url,
                mobile_number=mobile_number,
                pan_number=pan_number,
                password=password,
            )

            await self.login_second_step(
                session=session,
                url=url,
                mobile_number=mobile_number,
                pan_number=pan_number,
                mpin=mpin,
            )

    async def update_auth_token(
        self, auth: str, sid: str, rid: str, hs_server_id: str
    ) -> None:
        """Update auth token."""

        self.auth = auth
        self.sid = sid
        self.rid = rid
        self.hs_server_id = hs_server_id

        url = f"{self.url}/login/1.0/login/refresh"
        headers = {
            "accept": "*/*",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "sid": self.sid,
            "Auth": self.auth,
        }
        payload = json.dumps({"rid": self.rid})

        async with ClientSession() as session:
            response = await session.request(
                method="POST",
                url=url,
                headers=headers,
                data=payload,
            )

            resp = await response.json()

            if response.status in [200, 201]:
                self.auth = resp["data"]["token"]
                return

            raise KotakNeoUpdateTokenError(resp)

    async def instruments(
        self,
        exchange: str | None = None,
    ) -> list[dict[str, str]]:
        async with ClientSession() as session:
            response = await session.request(
                method="GET",
                url=f"{self.url}/Files/1.0/masterscrip/v1/file-paths",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Sid": self.sid,
                    "Auth": self.auth,
                    "neo-fin-key": self.neo_fin_key,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                params={
                    "sId": self.hs_server_id,
                },
            )
            resp = await response.json()

            if response.status in [200, 201]:
                file_paths = resp["data"]["filesPaths"]
                data = []
                for file_path in file_paths:
                    if not exchange or exchange in file_path:
                        data.extend(
                            iter(
                                csv.DictReader(
                                    urlopen(file_path)
                                    .read()
                                    .decode("utf-8")
                                    .splitlines()
                                )
                            )
                        )
                return self._parse_instruments(data)

        raise KotakNeoLoginError(resp)

    def _parse_instruments(self, data):
        return [
            {
                "instrument_token": row["pSymbol"],
                "name": row["pSymbolName"],
                "tradingsymbol": row["pTrdSymbol"],
                "exchange": row["pExchange"],
                "exchange_segment": row["pExchSeg"],
                "instrument_type": row["pInstType"],
                "option_type": row["pOptionType"],
                "tick_size": float(row["dTickSize "]) / 100,
                "lot_size": int(row["iLotSize"]),
                "expiry": self._get_date_from_timestamp(row["lExpiryDate "]),
                "precision": int(row["lPrecision"]),
                "strike": max(float(row["dStrikePrice;"]) / 100, 0),
                "segment": row["pSegment"],
                "max_order_size": int(row["lFreezeQty"]) - 1
                if row["pExchange"] == "NSE" and row["pSegment"] == "FO"
                else int(row["lFreezeQty"]),
            }
            for row in data
            if (" " not in row["pSymbol"])
            and (
                (row["pSegment"] != "" and row["lFreezeQty"] != "0")
                or (row["pSegment"] == "" and row["lFreezeQty"] == "0")
            )
        ]

    @lru_cache(maxsize=128)
    def _get_date_from_timestamp(self, date):
        if date and date != "-1":
            return (
                dt.datetime.fromtimestamp(int(date)) + relativedelta(years=10)
            ).date()

        return ""
