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

# Оставляем красивое системное логирование + наши принты
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


class PageCb(CallbackData, prefix="page"):
    idx: int


class CancelAppointmentCb(CallbackData, prefix="cancel_apt"):
    id: int


# ==========================================
# 3. API КЛІЄНТ (З логуванням у термінал)
# ==========================================
async def fetch_api(endpoint: str):
    print(f"\n[API GET] Запит до ендпоінту: {API_BASE_URL}{endpoint}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_BASE_URL}{endpoint}") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"[API GET SUCCESS] Отримано об'єктів: {len(data) if isinstance(data, list) else '1'}")
                    return data
                print(f"[API GET ERROR] Сервер повернув статус: {response.status}")
        except Exception as e:
            print(f"[API CONNECTION FAILED] Помилка з'єднання: {e}")
        return None


async def post_api(endpoint: str, data: dict):
    print(f"\n[API POST] Надсилання даних на {API_BASE_URL}{endpoint}")
    print(f"[API POST PAYLOAD] Дані запиту: {data}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{API_BASE_URL}{endpoint}", json=data) as response:
                res_json = await response.json()
                print(f"[API POST RESPONSE] Статус-код: {response.status} | Відповідь: {res_json}")
                return res_json, response.status
        except Exception as e:
            print(f"[API POST FAILED] Помилка запиту: {e}")
            return {"error": "Connection failed"}, 500


async def delete_api(endpoint: str):
    print(f"\n[API DELETE] Запит на видалення запису: {API_BASE_URL}{endpoint}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.delete(f"{API_BASE_URL}{endpoint}") as response:
                print(f"[API DELETE RESPONSE] Сервер повернув статус-код: {response.status}")
                return response.status
        except Exception as e:
            print(f"[API DELETE FAILED] Не вдалося виконати DELETE-запит: {e}")
            return 500


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
    services = await fetch_api('services/')
    available_services = [s for s in services if s.get('available', True)] if services else []

    if not available_services:
        print("[UI WARN] Спроба відкрити послуги, але список порожній у базі.")
        await message.edit_text(
            "🚨 Список послуг наразі порожній.\nСпробуйте пізніше.",
            reply_markup=InlineKeyboardBuilder().button(text="🏠 Меню", callback_data="back_to_main").as_markup()
        )
        return

    if page_index >= len(available_services):
        page_index = 0
    elif page_index < 0:
        page_index = len(available_services) - 1

    current_service = available_services[page_index]

    text = (
        f"🛠 **Крок 1: Оберіть послугу**\n\n"
        f"📋 **Назва:** {current_service['proposition']}\n"
        f"💰 **Вартість:** {current_service['price']} грн\n\n"
        f"📖 *Послуга {page_index + 1} із {len(available_services)}*"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="⬅️ Минуло", callback_data=PageCb(idx=page_index - 1).pack()),
        types.InlineKeyboardButton(text="Далі ➡️", callback_data=PageCb(idx=page_index + 1).pack())
    )
    kb.row(types.InlineKeyboardButton(
        text="✅ Обрати цю послугу",
        callback_data=ServiceCb(id=current_service['id']).pack()
    ))
    kb.row(types.InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main"))

    await state.set_state(BookingState.choosing_service)
    await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


async def show_dates_screen(message: types.Message, service_name: str, service_price: float, state: FSMContext):
    schedule = await fetch_api('schedule/')
    if schedule is None:
        print("[ERROR] Не вдалося отримати графік з Django для побудови календаря.")
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
    schedule = await fetch_api('schedule/')
    if not schedule:
        print("[ERROR] Не можемо завантажити години для екрану вибору часу.")
        await message.edit_text("🚨 Помилка: Не вдалося отримати графік з сервера.")
        return

    dt_obj = datetime.strptime(date_val, "%Y-%m-%d")
    target_weekday = dt_obj.weekday()

    day_config = next((d for d in schedule if int(d['day_index']) == target_weekday), None)

    if not day_config or not day_config.get('hours'):
        print(f"[UI INFO] На день {date_val} (день тижня {target_weekday}) відсутні робочі години.")
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
    print(f"\n[ACTION] Користувач {message.from_user.full_name} (@{message.from_user.username}) ввів /start")
    await state.clear()
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    text, reply_markup = get_main_menu_data()
    await message.answer(text, reply_markup=reply_markup, parse_mode="Markdown")


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    print(f"[BUTTON CLICKED] Кнопка: Головне меню | Користувач: {callback.from_user.full_name}")
    await state.clear()
    await callback.answer()
    text, reply_markup = get_main_menu_data()
    await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="Markdown")


@router.callback_query(F.data == "start_booking")
async def process_start_booking(callback: types.CallbackQuery, state: FSMContext):
    print(f"[BUTTON CLICKED] Кнопка: Записатися на послугу | Користувач: {callback.from_user.full_name}")
    await callback.answer()
    await show_services_page(callback.message, page_index=0, state=state)


@router.callback_query(PageCb.filter())
async def process_service_pagination(callback: types.CallbackQuery, callback_data: PageCb, state: FSMContext):
    print(f"[BUTTON CLICKED] Кнопка: Пагінація послуг (Перехід на індекс {callback_data.idx})")
    await callback.answer()
    await show_services_page(callback.message, page_index=callback_data.idx, state=state)


