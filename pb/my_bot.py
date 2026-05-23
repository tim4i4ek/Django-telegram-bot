import os
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.exceptions import TelegramBadRequest

# ==========================================
# 1. НАЛАШТУВАННЯ ТА КОНФІГУРАЦІЯ
# ==========================================
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_BASE_URL = 'http://127.0.0.1:8000/api/'
BASE_URL = 'http://127.0.0.1:8000'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ==========================================
# 2. СТАНИ (FSM) ТА КОЛБЕКИ
# ==========================================
class BookingState(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()


# Сучасний спосіб генерації кнопок в aiogram 3
class ServiceCb(CallbackData, prefix="srv"):
    id: int


class DateCb(CallbackData, prefix="date"):
    val: str  # Формат: YYYY-MM-DD


class TimeCb(CallbackData, prefix="time"):
    val: str  # Формат: "10:00"
    hour: int  # Формат: 10


# ==========================================
# 3. ФУНКЦІЇ ДЛЯ РОБОТИ З API
# ==========================================
async def fetch_api(endpoint: str):
    """Універсальна функція для GET-запитів до Django."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_BASE_URL}{endpoint}") as response:
                if response.status == 200:
                    return await response.json()
                logging.warning(f"API Error {response.status} for {endpoint}")
                return None
        except Exception as e:
            logging.error(f"API Connection Error: {e}")
            return None


async def post_api(endpoint: str, data: dict):
    """Універсальна функція для POST-запитів до Django."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{API_BASE_URL}{endpoint}", json=data) as response:
                return await response.json(), response.status
        except Exception as e:
            logging.error(f"API Post Error: {e}")
            return {"error": "Connection failed"}, 500


