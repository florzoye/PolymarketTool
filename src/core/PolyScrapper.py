import asyncio
import aiohttp

from fake_useragent import FakeUserAgent
from utils.customprint import CustomPrint
from utils.decorator import retry_async


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

    def _create_pos_request_data(self, offset: str, limit="50"):
        params = {
            'user': self.address,
            'sizeThreshold': '.1',
            'limit': limit,
            'offset': offset,
            'sortBy': 'CURRENT',
            'sortDirection': 'DESC',
        }
        headers = {
            'accept': 'application/json',
            'origin': 'https://polymarket.com',
            'user-agent': FakeUserAgent().random,
        }
        return params, headers

    @retry_async(attempts=3)
    async def get_account_positions(self):
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
                    if len(data) == 1:
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
                            "currentValue": pos.get("currentValue")
                        })
        return all_positions
    
    @retry_async(attempts=3)
    async def check_leaderboard(self):
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
    pos = await ins.check_leaderboard()
    print(pos)

if __name__ == "__main__":
    asyncio.run(main())