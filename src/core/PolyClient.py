# src/core/PolyClient.py

import time
import traceback
from typing import Tuple, Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, MarketOrderArgs, OrderType
from py_clob_client.exceptions import PolyApiException
from py_clob_client.order_builder.constants import BUY, SELL

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


class PolyClient:
    """
    Клиент для торговли на Polymarket.
    Отвечает за:
    - Инициализацию ClobClient
    - Управление API credentials (refresh)
    - Исполнение сделок (покупка/продажа)
    """
    
    def __init__(
        self,
        private_key: str,
        funder: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_passphrase: Optional[str] = None,
    ):
        self.private_key = private_key
        self.funder = funder
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        
        self.client: Optional[ClobClient] = None
        self._last_creds_refresh = 0
        self._creds_refresh_interval = 50 * 60  # 50 минут
        
        self._initialize_client()
    
    def _initialize_client(self) -> bool:
        if self.client:
            return True
        
        if not (self.private_key and self.funder):
            print("⚠️ ClobClient не может быть создан: отсутствует private_key или funder")
            return False
        
        try:
            self.client = ClobClient(
                HOST,
                key=self.private_key,
                chain_id=CHAIN_ID,
                signature_type=2,
                funder=self.funder
            )
            print(f"✅ ClobClient создан для {self.funder[:8]}...")
            
            self._setup_credentials()
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка инициализации ClobClient: {e}")
            traceback.print_exc()
            self.client = None
            return False
    
    def _setup_credentials(self) -> bool:
        if not self.client:
            return False
        
        if self.api_key and self.api_secret and self.api_passphrase:
            try:
                creds = ApiCreds(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    api_passphrase=self.api_passphrase
                )
                self.client.set_api_creds(creds)
                self._last_creds_refresh = time.time()
                print("🔑 Установлены переданные API credentials")
                return True
            except Exception as e:
                print(f"⚠️ Ошибка установки переданных credentials: {e}")
        
        try:
            creds = self.client.create_or_derive_api_creds()
            if creds:
                self.client.set_api_creds(creds)
                self._last_creds_refresh = time.time()
                print("🔐 API credentials получены через create_or_derive")
                return True
        except Exception as e:
            print(f"⚠️ create_or_derive_api_creds() ошибка: {e}")
        
        try:
            creds = self.client.derive_api_key()
            if creds:
                self.client.set_api_creds(creds)
                self._last_creds_refresh = time.time()
                print("🔁 API credentials получены через derive_api_key")
                return True
        except Exception as e:
            print(f"⚠️ derive_api_key() ошибка: {e}")
        
        print("❌ Не удалось установить API credentials")
        return False
    
    def refresh_credentials(self) -> bool:
        if not self.client:
            return False
        
        print("🔁 Обновление API credentials...")
        
        try:
            creds = self.client.create_or_derive_api_creds()
            if creds:
                self.client.set_api_creds(creds)
                self._last_creds_refresh = time.time()
                print("✅ Credentials обновлены через create_or_derive")
                return True
        except Exception as e:
            print(f"⚠️ create_or_derive ошибка: {e}")
        
        try:
            creds = self.client.derive_api_key()
            if creds:
                self.client.set_api_creds(creds)
                self._last_creds_refresh = time.time()
                print("✅ Credentials обновлены через derive")
                return True
        except Exception as e:
            print(f"⚠️ derive ошибка: {e}")
        
        print("❌ Не удалось обновить credentials")
        return False
    
    def _check_credentials_refresh(self):
        if time.time() - self._last_creds_refresh > self._creds_refresh_interval:
            self.refresh_credentials()
    
    def is_ready(self) -> bool:
        return self.client is not None
    
    async def buy(
        self,
        token_id: str,
        amount: float,
        order_type: OrderType = OrderType.FOK
    ) -> Tuple[bool, str]:
        if not self.is_ready():
            return False, "Клиент не инициализирован"
        
        if amount <= 0:
            return False, "Сумма должна быть больше 0"
        
        if not token_id:
            return False, "Отсутствует token_id"
        
        self._check_credentials_refresh()
        
        order_args = MarketOrderArgs(
            token_id=str(token_id),
            amount=amount,
            side=BUY,
            order_type=order_type
        )
        
        try:
            print(f"🛒 Покупка: token_id={token_id}, amount=${amount}")
            
            signed = self.client.create_market_order(order_args)
            response = self.client.post_order(signed, order_type)
            
            print(f"✅ Покупка успешна: {response}")
            return True, "Покупка выполнена"
            
        except PolyApiException as e:
            if getattr(e, "status_code", None) == 401:
                print("🔐 401 Unauthorized - обновляем credentials...")
                
                if self.refresh_credentials():
                    try:
                        signed = self.client.create_market_order(order_args)
                        response = self.client.post_order(signed, order_type)
                        print(f"✅ Покупка успешна после обновления: {response}")
                        return True, "Покупка выполнена после обновления credentials"
                    except Exception as retry_error:
                        print(f"❌ Повторная попытка неудачна: {retry_error}")
                        return False, f"Ошибка после обновления: {retry_error}"
                else:
                    return False, "Не удалось обновить credentials"
            
            print(f"❌ PolyApiException: {e}")
            return False, f"Ошибка API: {e}"
            
        except Exception as e:
            print(f"❌ Ошибка покупки: {e}")
            traceback.print_exc()
            return False, f"Ошибка: {e}"
    
    async def sell(
        self,
        token_id: str,
        amount: float,
        order_type: OrderType = OrderType.GTC
    ) -> Tuple[bool, str]:
        if not self.is_ready():
            return False, "Клиент не инициализирован"
        
        if amount <= 0:
            return False, "Количество должно быть больше 0"
        
        if not token_id:
            return False, "Отсутствует token_id"
        
        self._check_credentials_refresh()
        
        order_args = MarketOrderArgs(
            token_id=str(token_id),
            amount=amount,
            side=SELL,
            order_type=order_type
        )
        
        try:
            print(f"💸 Продажа: token_id={token_id}, amount={amount}")
            
            signed = self.client.create_market_order(order_args)
            response = self.client.post_order(signed, order_type)
            
            print(f"✅ Продажа успешна: {response}")
            return True, "Продажа выполнена"
            
        except PolyApiException as e:
            if getattr(e, "status_code", None) == 401:
                print("🔐 401 Unauthorized - обновляем credentials...")
                
                if self.refresh_credentials():
                    try:
                        signed = self.client.create_market_order(order_args)
                        response = self.client.post_order(signed, order_type)
                        print(f"✅ Продажа успешна после обновления: {response}")
                        return True, "Продажа выполнена после обновления credentials"
                    except Exception as retry_error:
                        print(f"❌ Повторная попытка неудачна: {retry_error}")
                        return False, f"Ошибка после обновления: {retry_error}"
                else:
                    return False, "Не удалось обновить credentials"
            
            print(f"❌ PolyApiException: {e}")
            return False, f"Ошибка API: {e}"
            
        except Exception as e:
            print(f"❌ Ошибка продажи: {e}")
            traceback.print_exc()
            return False, f"Ошибка: {e}"
    
    async def close_position(self, token_id: str, size: float) -> Tuple[bool, str]:
        return await self.sell(token_id, size)