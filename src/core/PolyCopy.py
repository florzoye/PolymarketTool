import time
import asyncio
from typing import Tuple, Optional, Dict, List

from src.models.settings import Settings
from src.models.position import Position
from src.core.PolyScrapper import PolyScrapper

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


class PolyCopy:
    def __init__(
        self,
        settings: Settings,
        scrapper: PolyScrapper,
        private_key: str = None,
        margin_amount: float = 0,
        funder: str = None,
        api_key: str = None,
        api_secret: str = None,
        api_passphrase: str = None,
    ):
        self.setting = settings
        self.scrapper = scrapper
        self.found_positions: List[Position] = []
        self.market_transactions: Dict[str, int] = {}
        self.processed_bets: Dict[str, float] = {} 
        self.margin_amount = margin_amount
        self.last_processed_timestamp = 0 
        
        
        self.client = None
        if private_key and margin_amount > 0 and funder:
            try:
                # Level 1 Auth
                self.client = ClobClient(
                    HOST,
                    key=private_key,
                    chain_id=CHAIN_ID,
                    signature_type=2,
                    funder=funder
                )
                print(f"✅ ClobClient создан для {funder[:8]}...")
                
                # API credentials (Level 2 Auth)
                if api_key and api_secret and api_passphrase:
                    
                    creds = ApiCreds(
                        api_key=api_key,
                        api_secret=api_secret,
                        api_passphrase=api_passphrase
                    )
                    self.client.set_api_creds(creds)
                else:
                    try:
                        creds = self.client.create_or_derive_api_creds()
                        if creds:
                            self.client.set_api_creds(creds)
                        else:
                            print(f"⚠️ Не удалось создать API credentials автоматически")
                    except Exception as e:
                        print(f"""
                              ⚠️ Ошибка при автоматическом создании API credentials: {e}
                                Бот будет работать в режиме 'только мониторинг'""")
                    
            except Exception as e:
                print(f"❌ Ошибка инициализации ClobClient: {e}")
                import traceback
                traceback.print_exc()

    async def execute_trade(self, bet: Position) -> Tuple[bool, str]:
        """
        Исполняет сделку через ClobClient
        
        Returns:
            (успех, сообщение)
        """
        if not self.client:
            return False, "ClobClient не инициализирован"
        
        if self.margin_amount <= 0:
            return False, "Не установлен размер маржи"
        
        if not bet.token_id:
            return False, "Отсутствует token_id"
        
        try:
            print(f"🔍 Исполняю сделку:")
            print(f"   token_id: {bet.token_id}")
            print(f"   amount: ${self.margin_amount}")
            
            mo = MarketOrderArgs(
                token_id=bet.token_id,
                amount=self.margin_amount,
                side=BUY,
                order_type=OrderType.FOK
            )
            
            signed = self.client.create_market_order(mo)
            resp = self.client.post_order(signed, OrderType.FOK)
            
            print(f"✅ Ответ от API: {resp}")
            return True, f"Сделка исполнена успешно"
            
        except Exception as e:
            print(f"❌ Ошибка исполнения: {e}")
            import traceback
            traceback.print_exc()
            return False, f"Ошибка: {str(e)}"


    async def multiple_orders(self, bet: Position, max_orders: int = 3, time_window: int = 1800) -> bool:
        """
        Проверяет, не накручивает ли кошелек транзакции на один рынок.
        
        Args:
            bet: Position — объект ставки
            max_orders: int — максимум ордеров на один рынок
            time_window: int — временное окно в секундах (по умолчанию 1800 = 30 минут)
        """
        current_time = time.time()
        market_key = f"{bet.title}_{bet.outcome}"

        if market_key not in self.market_transactions:
            self.market_transactions[market_key] = []

        self.market_transactions[market_key] = [
            t for t in self.market_transactions[market_key]
            if current_time - t <= time_window
        ]

        if len(self.market_transactions[market_key]) >= max_orders:
            print(f"⚠️ Превышен лимит ордеров на рынок '{market_key}' за последние {time_window // 60} мин.")
            return False

        self.market_transactions[market_key].append(current_time)
        return True


    async def custom_filter(self, bet: Position) -> Tuple[str, Optional[Position]]:
        """
        Проверяет ставку по кастомным фильтрам.
        """
        try:
            if bet.usdcSize < self.setting.min_amount:
                return ("слишком маленькая сумма", None)

            if not (self.setting.min_quote < bet.price < self.setting.max_quote):
                return ("не подходит по цене", None)

            if not await self.multiple_orders(bet):
                return ("обнаружена накрутка транзакций", None)

            if self.setting.first_bet:
                positions = await self.scrapper.get_last_bets()
                if positions is None:
                    return ("не удалось получить последние ставки", None)

                same_market_bets = [
                    p for p in positions 
                    if p.title == bet.title and p.outcome == bet.outcome
                ]
                
                if len(same_market_bets) > 1:
                    return ("не первая сделка на этот рынок", None)

            return ("прошла все фильтры", bet)

        except Exception as e:
            print(f"❌ Ошибка при фильтрации: {e}")
            return (f"ошибка: {e}", None)

    def _is_bet_processed(self, bet: Position, current_time: float) -> bool:
        """
        Проверяет, была ли ставка уже обработана.
        Использует уникальный ID и временные метки для надежности.
        """
        bet_id = f"{bet.conditionId}_{bet.outcome}_{bet.token_id}"
        
        if bet_id in self.processed_bets:
            process_time = self.processed_bets[bet_id]
            if current_time - process_time < 300:
                return True
        
        self.processed_bets[bet_id] = current_time
        
        old_bets = [
            bid for bid, timestamp in self.processed_bets.items() 
            if current_time - timestamp > 600
        ]
        for old_bet in old_bets:
            del self.processed_bets[old_bet]
        
        return False

    async def monitoring_wallets(self, callback_func=None) -> Tuple[str, Optional[Position]]:
        """
        Принцип работы:
        1. Получаем список последних 10 ставок
        2. Фильтруем по времени (не старше 2 минут)
        3. Проверяем каждую на уникальность
        4. Обрабатываем только новые
        """
        start_time = self.setting.started_at
        check_interval = 5  
        last_check_time = 0
        
        print(f"🔍 Мониторинг запущен на {self.setting.exp_at}s")
        print(f"📊 Фильтры: min=${self.setting.min_amount}, quote={self.setting.min_quote}-{self.setting.max_quote}")
        
        while True:
            current_time = time.time()
            elapsed = current_time - start_time
            
            if elapsed >= self.setting.exp_at:
                print(f"⏰ Время истекло ({elapsed:.0f}s)")
                return ("время мониторинга истекло", None)
            
            if current_time - last_check_time < check_interval:
                await asyncio.sleep(1)
                continue
            
            last_check_time = current_time
            
            try:
                recent_bets = await self.scrapper.get_last_bets()
                
                if not recent_bets:
                    print(f"⏳ Нет новых ставок... ({elapsed:.0f}s / {self.setting.exp_at}s)")
                    continue
                
                print(f"📥 Получено {len(recent_bets)} ставок для анализа")
                
                new_bets_found = 0
                
                for bet in recent_bets:
                    if self._is_bet_processed(bet, current_time):
                        continue
                    
                    new_bets_found += 1
                    print(f"\n🆕 Новая ставка #{new_bets_found}: {bet.title[:50]}...")
                    
                    msg, filtered_bet = await self.custom_filter(bet)
                    print(f"   Фильтр: {msg}")
                    
                    if filtered_bet is None:
                        continue
                    
                    self.found_positions.append(filtered_bet)
                    print(f"   ✅ Прошла все фильтры!")
                    
                    trade_executed = False
                    trade_message = ""
                    
                    if self.client and self.margin_amount > 0:
                        print(f"   💰 Исполняю сделку на ${self.margin_amount}...")
                        success, trade_msg = await self.execute_trade(filtered_bet)
                        trade_executed = success
                        trade_message = trade_msg
                    else:
                        trade_message = "ClobClient не настроен"
                        print(f"   ⚠️ {trade_message}")
                    
                    if callback_func:
                        try:
                            await callback_func(
                                filtered_bet, 
                                msg, 
                                trade_executed, 
                                trade_message
                            )
                            print(f"   📨 Уведомление отправлено")
                        except Exception as e:
                            print(f"   ❌ Ошибка отправки уведомления: {e}")
                
                if new_bets_found == 0:
                    print(f"⏭️ Все ставки уже обработаны")
                
            except asyncio.CancelledError:
                print(f"🛑 Мониторинг отменен")
                return ("мониторинг остановлен пользователем", None)
            except Exception as e:
                print(f"❌ Ошибка мониторинга: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(10)
                continue

    def reset_tracking(self):
        """Сбрасывает счетчики для нового сеанса мониторинга"""
        self.found_positions.clear()
        self.market_transactions.clear()
        self.processed_bets.clear()
        self.last_processed_timestamp = 0

    def get_statistics(self) -> Dict:
        """Возвращает статистику мониторинга"""
        return {
            "total_found": len(self.found_positions),
            "markets_tracked": len(self.market_transactions),
            "positions": self.found_positions,
            "processed_count": len(self.processed_bets)
        }