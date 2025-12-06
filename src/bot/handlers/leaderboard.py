from aiogram import Router, F
from aiogram.types import CallbackQuery

from db.database import database
from src.bot.keyboards import get_leaderboard_keyboard
from src.core.PolyScrapper import PolyScrapper

router = Router()


@router.callback_query(F.data == "show_leaderboard")
async def show_leaderboard(callback: CallbackQuery):
    """Показать рейтинг пользователя"""
    tg_id = callback.from_user.id
    db = database.get()
    address = await db.select_user_address(tg_id)

    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return
    
    await callback.answer("⏳ Загружаю данные...")
    
    scrapper = PolyScrapper(address)
    lead = await scrapper.check_leaderboard()

    userName = lead.get('userName', 'Unknown')
    rank = lead.get('rank', '—')
    vol = lead.get('vol', 0)
    pnl = lead.get('pnl', 0)

    text = (
        f"**Данные по вашему аккаунту - {userName}**\n"
        f"🏆 Место в топе: {rank}\n"
        f"👛 Обьем за все время: {round(vol, 3)}\n"
        f"💸 Реализованный PnL за все время: {round(pnl, 3)}\n"
        f"**Обновить информацию за конкретный период?**"
    )
    await callback.message.edit_text(
        text, 
        parse_mode="Markdown", 
        reply_markup=get_leaderboard_keyboard()
    )


@router.callback_query(F.data == "week_lead")
async def check_week_lead(callback: CallbackQuery):
    """Недельный рейтинг"""
    tg_id = callback.from_user.id
    db = database.get()
    address = await db.select_user_address(tg_id)

    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return
    
    await callback.answer("⏳ Загружаю данные...")
    
    scrapper = PolyScrapper(address)
    lead = await scrapper.check_leaderboard(timePeriod='week')

    userName = lead.get('userName', 'Unknown')
    rank = lead.get('rank', '—')
    vol = lead.get('vol', 0)
    pnl = lead.get('pnl', 0)

    text = (
        f"**Данные по вашему аккаунту - {userName}**\n"
        f"🏆 Место в топе: {rank}\n"
        f"👛 Обьем за эту неделю: {round(vol, 3)}\n"
        f"💸 Реализованный PnL за эту неделю: {round(pnl, 3)}\n"
        f"**Обновить информацию за конкретный период?**"
    )
    await callback.message.edit_text(
        text, 
        parse_mode="Markdown", 
        reply_markup=get_leaderboard_keyboard()
    )


@router.callback_query(F.data == "day_lead")
async def check_day_lead(callback: CallbackQuery):
    """Дневной рейтинг"""
    tg_id = callback.from_user.id
    db = database.get()
    address = await db.select_user_address(tg_id)

    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return
    
    await callback.answer("⏳ Загружаю данные...")
    
    scrapper = PolyScrapper(address)
    lead = await scrapper.check_leaderboard(timePeriod='day')

    userName = lead.get('userName', 'Unknown')
    rank = lead.get('rank', '—')
    vol = lead.get('vol', 0)
    pnl = lead.get('pnl', 0)

    text = (
        f"**Данные по вашему аккаунту - {userName}**\n"
        f"🏆 Место в топе: {rank}\n"
        f"👛 Обьем за сегодня: {round(vol, 3)}\n"
        f"💸 Реализованный PnL за сегодня: {round(pnl, 3)}\n"
        f"**Обновить информацию за конкретный период?**"
    )
    await callback.message.edit_text(
        text, 
        parse_mode="Markdown", 
        reply_markup=get_leaderboard_keyboard()
    )