import time
import asyncio
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.bot.states import CopyTradeState
from src.bot.cfg import bot, active_monitors

from src.core.PolyCopy import PolyCopy
from src.core.PolyClient import PolyClient
from src.core.PolyScrapper import PolyScrapper

from src.models.settings import Settings
from src.models.position import Position


async def start_monitoring_task(callback, state, tg_id, data, private_key, user_address, api_key, api_secret, api_passphrase):
    """Запуск мониторинга кошелька с поддержкой режима без API"""

    settings = Settings(
        exp_at=data.get("duration", 3600),
        started_at=int(time.time()),
        first_bet=data.get("first_bet", False),
        min_amount=data.get("min_amount", 1),
        min_quote=data.get("min_quote", 0.01),
        max_quote=data.get("max_quote", 0.99),
    )

    selected_wallet = data.get("selected_wallet", "")
    margin_amount = data.get("margin_amount", 0)

    scrapper = PolyScrapper(selected_wallet)

    api_enabled = all([api_key, api_secret, api_passphrase])

    poly_client = PolyClient(
        private_key=private_key,
        funder=user_address,
        api_key=api_key if api_enabled else None,
        api_secret=api_secret if api_enabled else None,
        api_passphrase=api_passphrase if api_enabled else None
    )

    poly_copy = PolyCopy(
        settings,
        scrapper,
        margin_amount=margin_amount,
        client=poly_client
    )

    async def notify_found_position(position: Position, message: str, trade_executed: bool, trade_message: str):
        """Уведомление о найденной позиции"""
        emoji = "✅" if trade_executed else "⏳"
        status = "Сделка исполнена!" if trade_executed else (
            "Только мониторинг" if not api_enabled else "Ошибка при исполнении"
        )

        text = (
            f"{emoji} **Найдена подходящая сделка!**\n\n"
            f"📝 {position.title}\n"
            f"💰 Сумма: ${round(position.usdcSize, 2)}\n"
            f"📊 Котировка: {round(position.price, 3)}\n"
            f"🎲 Исход: {position.outcome}\n"
        )

        if api_enabled:
            text += f"💵 Маржа: ${margin_amount}\n"

        text += f"\n📌 {message}\n🔄 {status}\n"

        if trade_message:
            text += f"\n🗒 {trade_message}"

        if api_enabled:
            text += "\n\nМониторинг продолжается..."
        else:
            text += "\n\n⚠️ Режим: только мониторинг (без автоисполнения)"

        try:
            await bot.send_message(tg_id, text, parse_mode="Markdown")
            logging.info(f"✅ Уведомление отправлено пользователю {tg_id}")
        except Exception as e:
            logging.error(f"❌ Ошибка отправки уведомления пользователю {tg_id}: {e}")

    async def run_monitoring():
        """Основной цикл мониторинга"""
        try:
            logging.info(f"🚀 Мониторинг запущен для пользователя {tg_id}")
            await poly_copy.monitoring_wallets(callback_func=notify_found_position)

            stats = poly_copy.get_statistics()
            summary = (
                f"✅ **Мониторинг завершен!**\n\n"
                f"📊 Найдено сделок: {stats['total_found']}\n"
                f"🎯 Отслежено рынков: {stats['markets_tracked']}"
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Запустить новый", callback_data="start_copy_trade")],
                    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
                ]
            )

            await bot.send_message(tg_id, summary, parse_mode="Markdown", reply_markup=kb)
            logging.info(f"✅ Мониторинг завершен для пользователя {tg_id}")

        except asyncio.CancelledError:
            stats = poly_copy.get_statistics()
            cancel_text = (
                f"🛑 **Мониторинг остановлен**\n\n"
                f"📊 Найдено сделок: {stats['total_found']}\n"
                f"🎯 Отслежено рынков: {stats['markets_tracked']}"
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Запустить новый", callback_data="start_copy_trade")],
                    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
                ]
            )

            await bot.send_message(tg_id, cancel_text, parse_mode="Markdown", reply_markup=kb)
            logging.info(f"🛑 Мониторинг остановлен пользователем {tg_id}")

        except Exception as e:
            err = f"❌ **Ошибка при мониторинге:** `{str(e)}`"
            logging.error(f"Ошибка мониторинга: {e}", exc_info=True)
            await bot.send_message(tg_id, err, parse_mode="Markdown")

        finally:
            if tg_id in active_monitors:
                del active_monitors[tg_id]
                logging.info(f"🧹 Очищен мониторинг пользователя {tg_id}")

    task = asyncio.create_task(run_monitoring())
    active_monitors[tg_id] = task

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Остановить мониторинг", callback_data="stop_monitoring")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="monitoring_stats")]
        ]
    )

    duration_text = f"{data.get('duration', 0) // 60} мин" if data.get('duration', 0) < 3600 else f"{data.get('duration', 0) // 3600} ч"
    mode_text = (
        "✨ Подходящие сделки будут автоматически исполняться!" if api_enabled
        else "⚠️ Режим: только мониторинг (уведомления без исполнения)"
    )

    try:
        await callback.message.edit_text(
            f"🚀 **Мониторинг запущен!**\n\n"
            f"👛 Кошелек: `{selected_wallet[:8]}...{selected_wallet[-6:]}`\n"
            f"⏱ Длительность: {duration_text}\n"
            f"💵 Маржа: ${margin_amount}\n\n"
            f"{mode_text}\n\n"
            f"Вы получите уведомление о каждой сделке.",
            parse_mode="Markdown",
            reply_markup=kb
        )
    except Exception as e:
        logging.warning(f"⚠️ Не удалось отредактировать сообщение: {e}")
        await bot.send_message(
            tg_id,
            f"🚀 **Мониторинг запущен!**\n\n"
            f"👛 Кошелек: `{selected_wallet[:8]}...{selected_wallet[-6:]}`\n"
            f"⏱ Длительность: {duration_text}\n"
            f"💵 Маржа: ${margin_amount}\n\n"
            f"{mode_text}\n\n"
            f"Вы получите уведомление о каждой сделке.",
            parse_mode="Markdown",
            reply_markup=kb
        )

    await state.set_state(CopyTradeState.monitoring)