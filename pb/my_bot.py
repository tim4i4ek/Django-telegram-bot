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
# 1. НАЛАШТУВАННЯ ТА ІНІЦІАЛІЗАЦІЯ
# ==========================================
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_BASE_URL = 'http://127.0.0.1:8000/api/'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ==========================================
# 2. СТАНИ ТА КОЛБЕКИ (FSM)
# ==========================================
class BookingState(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()


class ServiceCb(CallbackData, prefix="srv"):
    id: int


class DateCb(CallbackData, prefix="date"):
    val: str


class TimeCb(CallbackData, prefix="time"):
    val: str
    hour: int


# Пагінація для чистого перегляду довгих послуг
class PageCb(CallbackData, prefix="page"):
    idx: int


# ==========================================
# 3. API КЛІЄНТ
# ==========================================
async def fetch_api(endpoint: str):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_BASE_URL}{endpoint}") as response:
                if response.status == 200:
                    return await response.json()
                logging.error(f"API Error {endpoint}: Status {response.status}")
        except Exception as e:
            logging.error(f"API Connection Error: {e}")
        return None


async def post_api(endpoint: str, data: dict):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{API_BASE_URL}{endpoint}", json=data) as response:
                return await response.json(), response.status
        except Exception as e:
            logging.error(f"API Post Error: {e}")
            return {"error": "Connection failed"}, 500


# ==========================================
# 4. ЧИСТИЙ ІНТЕРФЕЙС: ЕКРАНИ (UI)
# ==========================================

