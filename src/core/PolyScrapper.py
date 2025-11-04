import time 
import asyncio
import aiohttp
from typing import List, Optional

from fake_useragent import FakeUserAgent
from utils.customprint import CustomPrint
from utils.decorator import retry_async

from data import config

class PolyScrapper:
    def __init__(self, address: str):
        self.address = address

    @property
    def _create_lead_request_data(self):
        headers = {
            'accept': 'application/json',
            'origin': 'https://polymarket.com',
            'user-agent': FakeUserAgent().random,
        }
        params =  {
            'timePeriod': 'all',
            'orderBy': 'PNL',
            'limit': '1',
            'offset': '0',
            'user': self.address,
            'category': 'overall',
        }
        return params, headers

    @property
    def _create_activity_request_data(self):
        headers = {
            'accept': 'application/json',
            'origin': 'https://polymarket.com',
            'user-agent': FakeUserAgent().random,
        }
        params = {
            'user': self.address,
            'limit': '10',
            'offset': '0',
            'sortBy': 'TIMESTAMP',
            'sortDirection': 'DESC',
        }
        return params, headers

    def _create_pos_request_data(self, offset: str, limit="50"):
        params = {
            'user': self.address,
            'sizeThreshold': '.1',
            'limit': limit,
            'offset': offset,
            'sortBy': 'INITIAL',
            'sortDirection': 'DESC',
        }
        headers = {
            'accept': 'application/json',
            'origin': 'https://polymarket.com',
            'user-agent': FakeUserAgent().random,
        }
        return params, headers
    
    @retry_async(attempts=3)
    async def get_account_positions(self) -> List:
        all_positions = []
        async with aiohttp.ClientSession() as session:
            for offset in range(0, 300, 50):
                params, headers = self._create_pos_request_data(offset=str(offset))
                async with session.get(
                    'https://data-api.polymarket.com/positions',
                    params=params,
                    headers=headers
                ) as response:
                    if response.status != 200:
                        CustomPrint().error(f"⚠️ {response.status}")
                        break
                    
                    data = await response.json()
                    if len(data) == 0:
                        break

                    for pos in data:
                        all_positions.append({
                            "size": pos.get("size"),
                            "avgPrice": pos.get("avgPrice"),
                            "cashPnl": pos.get("cashPnl"),
                            "initialValue": pos.get("initialValue"),
                            "realizedPnl": pos.get("realizedPnl"),
                            "percentRealizedPnl": pos.get("percentRealizedPnl"),
                            "curPrice": pos.get("curPrice"),
                            "title": pos.get("title"),
                            "currentValue": pos.get("currentValue"),
                        })
        return all_positions
    
    @retry_async(attempts=3)
    async def check_new_bets(self) -> Optional[dict]:
        async with aiohttp.ClientSession() as session:
            params, headers = self._create_activity_request_data
            while True:
                async with session.get(
                    'https://data-api.polymarket.com/activity',
                    params=params,
                    headers=headers
                ) as response:
                    if response.status != 200:
                        CustomPrint().error(f"⚠️ Ошибка {response.status}")
                        await asyncio.sleep(config.DELAY)
                        continue

                    data = await response.json()
                    if not data:
                        await asyncio.sleep(config.DELAY)
                        continue

                    newest_bet = data[0]
                    bet_time = int(newest_bet.get('timestamp', 0))
                    diff_minutes = (time.time() - bet_time) / 60

                    if diff_minutes <= 2 and newest_bet.get('side') == "BUY":
                        CustomPrint().success(f'Новая ставка: {newest_bet}')
                        return newest_bet

                await asyncio.sleep(config.DELAY)

    @retry_async(attempts=3)
    async def check_leaderboard(self) -> List:
        async with aiohttp.ClientSession() as session:
            params, headers = self._create_lead_request_data 
            response = await session.get(
                'https://data-api.polymarket.com/v1/leaderboard',
                params=params,
                headers=headers
            )
            if response.status != 200:
                        CustomPrint().error(f"⚠️ {response.status}")
                        return None
            
            data = await response.json()
            return data[0]

async def main():
    wallet = '0xd289b54aa8849c5cc146899a4c56910e7ec2d0bc'
    ins = PolyScrapper(wallet)
    pos = await ins.get_account_positions()
    print(pos[-1])

if __name__ == "__main__":
    asyncio.run(main())