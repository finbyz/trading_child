import asyncio
import datetime as dt

import numpy as np
import pandas as pd
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from apps.integration.utils import get_pe_ce_oi_change


class PCRConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def receive_json(self, content, **kwargs):
        self.option_instrument = content["option_instrument"]
        self.websocket_id = content["websocket_id"]
        self.all_data = content["all_data"]
        self.no_of_symbols = int(content["no_of_symbols"])
        self.diff_sub = int(content["diff_sub"]) * 12
        self.diff_sup = int(content["diff_sup"]) * 12

        await self.initial_pcr_data()

    async def initial_pcr_data(self):
        ct = timezone.localtime()
        second = (ct.second // 5) * 5
        loop_time = ct.replace(second=second) + dt.timedelta(seconds=5)

        await asyncio.sleep((loop_time - ct).total_seconds())

        while True:
            df: pd.DataFrame = get_pe_ce_oi_change(
                self.option_instrument,
                self.websocket_id,
                difference_list=[self.diff_sub, self.diff_sup],
            )
            if not df.empty:
                df.columns = [
                    row.replace(str(self.diff_sub), "sub").replace(
                        str(self.diff_sup), "sup"
                    )
                    for row in df.columns
                ]
                df["timestamp"] = df["timestamp"].apply(lambda x: x.isoformat())
                df["ce_oi_change_sup"] = df["ce_oi_change_sup"].fillna(0)
                df["pe_oi_change_sup"] = df["pe_oi_change_sup"].fillna(0)
                df["ce_minus_pe_oi_change_sup"] = df[
                    "ce_minus_pe_oi_change_sup"
                ].fillna(0)
                df["ce_minus_pe_oi_change_sup_update"] = df[
                    "ce_minus_pe_oi_change_sup_update"
                ].fillna(0)
                df["ce_oi_change_sub"] = df["ce_oi_change_sub"].fillna(0)
                df["pe_oi_change_sub"] = df["pe_oi_change_sub"].fillna(0)
                df["ce_minus_pe_oi_change_sub"] = df[
                    "ce_minus_pe_oi_change_sub"
                ].fillna(0)
                df["ce_minus_pe_oi_change_sub_update"] = df[
                    "ce_minus_pe_oi_change_sub_update"
                ].fillna(0)
                df["pe_oi_abs_change_sup"] = df["pe_oi_abs_change_sup"].fillna(0)
                df["ce_oi_abs_change_sup"] = df["ce_oi_abs_change_sup"].fillna(0)
                df["pe_by_ce_oi_abs_change_sup"] = df[
                    "pe_by_ce_oi_abs_change_sup"
                ].fillna(0)
                df["pe_oi_abs_change_sub"] = df["pe_oi_abs_change_sub"].fillna(0)
                df["ce_oi_abs_change_sub"] = df["ce_oi_abs_change_sub"].fillna(0)
                df["pe_by_ce_oi_abs_change_sub"] = df[
                    "pe_by_ce_oi_abs_change_sub"
                ].fillna(0)
                df.fillna(0, inplace=True)
                df = df.replace([np.inf, -np.inf], -1.0)

                if not self.all_data:
                    df = df.tail(self.no_of_symbols)

                data = df.to_dict("records")[::-1]

                await self.send_json({"data": data})
            else:
                await self.send_json({"data": []})

            ct = timezone.localtime()
            second = (ct.second // 5) * 5
            loop_time = ct.replace(second=second) + dt.timedelta(seconds=5)

            await asyncio.sleep((loop_time - ct).total_seconds())

            if timezone.localtime().time() > dt.time(15, 30):
                break
