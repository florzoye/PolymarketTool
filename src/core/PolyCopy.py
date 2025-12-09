import time
import asyncio
import traceback
from typing import Tuple, Optional, Dict, List, Callable

from utils.decorator import retry_async
from src.models.settings import Settings
from src.models.position import Position
from src.core.PolyScrapper import PolyScrapper
from src.core.PolyClient import PolyClient


class PolyCopy:
    """
    Класс для мониторинга и копирования сделок на Polymarket.
    
    Возможности:
    - Мониторинг новых сделок (только отслеживание)
    - Копирование сделок 
    - Управление SL/TP
    - Фильтрация сделок
    """
    
    def __init__(
        self,
        settings: Settings,
        scrapper: PolyScrapper,
        client: Optional[PolyClient] = None,
        margin_amount: float = 0,
    ):
        self.settings = settings
        self.scrapper = scrapper
        self.client = client
        self.margin_amount = margin_amount
        
        # Списки для хранения данных
        self.found_positions: List[Position] = []
        self.tracked_positions: List[Dict] = []
        
        # Дедупликация и защита от накрутки
        self.market_transactions: Dict[str, List[float]] = {}
        self.processed_bets: Dict[str, float] = {}
        
        self.last_processed_timestamp = 0
    
    
    def _get_bet_key(self, bet: Position) -> str:
        """Создает уникальный ключ для ставки."""
        return f"{bet.conditionId}_{bet.title}_{bet.outcome}_{round(bet.price, 4)}"
    
    def _is_bet_processed(self, bet: Position, current_time: float) -> bool:
        bet_key = self._get_bet_key(bet)
        
        if bet_key in self.processed_bets:
            time_diff = current_time - self.processed_bets[bet_key]
            if time_diff < 1800:  # 30 минут
                return True
        
        self.processed_bets[bet_key] = current_time
        
        old_keys = [
            k for k, t in self.processed_bets.items() 
            if current_time - t > 3600
        ]
        for k in old_keys:
            del self.processed_bets[k]
        
        return False
    
    def is_trading_enabled(self) -> bool:
        return self.client is not None and self.margin_amount > 0
    
    
    async def _check_multiple_orders(
        self,
        bet: Position,
        max_orders: int = 3,
        time_window_min: int = 30
    ) -> bool:
        market_key = f"{bet.title}_{bet.outcome}"
        now = time.time()
        
        if market_key not in self.market_transactions:
            self.market_transactions[market_key] = []
        
        self.market_transactions[market_key] = [
            ts for ts in self.market_transactions[market_key]
            if now - ts < time_window_min * 60
        ]
        
        if len(self.market_transactions[market_key]) >= max_orders:
            return False
        
        self.market_transactions[market_key].append(now)
        return True
    
    async def custom_filter(self, bet: Position) -> Tuple[str, Optional[Position]]:
        try:
            if bet.usdcSize < self.settings.min_amount:
                return ("слишком маленькая сумма", None)
            
            if not (self.settings.min_quote < bet.price < self.settings.max_quote):
                return ("не подходит по цене", None)
            
            if not await self._check_multiple_orders(bet):
                return ("обнаружена накрутка транзакций", None)
            
            if self.settings.first_bet:
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
            print(f"❌ Ошибка фильтрации: {e}")
            traceback.print_exc()
            return (f"ошибка: {e}", None)
    

    @retry_async(attempts=3)
    async def execute_trade(self, bet: Position) -> Tuple[bool, str]:

        if not self.is_trading_enabled():
            return False, "Торговля не включена (режим мониторинга)"
        
        if not bet.token_id:
            return False, "Отсутствует token_id"
        
        try:
            print(f"🔍 Исполняю сделку:")
            print(f"   Token ID: {bet.token_id}")
            print(f"   Amount: ${self.margin_amount}")
            print(f"   Market: {bet.title[:50]}")
            print(f"   Outcome: {bet.outcome}")
            
            success, message = await self.client.buy(
                token_id=str(bet.token_id),
                amount=self.margin_amount
            )
            
            return success, message
            
        except Exception as e:
            print(f"❌ Ошибка исполнения: {e}")
            traceback.print_exc()
            return False, f"Ошибка: {str(e)}"
    
    
    async def check_sl_tp(self):
        if not self.is_trading_enabled():
            return
        
        try:
            sl_percent = getattr(self.settings, "sl_percent", None)
            tp_percent = getattr(self.settings, "tp_percent", None)
            
            if sl_percent is None and tp_percent is None:
                return
            
            positions = await self.scrapper.get_account_positions()
            
            if not positions:
                return
            
            for tracked in list(self.tracked_positions):
                title = tracked.get("title")
                token_id = tracked.get("token_id")
                
                pm_pos = next(
                    (p for p in positions if p.get("title") == title),
                    None
                )
                
                if pm_pos is None:
                    size = float(pm_pos.get("size", 0)) if pm_pos else 0
                    if size <= 0:
                        try:
                            self.tracked_positions.remove(tracked)
                        except ValueError:
                            pass
                    continue
                
                pnl = pm_pos.get("percentRealizedPnl")
                size = float(pm_pos.get("size", 0))
                
                if pnl is None:
                    continue
                
                if sl_percent is not None:
                    try:
                        if float(pnl) <= float(sl_percent):
                            print(f"🛑 SL сработал: {title}")
                            print(f"   PnL: {pnl}% <= {sl_percent}%")
                            
                            success, msg = await self.client.close_position(
                                token_id, size
                            )
                            
                            if success:
                                try:
                                    self.tracked_positions.remove(tracked)
                                except ValueError:
                                    pass
                                print(f"   ✅ Позиция закрыта")
                            continue
                    except Exception as e:
                        print(f"⚠️ Ошибка SL: {e}")
                
                if tp_percent is not None:
                    try:
                        if float(pnl) >= float(tp_percent):
                            print(f"🎯 TP сработал: {title}")
                            print(f"   PnL: {pnl}% >= {tp_percent}%")
                            
                            success, msg = await self.client.close_position(
                                token_id, size
                            )
                            
                            if success:
                                try:
                                    self.tracked_positions.remove(tracked)
                                except ValueError:
                                    pass
                                print(f"   ✅ Позиция закрыта")
                            continue
                    except Exception as e:
                        print(f"⚠️ Ошибка TP: {e}")
                        
        except Exception as e:
            print(f"⚠️ Ошибка check_sl_tp: {e}")
            traceback.print_exc()
    

    async def monitoring_wallets(
        self,
        callback_func: Optional[Callable] = None
    ) -> Tuple[str, Optional[Position]]:
        """
        Главный цикл мониторинга.
        
        Работает в двух режимах:
        1. Только мониторинг (без client) - только отслеживает и логирует
        2. С торговлей (с client) - отслеживает и исполняет сделки
        
        Args:
            callback_func: Функция для уведомлений
        Returns:
            Tuple[str, Optional[Position]]: (причина остановки, последняя позиция)
        """
        start_time = self.settings.started_at
        check_interval = 5  # Проверка SL/TP каждые 5 секунд
        last_check_time = 0
        
        mode = "торговлей" if self.is_trading_enabled() else "мониторингом"
        
        print(f"\n{'='*60}")
        print(f"🔍 Запуск в режиме: {mode.upper()}")
        print(f"⏰ Длительность: {self.settings.exp_at}s")
        print(f"📊 Фильтры:")
        print(f"   - Мин. сумма: ${self.settings.min_amount}")
        print(f"   - Цена: {self.settings.min_quote} - {self.settings.max_quote}")
        print(f"   - Первая ставка: {self.settings.first_bet}")
        
        if self.is_trading_enabled():
            print(f"💰 Размер позиции: ${self.margin_amount}")
        
        print(f"{'='*60}\n")
        
        while True:
            current_time = time.time()
            elapsed = current_time - start_time
            
            if elapsed >= self.settings.exp_at:
                print(f"\n⏰ Время мониторинга истекло ({elapsed:.0f}s)")
                return ("время истекло", None)
            
            if self.is_trading_enabled():
                if current_time - last_check_time >= check_interval:
                    try:
                        await self.check_sl_tp()
                    except Exception as e:
                        print(f"⚠️ Ошибка SL/TP: {e}")
                    last_check_time = current_time
            
            try:
                recent_bets = await self.scrapper.get_last_bets()
                
                if not recent_bets:
                    print(f"⏳ Нет новых ставок... ({elapsed:.0f}s / {self.settings.exp_at}s)")
                    await asyncio.sleep(5)
                    continue
                
                print(f"\n📥 Получено {len(recent_bets)} ставок для анализа")
                new_bets_found = 0
                
                for bet in recent_bets:
                    if self._is_bet_processed(bet, current_time):
                        continue
                    
                    new_bets_found += 1
                    print(f"\n🆕 Новая ставка #{new_bets_found}:")
                    print(f"   📋 {bet.title[:50]}...")
                    print(f"   🎯 Исход: {bet.outcome}")
                    print(f"   💵 Сумма: ${bet.usdcSize:.2f}")
                    print(f"   📊 Цена: {bet.price:.4f}")
                    
                    filter_msg, filtered_bet = await self.custom_filter(bet)
                    print(f"   🔍 Фильтр: {filter_msg}")
                    
                    if filtered_bet is None:
                        continue
                    
                    self.found_positions.append(filtered_bet)
                    print(f"   ✅ Прошла все фильтры!")
                    
                    trade_executed = False
                    trade_message = ""
                    
                    if self.is_trading_enabled():
                        print(f"   💰 Исполнение сделки на ${self.margin_amount}...")
                        success, trade_msg = await self.execute_trade(filtered_bet)
                        trade_executed = success
                        trade_message = trade_msg
                        
                        if trade_executed:
                            # Добавляем в отслеживаемые позиции
                            self.tracked_positions.append({
                                "title": filtered_bet.title,
                                "outcome": filtered_bet.outcome,
                                "token_id": filtered_bet.token_id,
                                "size": float(self.margin_amount),
                                "opened_at": time.time(),
                                "margin_amount": self.margin_amount
                            })
                            print(f"   ✅ Сделка исполнена")
                        else:
                            print(f"   ❌ Ошибка: {trade_message}")
                    else:
                        trade_message = "Режим мониторинга (торговля отключена)"
                        print(f"   👁️ {trade_message}")
                    
                    if callback_func:
                        try:
                            await callback_func(
                                filtered_bet,
                                filter_msg,
                                trade_executed,
                                trade_message
                            )
                            print(f"   📨 Уведомление отправлено")
                        except Exception as e:
                            print(f"   ❌ Ошибка отправки уведомления: {e}")
                
                if new_bets_found == 0:
                    print(f"⏭️ Все ставки уже обработаны")
                
            except asyncio.CancelledError:
                print(f"\n🛑 Мониторинг отменен пользователем")
                return ("остановлено пользователем", None)
                
            except Exception as e:
                print(f"\n❌ Ошибка мониторинга: {e}")
                traceback.print_exc()
                await asyncio.sleep(10)
                continue
            
            await asyncio.sleep(1)
    
    def reset_tracking(self):
        self.found_positions.clear()
        self.tracked_positions.clear()
        self.market_transactions.clear()
        self.processed_bets.clear()
        self.last_processed_timestamp = 0
        print("🔄 Статистика сброшена")
    
    def get_statistics(self) -> Dict:
        return {
            "mode": "trading" if self.is_trading_enabled() else "monitoring",
            "total_found": len(self.found_positions),
            "tracked_positions_count": len(self.tracked_positions),
            "markets_tracked": len(self.market_transactions),
            "processed_bets_count": len(self.processed_bets),
            "tracked_positions": self.tracked_positions,
            "found_positions": self.found_positions,
        }