# ==========================================
# 4. ДОПОМІЖНІ ФУНКЦІЇ (UI)
# ==========================================
async def safe_delete(message: types.Message):
    """Безпечне видалення повідомлення без крашів бота."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass  # Якщо повідомлення застаріле - просто ігноруємо


async def clear_service_cards(message: types.Message, state: FSMContext):
    """Видаляє всі картки послуг, щоб очистити чат перед показом календаря."""
    data = await state.get_data()
    msg_ids = data.get("service_msg_ids", [])
    for msg_id in msg_ids:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        except TelegramBadRequest:
            pass
    await state.update_data(service_msg_ids=[])


# ==========================================
# 5. ОБРОБНИКИ (HANDLERS)
# ==========================================

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    text = (
        "👋 **Ласкаво просимо до нашої майстерні!**\n\n"
        "🔧 Ми спеціалізуємося на професійному обслуговуванні та ремонті.\n"
        "📅 Тут ви можете швидко та зручно переглянути вільні години та записатися на візит."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Записатися на послугу", callback_data="start_booking")

    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await safe_delete(callback.message)
    await cmd_start(callback.message, state)


@router.callback_query(F.data == "start_booking")
async def process_start_booking(callback: types.CallbackQuery, state: FSMContext):
    await safe_delete(callback.message)  # Видаляємо головне меню

    services = await fetch_api('services/')
    if not services:
        await callback.answer("🚨 Список послуг наразі порожній.", show_alert=True)
        return

    await state.set_state(BookingState.choosing_service)

    # Зберігаємо ID повідомлень, щоб потім їх видалити і не смітити в чаті
    sent_msg_ids = []

    for s in services:
        if not s.get('available', True):
            continue

        kb = InlineKeyboardBuilder()
        kb.button(text=f"✅ Обрати: {s['proposition']}", callback_data=ServiceCb(id=s['id']).pack())

        caption = f"🛠 **{s['proposition']}**\n💰 Ціна: {s['price']} грн"

        if s.get('image'):
            photo_url = f"{BASE_URL}{s['image']}" if s['image'].startswith('/') else s['image']
            msg = await callback.message.answer_photo(
                photo=photo_url, caption=caption, reply_markup=kb.as_markup(), parse_mode="Markdown"
            )
        else:
            msg = await callback.message.answer(
                caption, reply_markup=kb.as_markup(), parse_mode="Markdown"
            )
        sent_msg_ids.append(msg.message_id)

    # Кнопка повернення
    kb_back = InlineKeyboardBuilder()
    kb_back.button(text="🏠 Головне меню", callback_data="back_to_main")
    msg_back = await callback.message.answer("Або поверніться назад:", reply_markup=kb_back.as_markup())
    sent_msg_ids.append(msg_back.message_id)

    # Зберігаємо список повідомлень у стан
    await state.update_data(service_msg_ids=sent_msg_ids)


@router.callback_query(ServiceCb.filter(), BookingState.choosing_service)
async def process_service_selection(callback: types.CallbackQuery, callback_data: ServiceCb, state: FSMContext):
    # Спочатку завантажуємо послуги, щоб витягнути назву та ціну обраної
    services = await fetch_api('services/')
    selected_service = next((s for s in services if s['id'] == callback_data.id), None)

    if not selected_service:
        await callback.answer("Помилка: Послугу не знайдено.", show_alert=True)
        return

    # Зберігаємо дані в пам'ять (FSM)
    await state.update_data(
        service_id=selected_service['id'],
        service_name=selected_service['proposition'],
        service_price=selected_service['price']
    )

    schedule = await fetch_api('schedule/')
    if schedule is None:
        await callback.answer("Помилка завантаження графіка.", show_alert=True)
        return

    # Очищаємо чат від карток послуг!
    await clear_service_cards(callback.message, state)

    working_days_map = {d['day_index']: d['is_working'] for d in schedule}
    kb = InlineKeyboardBuilder()
    start_date = datetime.now()

    date_buttons = []
    for i in range(1, 31):
        curr_date = start_date + timedelta(days=i)
        date_str = curr_date.strftime("%Y-%m-%d")
        display_str = curr_date.strftime("%d.%m")

        if working_days_map.get(curr_date.weekday(), False):
            date_buttons.append(types.InlineKeyboardButton(
                text=f"{display_str}", callback_data=DateCb(val=date_str).pack()
            ))
        else:
            date_buttons.append(types.InlineKeyboardButton(
                text=f"❌ {display_str}", callback_data=f"off_{display_str}"
            ))

    kb.row(*date_buttons)
    kb.adjust(4)  # По 4 дні в ряд

    kb.row(types.InlineKeyboardButton(text="⬅️ Назад до послуг", callback_data="start_booking"))
    kb.row(types.InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main"))

    await callback.message.answer(
        f"📅 **Крок 2: Оберіть дату**\nПослуга: *{selected_service['proposition']}*\n\n❌ — вихідний день.",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(BookingState.choosing_date)


@router.callback_query(F.data.startswith("off_"))
async def weekend_clicked(callback: types.CallbackQuery):
    date_clicked = callback.data.split("_")[1]
    await callback.answer(f"{date_clicked} — це вихідний день!", show_alert=True)


@router.callback_query(DateCb.filter(), BookingState.choosing_date)
async def process_date_selection(callback: types.CallbackQuery, callback_data: DateCb, state: FSMContext):
    date_val = callback_data.val
    await state.update_data(date=date_val)

    user_data = await state.get_data()
    schedule = await fetch_api('schedule/')

    dt_obj = datetime.strptime(date_val, "%Y-%m-%d")
    day_config = next((d for d in schedule if d['day_index'] == dt_obj.weekday()), None)

    if not day_config or not day_config['hours']:
        await callback.answer("На цей день немає вільних годин.", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    for slot in day_config['hours']:
        time_display = slot['hour']
        hour_int = int(time_display.split(":")[0])
        kb.button(text=f"🕒 {time_display}", callback_data=TimeCb(val=time_display, hour=hour_int).pack())

    kb.adjust(3)

    # Кнопка повернення до тієї ж самої послуги
    kb.row(types.InlineKeyboardButton(
        text="⬅️ Інша дата", callback_data=ServiceCb(id=user_data['service_id']).pack()
    ))

    display_date = dt_obj.strftime("%d.%m.%Y")
    await callback.message.edit_text(
        f"⏰ **Крок 3: Оберіть час**\nДата: *{display_date}*\nПослуга: *{user_data['service_name']}*",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(BookingState.choosing_time)


@router.callback_query(TimeCb.filter(), BookingState.choosing_time)
async def process_time_selection(callback: types.CallbackQuery, callback_data: TimeCb, state: FSMContext):
    user_data = await state.get_data()

    client_nickname = f"@{callback.from_user.username}" if callback.from_user.username else "Немає нікнейму"

    payload = {
        "client_name": callback.from_user.full_name,
        "client_nickname": client_nickname,
        "date": user_data['date'],
        "time_slot": callback_data.hour,
        "proposition": user_data['service_id'],
        "price": user_data['service_price']
    }

    result, status = await post_api('book/', payload)

    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Головне меню", callback_data="back_to_main")

    if status == 201:
        dt_display = datetime.strptime(user_data['date'], "%Y-%m-%d").strftime("%d.%m.%Y")
        await callback.message.edit_text(
            f"✅ **Заявку успішно створено!**\n\n"
            f"👤 **Клієнт:** {callback.from_user.full_name} ({client_nickname})\n"
            f"🛠 **Послуга:** {user_data['service_name']}\n"
            f"📅 **Дата:** {dt_display}\n"
            f"⏰ **Час:** {callback_data.val}\n"
            f"💵 **До сплати:** {user_data['service_price']} грн\n\n"
            f"⏳ *Запис очікує на підтвердження майстром.*",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
    else:
        error_msg = "Цей час уже зайнятий або недоступний."
        if isinstance(result, dict):
            error_list = result.get('time_slot', result.get('date', result.get('non_field_errors', [error_msg])))
            error_msg = error_list[0] if isinstance(error_list, list) else error_msg

        await callback.message.edit_text(
            f"❌ **Помилка запису**\n\nПричина: {error_msg}",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )

    await state.clear()


# ==========================================
# 6. ЗАПУСК БОТА
# ==========================================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот успішно запущений!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())