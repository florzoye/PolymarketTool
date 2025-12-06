import time
import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from db.database import database
from src.bot.keyboards import get_positions_keyboard, get_back_button
from src.core.PolyScrapper import PolyScrapper
from src.core.PolyCopy import PolyCopy
from src.models.settings import Settings

router = Router()


@router.callback_query(F.data == "show_positions")
async def show_positions(callback: CallbackQuery, state: FSMContext):
    """Показать позиции пользователя"""
    tg_id = callback.from_user.id
    db = database.get()
    address = await db.select_user_address(tg_id)

    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return

    await callback.answer("⏳ Получаю данные с Polymarket...")

    scrapper = PolyScrapper(address)
    positions = await scrapper.get_account_positions()

    if not positions:
        try:
            await callback.message.edit_text(
                "😕 Похоже, у тебя нет активных позиций на Polymarket.",
                reply_markup=get_back_button("main_menu")
            )
        except TelegramBadRequest:
            await callback.message.answer(
                "😕 Похоже, у тебя нет активных позиций на Polymarket.",
                reply_markup=get_back_button("main_menu")
            )
        return

    await state.update_data(
        current_positions=positions,
        positions_message_id=callback.message.message_id
    )

    max_show = 10
    display_positions = positions[:max_show]

    text = f"📊 Топ {len(display_positions)} позиций по адресу `{address}`:\n\n"

    for i, pos in enumerate(display_positions, 1):
        title = pos.get("title", "Без названия")
        current = round(float(pos.get("currentValue", 0)), 2)
        pnl = round(float(pos.get("cashPnl", 0)), 2)
        percent = round(float(pos.get("percentRealizedPnl", 0) or 0), 2)

        pnl_emoji = "📈" if pnl >= 0 else "📉"

        text += (
            f"{i}. {title[:60]}\n"
            f"💰 Стоимость: `${current}`\n"
            f"{pnl_emoji} PnL: `${pnl}` ({percent}%)\n"
            f"───────────────────────\n"
        )

    try:
        await callback.message.edit_text(
            text, 
            parse_mode="Markdown",
            reply_markup=get_positions_keyboard(len(display_positions))
        )
    except TelegramBadRequest as e:
        logging.warning(f"Не удалось отредактировать сообщение: {e}")
        new_msg = await callback.message.answer(
            text, 
            parse_mode="Markdown",
            reply_markup=get_positions_keyboard(len(display_positions))
        )
        await state.update_data(positions_message_id=new_msg.message_id)
        
        try:
            await callback.message.delete()
        except:
            pass


@router.callback_query(F.data == "select_position_to_close")
async def select_position_to_close(callback: CallbackQuery, state: FSMContext):
    """Показывает список позиций для закрытия"""
    data = await state.get_data()
    positions = data.get("current_positions", [])
    
    if not positions:
        await callback.answer("❌ Нет активных позиций", show_alert=True)
        return
    
    keyboard = []
    for i, pos in enumerate(positions[:15]):  
        title = pos.get("title", "Без названия")[:40]
        current = round(float(pos.get("currentValue", 0)), 2)
        pnl = round(float(pos.get("cashPnl", 0)), 2)
        
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        button_text = f"{pnl_emoji} {title}... (${current})"
        
        keyboard.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"close_pos_{i}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="show_positions")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    try:
        await callback.message.edit_text(
            "❌ **Выберите позицию для закрытия:**\n\n"
            "⚠️ **Внимание!** Закрытие позиции необратимо.\n"
            "Убедитесь что выбрали правильную позицию.",
            parse_mode="Markdown",
            reply_markup=kb
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "❌ **Выберите позицию для закрытия:**\n\n"
            "⚠️ **Внимание!** Закрытие позиции необратимо.\n"
            "Убедитесь что выбрали правильную позицию.",
            parse_mode="Markdown",
            reply_markup=kb
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("close_pos_"))
async def confirm_close_position(callback: CallbackQuery, state: FSMContext):
    """Подтверждение закрытия позиции"""
    pos_index = int(callback.data.split("_")[-1])
    data = await state.get_data()
    positions = data.get("current_positions", [])
    
    if pos_index >= len(positions):
        await callback.answer("❌ Ошибка: позиция не найдена", show_alert=True)
        return
    
    position = positions[pos_index]
    title = position.get("title", "Без названия")
    current = round(float(position.get("currentValue", 0)), 2)
    size = float(position.get("size", 0))
    pnl = round(float(position.get("cashPnl", 0)), 2)
    percent = round(float(position.get("percentRealizedPnl", 0) or 0), 2)
    
    await state.update_data(closing_position_index=pos_index)
    
    pnl_emoji = "📈" if pnl >= 0 else "📉"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, закрыть позицию", callback_data="execute_close_position")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="select_position_to_close")]
        ]
    )
    
    text = (
        "⚠️ **Подтверждение закрытия позиции**\n\n"
        f"📝 **Название:** {title}\n"
        f"💰 **Текущая стоимость:** ${current}\n"
        f"📊 **Размер:** {size}\n"
        f"{pnl_emoji} **PnL:** ${pnl} ({percent}%)\n\n"
        f"❗ Вы уверены, что хотите закрыть эту позицию?"
    )
    
    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except TelegramBadRequest:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    
    await callback.answer()