def get_main_menu_data():
    text = (
        "👋 **Ласкаво просимо до нашої майстерні!**\n\n"
        "🔧 Ми спеціалізуємося на професійному обслуговуванні.\n"
        "📅 Тут ви можете швидко та зручно переглянути вільні години та записатися."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Записатися на послугу", callback_data="start_booking")
    return text, kb.as_markup()


async def show_services_page(message: types.Message, page_index: int, state: FSMContext):
    """Каталог послуг у вигляді акуратних карток з пагінацією (вперед/назад)"""
    services = await fetch_api('services/')
    # Фільтруємо лише доступні
    available_services = [s for s in services if s.get('available', True)] if services else []

    if not available_services:
        await message.edit_text(
            "🚨 Список послуг наразі порожній.\nСпробуйте пізніше.",
            reply_markup=InlineKeyboardBuilder().button(text="🏠 Меню", callback_data="back_to_main").as_markup()
        )
        return

    # Захист від виходу за межі списку послуг
    if page_index >= len(available_services):
        page_index = 0
    elif page_index < 0:
        page_index = len(available_services) - 1

    current_service = available_services[page_index]

    # Будуємо гарний чистий текст (назва послуги може бути будь-якої довжини!)
    text = (
        f"🛠 **Крок 1: Оберіть послугу**\n\n"
        f"📋 **Назва:** {current_service['proposition']}\n"
        f"💰 **Вартість:** {current_service['price']} грн\n\n"
        f"📖 *Послуга {page_index + 1} із {len(available_services)}*"
    )

    kb = InlineKeyboardBuilder()

    # Ряд кнопок перемикання (Пагінація)
    kb.row(
        types.InlineKeyboardButton(text="⬅️ Минуло", callback_data=PageCb(idx=page_index - 1).pack()),
        types.InlineKeyboardButton(text="Далі ➡️", callback_data=PageCb(idx=page_index + 1).pack())
    )
    # Кнопка вибору конкретно цієї послуги
    kb.row(types.InlineKeyboardButton(
        text="✅ Обрати цю послугу",
        callback_data=ServiceCb(id=current_service['id']).pack()
    ))
    # Повернення в меню
    kb.row(types.InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main"))

    await state.set_state(BookingState.choosing_service)
    await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


async def show_dates_screen(message: types.Message, service_name: str, service_price: float, state: FSMContext):
    """Календар вибору дат"""
    schedule = await fetch_api('schedule/')
    if schedule is None:
        await message.edit_text("Помилка завантаження графіка робочих днів.")
        return

    working_days_map = {int(d['day_index']): d['is_working'] for d in schedule}
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
                text=f"❌", callback_data=f"off_{display_str}"
            ))

    kb.row(*date_buttons)
    kb.adjust(4)

    kb.row(types.InlineKeyboardButton(text="⬅️ Назад до послуг", callback_data="start_booking"))
    kb.row(types.InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main"))

    text = (
        f"📅 **Крок 2: Оберіть дату візиту**\n\n"
        f"📋 Послуга: *{service_name}*\n"
        f"💰 Вартість: *{service_price} грн*\n\n"
        f"❌ — означає вихідний день майстра."
    )
    await state.set_state(BookingState.choosing_date)
    await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


async def show_times_screen(message: types.Message, date_val: str, service_name: str, state: FSMContext):
    """Екран вибору вільного часу"""
    schedule = await fetch_api('schedule/')
    if not schedule:
        await message.edit_text("🚨 Помилка: Не вдалося отримати графік з сервера.")
        return

    dt_obj = datetime.strptime(date_val, "%Y-%m-%d")
    target_weekday = dt_obj.weekday()

    day_config = next((d for d in schedule if int(d['day_index']) == target_weekday), None)

    if not day_config or not day_config.get('hours'):
        await message.edit_text(
            "❌ На цей день немає вільних годин для запису.",
            reply_markup=InlineKeyboardBuilder().button(text="⬅️ Назад до дат",
                                                        callback_data="back_to_dates").as_markup()
        )
        return

    kb = InlineKeyboardBuilder()
    for slot in day_config['hours']:
        time_display = slot['hour']
        hour_int = int(time_display.split(":")[0])
        safe_time_val = time_display.replace(":", "-")

        kb.button(text=f"🕒 {time_display}", callback_data=TimeCb(val=safe_time_val, hour=hour_int).pack())

    kb.adjust(3)
    kb.row(types.InlineKeyboardButton(text="⬅️ Обрати іншу дату", callback_data="back_to_dates"))
    kb.row(types.InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main"))

    display_date = dt_obj.strftime("%d.%m.%Y")
    text = (
        f"⏰ **Крок 3: Оберіть зручний час**\n\n"
        f"📅 Дата: *{display_date}*\n"
        f"📋 Послуга: *{service_name}*"
    )

    await state.set_state(BookingState.choosing_time)
    await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


# ==========================================
# 5. ХЕНДЛЕРИ ТА ОБРОБКА ПОДІЙ
# ==========================================

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    text, reply_markup = get_main_menu_data()
    await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    text, reply_markup = get_main_menu_data()
    await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")


@router.callback_query(F.data == "start_booking")
async def process_start_booking(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    # Завжди стартуємо з першої послуги (індекс 0)
    await show_services_page(callback.message, page_index=0, state=state)


@router.callback_query(PageCb.filter())
async def process_service_pagination(callback: types.CallbackQuery, callback_data: PageCb, state: FSMContext):
    """Обробка перемикання послуг «Вліво / Вправо»"""
    await callback.answer()
    await show_services_page(callback.message, page_index=callback_data.idx, state=state)


@router.callback_query(ServiceCb.filter())
async def process_service_selected(callback: types.CallbackQuery, callback_data: ServiceCb, state: FSMContext):
    await callback.answer()
    services = await fetch_api('services/')
    selected_service = next((s for s in services if s['id'] == callback_data.id), None)

    if not selected_service:
        await callback.message.edit_text("Помилка: Послугу не знайдено.")
        return

    await state.update_data(
        service_id=selected_service['id'],
        service_name=selected_service['proposition'],
        service_price=selected_service['price']
    )

    await show_dates_screen(
        message=callback.message,
        service_name=selected_service['proposition'],
        service_price=selected_service['price'],
        state=state
    )


@router.callback_query(F.data == "back_to_dates")
async def process_back_to_dates(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_data = await state.get_data()

    if 'service_name' not in user_data:
        await show_services_page(callback.message, page_index=0, state=state)
        return

    await show_dates_screen(
        message=callback.message,
        service_name=user_data['service_name'],
        service_price=user_data['service_price'],
        state=state
    )


@router.callback_query(F.data.startswith("off_"))
async def weekend_clicked(callback: types.CallbackQuery):
    await callback.answer("Цей день є вихідним, оберіть іншу дату!", show_alert=True)


@router.callback_query(DateCb.filter())
async def process_date_selected(callback: types.CallbackQuery, callback_data: DateCb, state: FSMContext):
    await callback.answer()
    date_val = callback_data.val
    await state.update_data(date=date_val)

    user_data = await state.get_data()
    await show_times_screen(
        message=callback.message,
        date_val=date_val,
        service_name=user_data.get('service_name', 'Послуга'),
        state=state
    )


@router.callback_query(TimeCb.filter())
async def process_time_final_booking(callback: types.CallbackQuery, callback_data: TimeCb, state: FSMContext):
    await callback.answer()
    user_data = await state.get_data()

    beautiful_time = callback_data.val.replace("-", ":")
    client_nickname = f"@{callback.from_user.username}" if callback.from_user.username else "Приховано"

    payload = {
        "client_name": callback.from_user.full_name,
        "client_nickname": client_nickname,
        "date": user_data['date'],
        "time_slot": callback_data.hour,
        "proposition": user_data['service_id'],
        "price": user_data['price'] if 'price' in user_data else user_data['service_price']
    }

    result, status_code = await post_api('book/', payload)

    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Повернутися на головну", callback_data="back_to_main")

    if status_code == 201:
        dt_display = datetime.strptime(user_data['date'], "%Y-%m-%d").strftime("%d.%m.%Y")
        text = (
            f"✅ **Заявку успішно створено!**\n\n"
            f"🛠 **Послуга:** {user_data['service_name']}\n"
            f"📅 **Дата:** {dt_display}\n"
            f"⏰ **Час:** {beautiful_time}\n"
            f"💵 **До сплати:** {user_data['service_price']} грн\n\n"
            f"⏳ *Майстер зв'яжеться з вами для підтвердження.*"
        )
    else:
        text = f"❌ **Сталася помилка**\n\nМожливо, цей час щойно зайняли або сервер відхилив запит."

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    await state.clear()


# ==========================================
# 6. ЗАПУСК
# ==========================================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот успішно запущений в режимі чистого інтерфейсу!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())