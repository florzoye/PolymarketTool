from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, BufferedInputFile

from src.core.PolyCharts import PolyCharts

router = Router()


@router.callback_query(F.data.startswith("chart_"))
async def send_chart(callback: CallbackQuery, state: FSMContext):
    """Отправка графика позиции"""
    index = int(callback.data.split("_")[1])

    user_data = await state.get_data()
    positions = user_data.get("current_positions")

    if not positions or index >= len(positions):
        await callback.answer("Ошибка: позиция не найдена", show_alert=True)
        return

    pos = positions[index]
    condition_id = pos.get("asset")
    slug = pos.get("title", "chart").replace(" ", "_")[:40]

    await callback.answer("⏳ Строю график...")

    charts = PolyCharts(condition_id, slug)
    ok, buffer = await charts.create_chart()

    if not ok:
        await callback.message.answer("График не удалось построить")
        return

    await callback.message.answer_photo(
        photo=BufferedInputFile(buffer.getvalue(), filename=f"{slug}.png"),
        caption=f"📉 График: {pos.get('title', '')}"
    )
    
    buffer.close()