@router.callback_query(F.data == "execute_close_position")
async def execute_close_position(callback: CallbackQuery, state: FSMContext):
    """Исполнение закрытия позиции"""
    tg_id = callback.from_user.id
    data = await state.get_data()
    db = database.get()
    
    pos_index = data.get("closing_position_index")
    positions = data.get("current_positions", [])
    
    if pos_index is None or pos_index >= len(positions):
        await callback.answer("❌ Ошибка: позиция не найдена", show_alert=True)
        return
    
    position = positions[pos_index]
    title = position.get("title", "Без названия")
    
    private_key = await db.get_private_key(tg_id)
    user_address = await db.select_user_address(tg_id)
    api_key, api_secret, api_passphrase = await db.get_api_credentials(tg_id)
    
    if not private_key:
        try:
            await callback.message.edit_text(
                "❌ Приватный ключ не найден!\n"
                "Для закрытия позиций нужен приватный ключ.",
                reply_markup=get_back_button("show_positions")
            )
        except TelegramBadRequest:
            await callback.message.answer(
                "❌ Приватный ключ не найден!\n"
                "Для закрытия позиций нужен приватный ключ.",
                reply_markup=get_back_button("show_positions")
            )
        await callback.answer()
        return
    
    try:
        await callback.message.edit_text(
            f"⏳ **Закрываю позицию...**\n\n"
            f"📝 {title}\n\n"
            f"Пожалуйста, подождите...",
            parse_mode="Markdown"
        )
    except TelegramBadRequest:
        await callback.message.answer(
            f"⏳ **Закрываю позицию...**\n\n"
            f"📝 {title}\n\n"
            f"Пожалуйста, подождите...",
            parse_mode="Markdown"
        )
    
    try:
        scrapper = PolyScrapper(user_address)
        
        temp_settings = Settings(
            exp_at=60,
            started_at=int(time.time()),
            first_bet=False,
            min_amount=1,
            min_quote=0.01,
            max_quote=0.99
        )
        
        poly_copy = PolyCopy(
            temp_settings,
            scrapper,
            private_key=private_key,
            margin_amount=1,
            funder=user_address,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase
        )
        
        current_positions = await scrapper.get_account_positions()
        
        actual_pos = next((p for p in current_positions if p.get('title') == title), None)
        
        if not actual_pos:
            try:
                await callback.message.edit_text(
                    f"❌ **Позиция не найдена**\n\n"
                    f"Возможно она уже закрыта или изменилась.",
                    parse_mode="Markdown",
                    reply_markup=get_back_button("show_positions")
                )
            except TelegramBadRequest:
                await callback.message.answer(
                    f"❌ **Позиция не найдена**\n\n"
                    f"Возможно она уже закрыта или изменилась.",
                    parse_mode="Markdown",
                    reply_markup=get_back_button("show_positions")
                )
            await callback.answer()
            return
        
        token_id = actual_pos.get('asset')
        size = float(actual_pos.get('size'))
        
        if not token_id:
            try:
                await callback.message.edit_text(
                    f"❌ **Ошибка: не найден token_id**\n\n"
                    f"Невозможно закрыть позицию без token_id.",
                    parse_mode="Markdown",
                    reply_markup=get_back_button("show_positions")
                )
            except TelegramBadRequest:
                await callback.message.answer(
                    f"❌ **Ошибка: не найден token_id**\n\n"
                    f"Невозможно закрыть позицию без token_id.",
                    parse_mode="Markdown",
                    reply_markup=get_back_button("show_positions")
                )
            await callback.answer()
            return
        
        success = await poly_copy.close_position(token_id, size)
        
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить позиции", callback_data="show_positions")],
                [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
            ]
        )
        
        if success:
            pnl = round(float(position.get("cashPnl", 0)), 2)
            percent = round(float(position.get("percentRealizedPnl", 0) or 0), 2)
            
            text = (
                f"✅ **Позиция успешно закрыта!**\n\n"
                f"📝 {title}\n"
                f"💰 Финальный PnL: ${pnl} ({percent}%)\n\n"
                f"Позиция больше не отображается в вашем портфеле."
            )
        else:
            text = (
                f"❌ **Ошибка при закрытии позиции**\n\n"
                f"📝 {title}\n\n"
                f"Возможные причины:\n"
                f"• Недостаточно средств\n"
                f"• Проблемы с API\n"
                f"• Позиция уже закрыта\n\n"
                f"Попробуйте позже или проверьте на polymarket.com"
            )
        
        try:
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except TelegramBadRequest:
            await callback.message.answer(text, parse_mode="Markdown", reply_markup=kb)
        
        await callback.answer()
        
    except Exception as e:
        logging.error(f"Ошибка закрытия позиции: {e}")
        
        try:
            await callback.message.edit_text(
                f"❌ **Произошла ошибка:**\n\n"
                f"`{str(e)}`\n\n"
                f"Попробуйте позже.",
                parse_mode="Markdown",
                reply_markup=get_back_button("show_positions")
            )
        except TelegramBadRequest:
            await callback.message.answer(
                f"❌ **Произошла ошибка:**\n\n"
                f"`{str(e)}`\n\n"
                f"Попробуйте позже.",
                parse_mode="Markdown",
                reply_markup=get_back_button("show_positions")
            )
        
        await callback.answer()