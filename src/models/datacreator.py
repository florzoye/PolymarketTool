import time
from typing import Tuple, Dict
from fake_useragent import FakeUserAgent

class DataCreator:
    def create_activity_request_data(
            self,
            address: str, 
            limit: str = 10
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        headers = {
            'accept': 'application/json',
            'origin': 'https://polymarket.com',
            'user-agent': FakeUserAgent().random,
        }
        params = {
            'user': address,
            'limit': limit,
            'offset': '0',
            'sortBy': 'TIMESTAMP',
            'sortDirection': 'DESC',
        }
        return params, headers

    def create_lead_request_data(
            self,
            address: str, 
            timePeriod: str | None = 'all'
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        headers = {
            'accept': 'application/json',
            'origin': 'https://polymarket.com',
            'user-agent': FakeUserAgent().random,
        }
        params =  {
            'timePeriod': timePeriod,
            'orderBy': 'PNL',
            'limit': '1',
            'offset': '0',
            'user': address,
            'category': 'overall',
        }
        return params, headers

    def create_pos_request_data(
            self,
            address: str,
            offset: str,
            limit="50", 
            sortBy: str | None = 'CASHPNL',
    ) -> Tuple[Dict[str, str], Dict[str, str]] :
        params = {
            'user': address,
            'sizeThreshold': '.5',
            'limit': limit,
            'offset': offset,
            'sortBy':sortBy,
            'sortDirection': 'DESC',
        }
        headers = {
            'accept': 'application/json',
            'origin': 'https://polymarket.com',
            'user-agent': FakeUserAgent().random,
        }
        return params, headers
    
    def create_chart_request_data(
            self, 
            condition_id: str
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        headers = {
            'accept': 'application/json',
            'origin': 'https://polymarket.com',
            'user-agent': FakeUserAgent().random,
        }
        params = {
            'startTs': str(int(time.time() - 3600 * 250)),
            'market': condition_id,
            'fidelity': '60',
        }
        return params, headers