@router.callback_query(ServiceCb.filter())
async def process_service_selected(callback: types.CallbackQuery, callback_data: ServiceCb, state: FSMContext):
    print(f"[BUTTON CLICKED] Кнопка: Обрати цю послугу | ID обраної послуги: {callback_data.id}")
    await callback.answer()
    services = await fetch_api('services/')
    selected_service = next((s for s in services if s['id'] == callback_data.id), None)

    if not selected_service:
        print(f"[ERROR] Кнопка натиснута, але ERROR: не можемо дістати дані про послугу з ID {callback_data.id}")
        await callback.message.edit_text("Помилка: Послугу не знадено.")
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
    print(f"[BUTTON CLICKED] Кнопка: Назад до дат | Користувач: {callback.from_user.full_name}")
    await callback.answer()
    user_data = await state.get_data()

    if 'service_name' not in user_data:
        print("[WARN] Дані FSM порожні при переході назад. Повертаємо на вибір послуг.")
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
    print(f"[BUTTON CLICKED] Кнопка: Вихідний день ({callback.data}) | Повідомлено користувача.")
    await callback.answer("Цей день є вихідним, оберіть іншу дату!", show_alert=True)


@router.callback_query(DateCb.filter())
async def process_date_selected(callback: types.CallbackQuery, callback_data: DateCb, state: FSMContext):
    print(f"[BUTTON CLICKED] Кнопка: Дата обрана | Значення: {callback_data.val}")
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


@router.callback_query(TimeCb.filter(), BookingState.choosing_time)
async def process_time(callback: types.CallbackQuery, callback_data: TimeCb, state: FSMContext):
    print(f"[BUTTON CLICKED] Кнопка: Час обрано | Валідне значення: {callback_data.val}, година: {callback_data.hour}")
    await callback.answer()
    user_data = await state.get_data()
    client_nickname = f"@{callback.from_user.username}" if callback.from_user.username else "Приховано"

    payload = {
        "client_name": callback.from_user.full_name,
        "client_nickname": client_nickname,
        "date": user_data['date'],
        "time_slot": callback_data.hour,
        "proposition": user_data['service_id'],
        "price": user_data['service_price']
    }

    # Отправляем запрос
    result, status_code = await post_api('book/', payload)

    kb = InlineKeyboardBuilder()

    if status_code == 201:
        created_id = result.get('id')
        print(f"[SUCCESS] Запис створено в базі Django! Присвоєно Номер №{created_id}")

        dt_display = datetime.strptime(user_data['date'], "%Y-%m-%d").strftime("%d.%m.%Y")
        time_display = callback_data.val.replace("-", ":")

        text = (
            f"⏳ **Ваш запис №{created_id} очікує підтвердження майстра.**\n\n"
            f"📋 **Послуга:** {user_data['service_name']}\n"
            f"📅 **Дата:** {dt_display}\n"
            f"⏰ **Час:** {time_display}\n"
            f"💵 **До сплати:** {user_data['service_price']} грн\n\n"
            f"📱 _Ви можете скасувати запис нижче, якщо ваші плани зміняться._"
        )

        if created_id:
            kb.button(text="❌ Відмінити запис", callback_data=CancelAppointmentCb(id=created_id).pack())
    else:
        # УДОБНЫЙ ВЫВОД ОШИБКИ В ТЕРМИНАЛ:
        print(f"\n[ERROR] Кнопка натиснута, але ERROR: не можемо дістати дані або зберегти запис!")
        print(f"[ERROR DETAILS] Статус відповіді сервера: {status_code} | Текст помилки валідації: {result}\n")

        text = f"❌ **Сталася помилка**\n\nМожливо, цей час щойно зайняли. Спробуйте обрати інший."

    kb.row(types.InlineKeyboardButton(text="🏠 На головну", callback_data="back_to_main"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    await state.clear()


# ХЕНДЛЕР ОБРАБОТКИ ОТМЕНЫ ЗАПИСИ КЛИЕНТОМ:
@router.callback_query(CancelAppointmentCb.filter())
async def process_cancel_appointment(callback: types.CallbackQuery, callback_data: CancelAppointmentCb):
    print(f"[BUTTON CLICKED] Кнопка: Відмінити запис | Запит на видалення ID: {callback_data.id}")
    await callback.answer()

    endpoint = f"book/{callback_data.id}/delete/"
    status_code = await delete_api(endpoint)

    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 На головну", callback_data="back_to_main")

    if status_code in [200, 204]:
        print(f"[SUCCESS] Запис №{callback_data.id} успішно видалено з бази даних!")
        text = "🗑 **Запис успішно скасовано та видалено з бази даних!**"
    else:
        print(
            f"[ERROR] Кнопка натиснута, але ERROR: не вдалося видалити запис №{callback_data.id} з Django. Статус-код: {status_code}")
        text = "🚨 **Не вдалося скасувати запис.**\n\nМожливо, він уже видалений або підтверджений."

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


# ==========================================
# 6. ЗАПУСК
# ==========================================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("\n" + "=" * 50)
    print("[SERVER START] Бот успішно запущений в режимі чистого інтерфейсу!")
    print("[SERVER INFO] Спостереження за діями користувачів активоване.")
    print("=" * 50 + "\n")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())