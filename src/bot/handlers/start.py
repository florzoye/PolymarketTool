from aiogram.filters import Command
from aiogram import Router, F, types
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from db.database import database
from src.bot.states import RegisterState
from src.bot.keyboards import (
    get_main_menu_keyboard, 
    get_api_setup_keyboard, 
    get_back_button
)

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Команда /start - регистрация или главное меню"""
    tg_id = message.from_user.id
    db = database.get()
    
    address = await db.select_user_address(tg_id)

    if address is None:
        await message.answer(
            "👋 Привет! Добро пожаловать в Polymarket Copy Trading Bot!\n\n"
            "Для начала работы мне нужен ваш адрес на Polymarket.\n"
            "📝 Отправьте ваш адрес (формат: 0x...):",
            parse_mode="Markdown"
        )
        await state.set_state(RegisterState.waiting_for_address)
    else:
        await message.answer(
            f"✅ Добро пожаловать!\n\n"
            f"Ваш адрес: `{address}`\n\n"
            f"Выберите действие:",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(RegisterState.waiting_for_address)
async def get_address(message: types.Message, state: FSMContext):
    """Получение адреса при регистрации"""
    address = message.text.strip()
    tg_id = message.from_user.id

    if not address.startswith("0x") or len(address) != 42:
        await message.answer("⚠️ Это невалидный Ethereum/Polymarket адрес. Попробуй снова.")
        return

    await state.update_data(address=address)
    
    await message.answer(
        "✅ Адрес принят!\n\n"
        "🔐 Теперь отправьте ваш приватный ключ для автоматического исполнения сделок.\n\n"
        "⚠️ **ВАЖНО**: Ваш приватный ключ будет надежно храниться в зашифрованном виде.\n"
        "Он нужен для автоматического копирования сделок.\n\n"
        "Формат: 0x... (64 символа после 0x)",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.waiting_for_private_key)


@router.message(RegisterState.waiting_for_private_key)
async def get_private_key(message: types.Message, state: FSMContext):
    """Получение приватного ключа"""
    private_key = message.text.strip()
    
    try:
        await message.delete()
    except:
        pass

    if not private_key.startswith("0x") or len(private_key) != 66:
        await message.answer(
            "⚠️ Невалидный приватный ключ.\n"
            "Формат должен быть: 0x... (66 символов)\n\n"
            "Попробуйте снова:"
        )
        return

    await state.update_data(private_key=private_key)
    
    await message.answer(
        "✅ Приватный ключ принят!\n\n"
        "🔐 **API Credentials (опционально)**\n\n"
        "Для автоматического исполнения ордеров через Polymarket API нужны:\n"
        "• API Key\n"
        "• API Secret\n"
        "• API Passphrase\n\n"
        "📖 Как получить: зайдите на https://polymarket.com, зайдите настройки -> builder -> add API\n\n"
        "⚠️ **Без API credentials** бот сможет только мониторить сделки, но не исполнять их автоматически.\n\n"
        "Хотите настроить API credentials сейчас?",
        parse_mode="Markdown",
        reply_markup=get_api_setup_keyboard()
    )
    await state.set_state(RegisterState.waiting_for_api_key)


@router.callback_query(F.data == "setup_api_yes")
async def setup_api_yes(callback: CallbackQuery, state: FSMContext):
    """Начало настройки API credentials"""
    await callback.message.edit_text(
        "🔑 **Шаг 1/3: API Key**\n\n"
        "Отправьте ваш Polymarket API Key:\n"
        "(Получить можно на https://polymarket.com/settings/api)\n\n"
        "Формат: строка из букв и цифр",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.waiting_for_api_key)
    await callback.answer()


@router.callback_query(F.data == "setup_api_no")
async def setup_api_no(callback: CallbackQuery, state: FSMContext):
    """Пропуск настройки API credentials"""
    tg_id = callback.from_user.id
    data = await state.get_data()
    db = database.get()
    
    address = data.get("address")
    private_key = data.get("private_key")
    
    await db.add_user({
        "tg_id": tg_id,
        "address": address
    })
    await db.update_private_key(tg_id, private_key)
    
    await state.clear()
    await callback.message.edit_text(
        f"✅ Регистрация завершена!\n\n"
        f"📍 Адрес: `{address}`\n"
        f"🔐 Приватный ключ: сохранен\n"
        f"⚠️ API Credentials: не настроены\n\n"
        f"⚠️ **Внимание:** Без API credentials бот будет работать в режиме \"только мониторинг\".\n"
        f"Автоматическое исполнение сделок будет недоступно.\n\n"
        f"Вы можете добавить API credentials позже через настройки.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@router.message(RegisterState.waiting_for_api_key)
async def get_api_key(message: types.Message, state: FSMContext):
    """Получение API Key"""
    api_key = message.text.strip()
    
    try:
        await message.delete()
    except:
        pass
    
    if len(api_key) < 10:
        await message.answer("⚠️ API Key слишком короткий. Попробуйте снова:")
        return
    
    await state.update_data(api_key=api_key)
    
    await message.answer(
        "✅ API Key принят!\n\n"
        "🔑 **Шаг 2/3: API Secret**\n\n"
        "Теперь отправьте ваш API Secret:",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.waiting_for_api_secret)


@router.message(RegisterState.waiting_for_api_secret)
async def get_api_secret(message: types.Message, state: FSMContext):
    """Получение API Secret"""
    api_secret = message.text.strip()
    
    try:
        await message.delete()
    except:
        pass
    
    if len(api_secret) < 10:
        await message.answer("⚠️ API Secret слишком короткий. Попробуйте снова:")
        return
    
    await state.update_data(api_secret=api_secret)
    
    await message.answer(
        "✅ API Secret принят!\n\n"
        "🔑 **Шаг 3/3: API Passphrase**\n\n"
        "Наконец, отправьте ваш API Passphrase:",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.waiting_for_api_passphrase)


@router.message(RegisterState.waiting_for_api_passphrase)
async def get_api_passphrase(message: types.Message, state: FSMContext):
    """Получение API Passphrase и завершение регистрации"""
    api_passphrase = message.text.strip()
    tg_id = message.from_user.id
    db = database.get()
    
    try:
        await message.delete()
    except:
        pass
    
    if len(api_passphrase) < 3:
        await message.answer("⚠️ API Passphrase слишком короткий. Попробуйте снова:")
        return
    
    data = await state.get_data()
    address = data.get("address")
    private_key = data.get("private_key")
    api_key = data.get("api_key")
    api_secret = data.get("api_secret")
    
    await db.add_user({
        "tg_id": tg_id,
        "address": address
    })
    await db.update_private_key(tg_id, private_key)
    await db.update_api_credentials(tg_id, api_key, api_secret, api_passphrase)
    
    await state.clear()
    
    await message.answer(
        f"✅ **Регистрация полностью завершена!**\n\n"
        f"📍 Адрес: `{address}`\n"
        f"🔐 Приватный ключ: сохранен\n"
        f"🔑 API Credentials: настроены ✅\n\n"
        f"🎉 Теперь бот может автоматически исполнять сделки!\n"
        f"Все данные надежно зашифрованы.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )


@router.callback_query(F.data == "reset_wallet")
async def reset_wallet(callback: CallbackQuery, state: FSMContext):
    """Начало процесса смены кошелька"""
    tg_id = callback.from_user.id
    db = database.get()
    address = await db.select_user_address(tg_id)
    
    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return
    
    
    await callback.message.edit_text(
        f'Сейчас ваш адресс - `{address}`\n\n'
        f'Если желаете поменять, пришлите новый в чат.',
        parse_mode="Markdown",
        reply_markup=get_back_button("main_menu")
    )
    await state.set_state(RegisterState.reset_address)
    await callback.answer()


@router.message(RegisterState.reset_address)
async def reset_address(message: types.Message, state: FSMContext):
    """Получение нового адреса"""
    address = message.text.strip()

    if not address.startswith("0x") or len(address) != 42:
        await message.answer("⚠️ Это невалидный Ethereum/Polymarket адрес. Попробуй снова.")
        return

    await state.update_data(new_address=address)
    
    await message.answer(
        "✅ Новый адрес принят!\n\n"
        "🔐 Отправьте новый приватный ключ для этого адреса:",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.reset_private_key)


@router.message(RegisterState.reset_private_key)
async def reset_private_key(message: types.Message, state: FSMContext):
    """Получение нового приватного ключа"""
    private_key = message.text.strip()
    tg_id = message.from_user.id
    db = database.get()
    
    try:
        await message.delete()
    except:
        pass

    if not private_key.startswith("0x") or len(private_key) != 66:
        await message.answer("⚠️ Невалидный приватный ключ. Попробуйте снова.")
        return

    data = await state.get_data()
    new_address = data.get("new_address")

    await db.update_user_address(tg_id, new_address)
    await db.update_private_key(tg_id, private_key)

    await state.clear()
    await message.answer(
        f"✅ Данные обновлены!\n\n"
        f"📍 Новый адрес: `{new_address}`\n"
        f"🔐 Приватный ключ обновлен\n\n"
        f"Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    tg_id = callback.from_user.id
    db = database.get()
    address = await db.select_user_address(tg_id)
    
    if not address:
        await callback.message.edit_text(
            "❌ Адрес не найден. Используйте /start для регистрации."
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"✅ Главное меню\n"
        f"Ваш адрес: `{address}`\n\n"
        f"Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()