import time 
import asyncio
import aiohttp
from typing import List

from utils.customprint import CustomPrint
from utils.decorator import retry_async

from src.models.position import Position
from src.models.datacreator import DataCreator


class PolyScrapper:
    def __init__(self, address: str):
        self.address = address
        self.base_url = "https://data-api.polymarket.com/"
        self.datacreator = DataCreator()

    @retry_async(attempts=3)
    async def get_account_positions(
        self, 
        sortBy: str | None = 'CASHPNL', 
    ) -> List:
        """
        Фунция для поиска всех позиций и предсортировки в API

        Args:
            sortBy (str): default = CASHPNL, так же может быть INITIAL - новые,  CURRENT - самое большое колво валуе (маржа + пнл)
        Returns:
            positions (list): сырые позиции с начальными фильтрами
        """
        all_positions = []
        async with aiohttp.ClientSession() as session:
            for offset in range(0, 300, 50):
                params, headers = self.datacreator.create_pos_request_data(
                    offset=str(offset),
                    sortBy=sortBy,
                    address=self.address
                )
                async with session.get(
                    f'{self.base_url}positions',
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
                            "asset": pos.get('asset')
                        })
        return all_positions
    

    async def get_last_bets(self, max_age: int | None = 2) -> List[Position]:  
        """
        Получает последние ставки (ТОЛЬКО ПОКУПКИ, НЕ СТАРШЕ 2 минут)
        Возвращает список Position объектов
        """
        async with aiohttp.ClientSession() as session:
            params, headers = self.datacreator.create_activity_request_data(limit='30', address=self.address)
            
            async with session.get(
                f'{self.base_url}activity',
                params=params,
                headers=headers
            ) as response:
                if response.status != 200:
                    CustomPrint().error(f"⚠️ Ошибка {response.status}")
                    return []
                
                data = await response.json()
                
                if not data:
                    return []

                current_time = time.time()
                filtered_bets = []
                
                for pos in data:
                    bet_time = int(pos.get('timestamp', 0))
                    age_minutes = (current_time - bet_time) / 60
                    
                    if age_minutes > max_age or pos.get('side') != 'BUY':
                        continue
                    
                    filtered_bets.append(
                    Position(
                        slug=pos.get('slug'),
                        conditionId=pos.get('conditionId'),
                        outcome=pos.get('outcome'),
                        usdcSize=pos.get('usdcSize'),
                        title=pos.get('title'),
                        price=pos.get('price'),
                        token_id=pos.get('asset')
                    ))
                
                return filtered_bets
                        

    @retry_async(attempts=3)
    async def check_leaderboard(self, timePeriod: str | None = 'all') -> dict:
        async with aiohttp.ClientSession() as session:
            params, headers = self.datacreator.create_lead_request_data(timePeriod=timePeriod, address=self.address)   
            response = await session.get(
                f'{self.base_url}v1/leaderboard',
                params=params,
                headers=headers
            )
            if response.status != 200:
                        CustomPrint().error(f"⚠️ {response.status}")
                        return None
            return (await response.json())[0]
        

    @retry_async(attempts=3)
    async def get_value_user(self):
        async with aiohttp.ClientSession() as session:
            _, headers = self.datacreator.create_activity_request_data(address=self.address)
            params = {'user': self.address}
            response = await session.get(
                f'{self.base_url}value',
                params=params,
                headers=headers
            )
            if response.status != 200:
                    CustomPrint().error(f"⚠️ {response.status}")
                    return None
            return round((await response.json())[0]['value'], 3)

async def main():
    adre = '0xD289B54Aa8849C5cc146899a4C56910e7eC2d0BC'
    ins = PolyScrapper(adre)
    print(await ins.get_account_positions())

if __name__ == '__main__':
    asyncio.run(main())