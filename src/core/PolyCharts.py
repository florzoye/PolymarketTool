import io
import aiohttp
import pandas as pd
from typing import Tuple
import matplotlib.pyplot as plt

from src.models.datacreator import DataCreator


class PolyCharts:
    def __init__(self, condition_id: str, slug: str):
        self.slug = slug
        self.datacreator = DataCreator()
        self.condition_id = condition_id
        self.base_url = "https://clob.polymarket.com/prices-history"

    async def create_chart(self) -> Tuple[bool, io.BytesIO]:
        async with aiohttp.ClientSession() as session:
            params, headers = self.datacreator.create_chart_request_data(self.condition_id)
            response = await session.get(self.base_url, params=params, headers=headers)
            response_json = await response.json()

            data = response_json.get("history", [])
            if not data:
                return False, None

            df = pd.DataFrame(data)
            df["t"] = pd.to_datetime(df["t"], unit="s")
            df.rename(columns={"t": "time", "p": "price"}, inplace=True)

            try:
                plt.figure(figsize=(12, 5))
                plt.plot(df["time"], df["price"])
                plt.title(self.slug.replace("_", " "))
                plt.xlabel("Time")
                plt.ylabel("Price")
                plt.grid(True)
                plt.tight_layout()

                buffer = io.BytesIO()
                plt.savefig(buffer, format="png", dpi=200)
                buffer.seek(0)
                plt.close()

                return True, buffer

            except Exception:
                return False, None
