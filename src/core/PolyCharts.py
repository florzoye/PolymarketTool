import os
import re
import aiohttp
import pandas as pd
from typing import Tuple
import matplotlib.pyplot as plt

from src.models.datacreator import DataCreator

class PolyCharts:
    def __init__(self,
                 condition_id: str,
                 slug: str,
                 tg_id: int,
                 max_files: int = 3
        ):
        self.slug = slug
        self.datacreator = DataCreator()
        self.condition_id = condition_id
        self.base_url = 'https://clob.polymarket.com/prices-history'
        self.max_files = max_files

        self.save_dir = f"charts/{tg_id}"

        os.makedirs(self.save_dir, exist_ok=True)



    def _cleanup_old_charts(self):
        pattern = re.compile(rf"^{re.escape(self.slug)}(_\d+)?\.png$")
        files = [
            f for f in os.listdir(self.save_dir)
            if pattern.match(f)
        ]

        files = sorted(
            files,
            key=lambda f: os.path.getmtime(os.path.join(self.save_dir, f))
        )

        if len(files) <= self.max_files:
            return

        excess = files[:-self.max_files]
        for filename in excess:
            os.remove(os.path.join(self.save_dir, filename))


    def _get_next_path(self) -> str:
        """Вернуть путь для нового файла."""
        base = os.path.join(self.save_dir, f"{self.slug}.png")

        if not os.path.exists(base):
            return base

        counter = 1
        while True:
            new_path = os.path.join(self.save_dir, f"{self.slug}_{counter}.png")
            if not os.path.exists(new_path):
                return new_path
            counter += 1


    async def create_chart(self) -> Tuple[bool, str]:
        async with aiohttp.ClientSession() as session:
            params, headers = self.datacreator.create_chart_request_data(self.condition_id)

            response = await session.get(
                self.base_url,
                params=params,
                headers=headers
            )

            response_json = await response.json()
            data = response_json.get("history", [])

            if not data:
                return False, "График не сохранен!"

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

                # путь нового файла
                save_path = self._get_next_path()

                # очистить старые
                self._cleanup_old_charts()

                plt.savefig(save_path, dpi=200)
                plt.close()

                return True, save_path

            except Exception:
                return False, f"График не сохранен!"
