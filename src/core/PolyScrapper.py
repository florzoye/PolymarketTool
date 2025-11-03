import asyncio
import aiohttp
from fake_useragent import FakeUserAgent
from pprint import pprint

from utils.customprint import CustomPrint

class PolyScrapper:
    def __init__(self, address: str):
        self.address = address

    def _create_request_data(self,offset: str, limit="50"):
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

    async def get_account_positions(self):
        all_positions = []
        async with aiohttp.ClientSession() as session:
            for offset in range(0, 300, 50):
                params, headers = self._create_request_data(offset=str(offset))
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


async def main():
    wallet = '0xd289b54aa8849c5cc146899a4c56910e7ec2d0bc'
    ins = PolyScrapper(wallet)
    pos = await ins.get_account_positions()
    pprint(pos)

if __name__ == "__main__":
    asyncio.run(main())