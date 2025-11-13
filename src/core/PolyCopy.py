import time
import asyncio
import traceback
from typing import Tuple, Optional, Dict, List

from utils.decorator import retry_async
from src.models.settings import Settings
from src.models.position import Position
from src.core.PolyScrapper import PolyScrapper

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.exceptions import PolyApiException
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

        # сохраняем входные параметры
        self.private_key = private_key
        self.funder = funder
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase

        self.found_positions: List[Position] = []
        self.market_transactions: Dict[str, List[float]] = {}  # key -> list of timestamps
        self.processed_bets: Dict[str, float] = {}  # bet_key -> last processed time
        self.margin_amount = margin_amount
        self.last_processed_timestamp = 0

        self.client = None
        self._last_creds_refresh = 0  # unix time
        self._creds_refresh_interval = 50 * 60  # обновлять креды каждые ~50 минут
        # Попытка создать/инициализировать клиент сразу (если возможно)
        try:
            self._ensure_client()
        except Exception:
            # Логи уже в _ensure_client
            pass

    def _get_bet_key(self, bet: Position) -> str:
        """Создаёт стабильный уникальный идентификатор для ставки."""
        return f"{bet.conditionId}_{bet.title}_{bet.outcome}_{round(bet.price, 4)}"

    def _is_bet_processed(self, bet: Position, current_time: float) -> bool:
        """Проверяет, обрабатывалась ли ставка недавно (до 30 мин назад)."""
        bet_key = self._get_bet_key(bet)

        if bet_key in self.processed_bets and current_time - self.processed_bets[bet_key] < 1800:
            return True

        self.processed_bets[bet_key] = current_time

        old_keys = [k for k, t in self.processed_bets.items() if current_time - t > 3600]
        for k in old_keys:
            del self.processed_bets[k]

        return False

    def _ensure_client(self):
        """
        Создаёт и настраивает ClobClient один раз, если это ещё не сделано.
        Устанавливает API creds: приоритет — явно переданные (api_key/...),
        затем create_or_derive_api_creds(), затем derive_api_key() как fallback.
        """
        if self.client:
            return

        if not (self.private_key and self.funder and self.margin_amount > 0):
            # Клиент не требуется/нельзя создать (режим только мониторинга)
            print("⚠️ ClobClient не будет создан: отсутствует private_key, funder или margin_amount <= 0")
            return

        try:
            self.client = ClobClient(
                HOST,
                key=self.private_key,
                chain_id=CHAIN_ID,
                signature_type=2,
                funder=self.funder
            )
            print(f"✅ ClobClient создан для {self.funder[:8]}...")

            # 1) Если явно переданы API creds — используем их
            if self.api_key and self.api_secret and self.api_passphrase:
                creds = ApiCreds(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    api_passphrase=self.api_passphrase
                )
                try:
                    self.client.set_api_creds(creds)
                    print("🔑 Установлены переданные в БД API credentials.")
                    self._last_creds_refresh = time.time()
                    return
                except Exception as e:
                    print(f"⚠️ Ошибка установки переданных API credentials: {e}")

            # 2) Попытка создать или derive на сервере (лучший вариант)
            try:
                creds = self.client.create_or_derive_api_creds()
                if creds:
                    self.client.set_api_creds(creds)
                    print("🔐 Созданы/получены API credentials через create_or_derive_api_creds().")
                    self._last_creds_refresh = time.time()
                    return
            except Exception as e:
                print(f"⚠️ create_or_derive_api_creds() вернуло ошибку: {e}")

            # 3) Fallback: локальный derive (не требует POST)
            try:
                post_creds = self.client.derive_api_key()
                if post_creds:
                    self.client.set_api_creds(post_creds)
                    print("🔁 Установлены derived API credentials (local derive).")
                    self._last_creds_refresh = time.time()
                    return
            except Exception as e:
                print(f"⚠️ derive_api_key() вернуло ошибку: {e}")

            print("⚠️ Не удалось получить рабочие API credentials — клиент создан в режиме только мониторинга.")
        except Exception as e:
            print(f"❌ Ошибка инициализации ClobClient: {e}")
            traceback.print_exc()
            self.client = None

    def _refresh_api_creds(self) -> bool:
        """
        Пытается обновить API credentials (create_or_derive_api_creds -> derive).
        Возвращает True если успешно.
        """
        if not self.client:
            return False

        print("🔁 Пытаемся обновить API credentials...")
        try:
            creds = self.client.create_or_derive_api_creds()
            if creds:
                self.client.set_api_creds(creds)
                self._last_creds_refresh = time.time()
                print("✅ API credentials обновлены через create_or_derive_api_creds().")
                return True
        except Exception as e:
            print(f"⚠️ Ошибка create_or_derive_api_creds(): {e}")

        try:
            post_creds = self.client.derive_api_key()
            if post_creds:
                self.client.set_api_creds(post_creds)
                self._last_creds_refresh = time.time()
                print("✅ API credentials обновлены через derive_api_key() fallback.")
                return True
        except Exception as e:
            print(f"⚠️ Ошибка derive_api_key(): {e}")

        print("❌ Не удалось обновить API credentials.")
        return False

    async def multiple_orders(
        self,
        bet: Position,
        max_orders: int = 3,
        time_window_min: int = 30
    ) -> bool:
        """
        Проверяет, что за последние time_window_min минут по этому рынку не было более max_orders сделок.
        """
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

        # добавляем текущую
        self.market_transactions[market_key].append(now)
        return True

    @retry_async(attempts=3)
    async def execute_trade(self, bet: Position) -> Tuple[bool, str]:
        """Исполняет сделку через ClobClient с авто-рефрешем creds при 401."""
        # Убедимся, что клиент создан
        if not self.client:
            # попытка создать клиент (если параметры были заданы)
            self._ensure_client()

        if not self.client:
            return False, "ClobClient не инициализирован (режим только мониторинга)"

        if self.margin_amount <= 0:
            return False, "Не установлен размер маржи"

        if not bet.token_id:
            return False, "Отсутствует token_id"

        # Если creds старые по времени — обновим заранее
        if time.time() - self._last_creds_refresh > self._creds_refresh_interval:
            self._refresh_api_creds()

        mo = MarketOrderArgs(
            token_id=str(bet.token_id),
            amount=self.margin_amount,
            side=BUY,
            order_type=OrderType.FOK
        )

        # Попробуем отправить ордер, а при 401 попробуем обновить creds и повторить один раз
        try:
            print(f"🔍 Исполняю сделку:")
            print(f"   token_id: {bet.token_id}")
            print(f"   amount: ${self.margin_amount}")

            signed = self.client.create_market_order(mo)
            resp = self.client.post_order(signed, OrderType.FOK)

            print(f"✅ Ответ от API: {resp}")
            return True, "Сделка исполнена успешно"

        except PolyApiException as e:
            print(f"⚠️ PolyApiException: {e}")
            # при 401 — пробуем обновить creds и повторить
            if getattr(e, "status_code", None) == 401:
                print("🔐 Получен 401 Unauthorized — пробуем обновить API credentials и повторить...")
                try:
                    refreshed = self._refresh_api_creds()
                    if refreshed:
                        # повторная попытка
                        try:
                            signed = self.client.create_market_order(mo)
                            resp = self.client.post_order(signed, OrderType.FOK)
                            print(f"✅ Ответ от API после обновления ключей: {resp}")
                            return True, "Сделка исполнена успешно после обновления API credentials"
                        except PolyApiException as e2:
                            print(f"❌ Повторная попытка упала: {e2}")
                            return False, f"Ошибка после обновления ключей: {e2}"
                    else:
                        return False, "Не удалось обновить API credentials (401)"
                except Exception as inner_e:
                    print(f"❌ Ошибка при обновлении creds: {inner_e}")
                    return False, f"Ошибка при обновлении creds: {inner_e}"
            # для остальных ошибок пробрасываем дальше
            raise

        except Exception as e:
            print(f"❌ Ошибка исполнения: {e}")
            traceback.print_exc()
            return False, f"Ошибка: {str(e)}"

    async def custom_filter(self, bet: Position) -> Tuple[str, Optional[Position]]:
        """Проверяет ставку по кастомным фильтрам."""
        try:
            if bet.usdcSize < self.setting.min_amount:
                return ("слишком маленькая сумма", None)

            if not (self.setting.min_quote < bet.price < self.setting.max_quote):
                return ("не подходит по цене", None)

            if not await self.multiple_orders(bet):
                return ("обнаружена накрутка транзакций (слишком часто)", None)

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

    async def monitoring_wallets(self, callback_func=None) -> Tuple[str, Optional[Position]]:
        """
        Мониторит Polymarket:
        1. Получает последние ставки
        2. Проверяет уникальность, фильтры
        3. Исполняет сделки (если клиент доступен)
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

                    # убедимся что клиент создан (если нужно автоисполнение)
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
                            await callback_func(filtered_bet, msg, trade_executed, trade_message)
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
