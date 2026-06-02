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


class StaffState(StatesGroup):
    browsing_appointments = State()


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


class StaffPageCb(CallbackData, prefix="st_page"):
    idx: int


class StaffDeleteCb(CallbackData, prefix="st_del"):
    id: int


# ==========================================
# 3. API КЛІЄНТ (З логами для термінала)
# ==========================================
async def fetch_api(endpoint: str):
    print(f"\n[API GET] Запит до ендпоінту: {API_BASE_URL}{endpoint}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_BASE_URL}{endpoint}") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"[API GET SUCCESS] Дані отримано успішно.")
                    return data
                print(f"[API GET ERROR] Сервер повернув статус: {response.status}")
        except Exception as e:
            print(f"[API CONNECTION FAILED] Помилка з'єднання: {e}")
        return None


async def post_api(endpoint: str, data: dict):
    print(f"\n[API POST] Надсилання даних на {API_BASE_URL}{endpoint}")
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
# 4. ИНТЕРФЕЙС И ЭКРАНЫ (UI)
# ==========================================
def get_main_menu_data():
    text = (
        "👋 **Ласкаво просимо до нашої майстерні!**\n\n"
        "🔧 Ми спеціалізуємося на професійному обслуговуванні.\n"
        "📅 Тут ви можете швидко та зручно переглянути вільні години та записатися."
    )
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📅 Записатися на послугу", callback_data="start_booking"))
    kb.row(types.InlineKeyboardButton(text="📋 Мої записи",
                                      callback_data="my_appointments"))  # Добавили кнопку всех записей клиента
    return text, kb.as_markup()


async def show_services_page(message: types.Message, page_index: int, state: FSMContext):
    services = await fetch_api('services/')
    available_services = [s for s in services if s.get('available', True)] if services else []

    if not available_services:
        print("[UI WARN] Спроба відкрити послуги, але список порожній у базі.")
        await message.edit_text("🚨 Список послуг наразі порожній.\nСпробуйте пізніше.",
                                reply_markup=InlineKeyboardBuilder().button(text="🏠 Меню",
                                                                            callback_data="back_to_main").as_markup())
        return

    if page_index >= len(available_services):
        page_index = 0
    elif page_index < 0:
        page_index = len(available_services) - 1

    current_service = available_services[page_index]
    text = f"🛠 **Крок 1: Оберіть послугу**\n\n📋 **Назва:** {current_service['proposition']}\n💰 **Вартість:** {current_service['price']} грн\n\n📖 *Послуга {page_index + 1} із {len(available_services)}*"

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="⬅️ Минуло", callback_data=PageCb(idx=page_index - 1).pack()),
           types.InlineKeyboardButton(text="Далі ➡️", callback_data=PageCb(idx=page_index + 1).pack()))
    kb.row(types.InlineKeyboardButton(text="✅ Обрати цю послугу",
                                      callback_data=ServiceCb(id=current_service['id']).pack()))
    kb.row(types.InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main"))

    await state.set_state(BookingState.choosing_service)
    await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


async def show_dates_screen(message: types.Message, service_name: str, service_price: float, state: FSMContext):
    schedule = await fetch_api('schedule/')
    if schedule is None:
        print("[ERROR] Не вдалося завантажити графік.")
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
            date_buttons.append(
                types.InlineKeyboardButton(text=f"{display_str}", callback_data=DateCb(val=date_str).pack()))
        else:
            date_buttons.append(types.InlineKeyboardButton(text=f"❌", callback_data=f"off_{display_str}"))

    kb.row(*date_buttons)
    kb.adjust(4)
    kb.row(types.InlineKeyboardButton(text="⬅️ Назад до послуг", callback_data="start_booking"))
    kb.row(types.InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main"))

    text = f"📅 **Крок 2: Оберіть дату візиту**\n\n📋 Послуга: *{service_name}*\n💰 Вартість: *{service_price} грн*\n\n❌ — означає вихідний день майстра."
    await state.set_state(BookingState.choosing_date)
    await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


async def show_times_screen(message: types.Message, date_val: str, service_name: str, state: FSMContext):
    schedule = await fetch_api('schedule/')
    if not schedule:
        print("[ERROR] Не вдалося завантажити години.")
        await message.edit_text("🚨 Помилка: Не вдалося отримати графік з сервера.")
        return

    dt_obj = datetime.strptime(date_val, "%Y-%m-%d")
    day_config = next((d for d in schedule if int(d['day_index']) == dt_obj.weekday()), None)

    if not day_config or not day_config.get('hours'):
        await message.edit_text("❌ На цей день немає вільних годин.",
                                reply_markup=InlineKeyboardBuilder().button(text="⬅️ Назад",
                                                                            callback_data="back_to_dates").as_markup())
        return

    kb = InlineKeyboardBuilder()
    for slot in day_config['hours']:
        time_display = slot['hour']
        kb.button(text=f"🕒 {time_display}",
                  callback_data=TimeCb(val=time_display.replace(":", "-"), hour=int(time_display.split(":")[0])).pack())

    kb.adjust(3)
    kb.row(types.InlineKeyboardButton(text="⬅️ Обрати іншу дату", callback_data="back_to_dates"))
    kb.row(types.InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main"))

    await state.set_state(BookingState.choosing_time)
    await message.edit_text(
        f"⏰ **Крок 3: Оберіть зручний час**\n\n📅 Дата: *{dt_obj.strftime('%d.%m.%Y')}*\n📋 Послуга: *{service_name}*",
        reply_markup=kb.as_markup(), parse_mode="Markdown")


# Экран Панели Работника (Админка ТГ)
async def show_staff_appointments_page(message: types.Message, page_index: int, staff_name: str, company_name: str,
                                       state: FSMContext):
    appointments = await fetch_api('staff/appointments/')

    if not appointments:
        text = f"👋 **Привіт, {staff_name}!**\nЯ роботник компанії **{company_name}**.\n\n🚨 **Наразі немає жодного запису в базі даних.**"
        kb = InlineKeyboardBuilder().button(text="🏠 На головну", callback_data="back_to_main")
        try:
            await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
        except Exception:
            await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
        return

    if page_index >= len(appointments):
        page_index = 0
    elif page_index < 0:
        page_index = len(appointments) - 1

    apt = appointments[page_index]
    dt_display = datetime.strptime(apt['date'], "%Y-%m-%d").strftime("%d.%m.%Y")

    text = (
        f"👋 **Привіт, {staff_name}!**\n"
        f"💼 Я роботник **{staff_name}** із компанії **{company_name}**.\n"
        f"───────────────────\n"
        f"📋 **Заявка №{apt['id']}** (Картка {page_index + 1} із {len(appointments)})\n\n"
        f"👤 **Клієнт:** {apt['client_name']}\n"
        f"📱 **Нікнейм:** {apt['client_nickname']}\n"
        f"📅 **Дата:** {dt_display}\n"
        f"⏰ **Час візиту:** {apt['time_slot']}:00\n"
        f"💵 **Вартість:** {apt['price']} грн"
    )

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="⬅️ Минулий", callback_data=StaffPageCb(idx=page_index - 1).pack()),
           types.InlineKeyboardButton(text="Наступний ➡️", callback_data=StaffPageCb(idx=page_index + 1).pack()))

    if apt['client_nickname'] and apt['client_nickname'] != "Приховано":
        kb.row(types.InlineKeyboardButton(text="💬 Написати клієнту",
                                          url=f"https://t.me/{apt['client_nickname'].replace('@', '')}"))

    kb.row(
        types.InlineKeyboardButton(text="❌ Скасувати/Видалити запис", callback_data=StaffDeleteCb(id=apt['id']).pack()))
    kb.row(types.InlineKeyboardButton(text="🏠 Вийти з адмінки", callback_data="back_to_main"))

    await state.update_data(staff_page_idx=page_index, staff_name=staff_name, company_name=company_name)
    await state.set_state(StaffState.browsing_appointments)

    try:
        await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except Exception:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


# ==========================================
# 5. ХЕНДЛЕРЫ КЛИЕНТА
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
    print(f"[BUTTON CLICKED] Кнопка: Записатися на послугу")
    await callback.answer()
    await show_services_page(callback.message, page_index=0, state=state)


@router.callback_query(PageCb.filter())
async def process_service_pagination(callback: types.CallbackQuery, callback_data: PageCb, state: FSMContext):
    await callback.answer()
    await show_services_page(callback.message, page_index=callback_data.idx, state=state)


@router.callback_query(ServiceCb.filter())
async def process_service_selected(callback: types.CallbackQuery, callback_data: ServiceCb, state: FSMContext):
    print(f"[BUTTON CLICKED] Кнопка: Обрати цю послугу ID: {callback_data.id}")
    await callback.answer()
    services = await fetch_api('services/')
    selected_service = next((s for s in services if s['id'] == callback_data.id), None)

    if not selected_service:
        await callback.message.edit_text("Помилка: Послугу не знадено.")
        return

    await state.update_data(service_id=selected_service['id'], service_name=selected_service['proposition'],
                            service_price=selected_service['price'])
    await show_dates_screen(callback.message, selected_service['proposition'], selected_service['price'], state)


@router.callback_query(F.data == "back_to_dates")
async def process_back_to_dates(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_data = await state.get_data()
    await show_dates_screen(callback.message, user_data.get('service_name', 'Послуга'),
                            user_data.get('service_price', 0), state)


@router.callback_query(F.data.startswith("off_"))
async def weekend_clicked(callback: types.CallbackQuery):
    await callback.answer("Цей день є вихідним, оберіть іншу дату!", show_alert=True)


@router.callback_query(DateCb.filter())
async def process_date_selected(callback: types.CallbackQuery, callback_data: DateCb, state: FSMContext):
    await callback.answer()
    await state.update_data(date=callback_data.val)
    user_data = await state.get_data()
    await show_times_screen(callback.message, callback_data.val, user_data.get('service_name', 'Послуга'), state)


@router.callback_query(TimeCb.filter(), BookingState.choosing_time)
async def process_time(callback: types.CallbackQuery, callback_data: TimeCb, state: FSMContext):
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

    result, status_code = await post_api('book/', payload)
    kb = InlineKeyboardBuilder()

    if status_code == 201:
        created_id = result.get('id')
        print(f"[SUCCESS] Запис створено! Номер №{created_id}")
        dt_display = datetime.strptime(user_data['date'], "%Y-%m-%d").strftime("%d.%m.%Y")
        text = f"⏳ **Ваш запис №{created_id} очікує підтвердження майстра.**\n\n📋 **Послуга:** {user_data['service_name']}\n📅 **Дата:** {dt_display}\n⏰ **Час:** {callback_data.val.replace('-', ':')}\n💵 **До сплати:** {user_data['service_price']} грн"
        kb.button(text="❌ Відмінити цей запис", callback_data=CancelAppointmentCb(id=created_id).pack())
    else:
        # Ловим ошибку валидации (например, лимит 3 записей превышен)
        print(f"[ERROR] Не вдалося зберегти запис. Код: {status_code} | Відповідь: {result}")
        error_msg = result.get('non_field_errors', [None])[
                        0] or "Можливо, цей час щойно зайняли або ви перевищили лімит у 3 активні записи."
        text = f"❌ **Сталася помилка при записі**\n\n{error_msg}"

    kb.row(types.InlineKeyboardButton(text="🏠 На головну", callback_data="back_to_main"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    await state.clear()


# ==========================================
# ⚡ НОВАЯ ФИЧА: КНОПКА "МОЇ ЗАПИСИ" ДЛЯ КЛИЕНТА
# ==========================================
@router.callback_query(F.data == "my_appointments")
async def show_client_appointments(callback: types.CallbackQuery):
    if not callback.from_user.username:
        await callback.answer("🚨 У вас має бути встановлений Username в налаштуваннях ТГ!", show_alert=True)
        return

    await callback.answer()
    nickname = callback.from_user.username
    appointments = await fetch_api(f"client/appointments/{nickname}/")

    kb = InlineKeyboardBuilder()

    if not appointments:
        text = "📋 **У вас немає жодного активного запису.**"
    else:
        text = f"📋 **Ваші активні записи (всього: {len(appointments)}/3):**\n\n"
        for idx, apt in enumerate(appointments, 1):
            dt_display = datetime.strptime(apt['date'], "%Y-%m-%d").strftime("%d.%m")
            text += f"{idx}. **Запис №{apt['id']}** — 📅 {dt_display} о ⏰ {apt['time_slot']}:00\n"
            # Под каждой записью генерируем кнопку отмены
            kb.row(types.InlineKeyboardButton(text=f"❌ Скасувати №{apt['id']}",
                                              callback_data=CancelAppointmentCb(id=apt['id']).pack()))

    kb.row(types.InlineKeyboardButton(text="🏠 Головне меню", callback_data="back_to_main"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


@router.callback_query(CancelAppointmentCb.filter())
async def process_cancel_appointment(callback: types.CallbackQuery, callback_data: CancelAppointmentCb):
    print(f"[BUTTON CLICKED] Клієнт скасовує запис ID: {callback_data.id}")
    await callback.answer()
    status_code = await delete_api(f"book/{callback_data.id}/delete/")

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="📋 Оновити список записів", callback_data="my_appointments"))
    kb.row(types.InlineKeyboardButton(text="🏠 На головну", callback_data="back_to_main"))

    if status_code in [200, 204]:
        print(f"[SUCCESS] Запис №{callback_data.id} видалено клієнтом.")
        await callback.message.edit_text(f"🗑 **Запис №{callback_data.id} успішно скасовано та видалено!**",
                                         reply_markup=kb.as_markup(), parse_mode="Markdown")
    else:
        await callback.message.edit_text("🚨 **Не вдалося скасувати запис.** Возможно, он уже удален.",
                                         reply_markup=kb.as_markup(), parse_mode="Markdown")


# ==========================================
# 6. ХЕНДЛЕРЫ ДЛЯ КОМАНДЫ РАБОТНИКА (/staff)
# ==========================================
@router.message(F.text == "/staff")
async def cmd_staff_login(message: types.Message, state: FSMContext):
    if not message.from_user.username:
        await message.answer("🚨 Для входу в адмінку у вас повинен бути встановлений Telegram Username.")
        return

    print(f"\n[STAFF TRY] Спроба входу в адмінку від @{message.from_user.username}")
    staff_data = await fetch_api(f"staff/check/{message.from_user.username}/")

    if staff_data and staff_data.get('is_staff'):
        print(f"[STAFF SUCCESS] Працівник {staff_data['name']} успішно увійшов!")
        await show_staff_appointments_page(message, 0, staff_data['name'], staff_data['company_name'], state)
    else:
        await message.answer("🛑 Ви не є зареєстрованим працівником. Доступ закритий.")


@router.callback_query(StaffPageCb.filter(), StaffState.browsing_appointments)
async def process_staff_pagination(callback: types.CallbackQuery, callback_data: StaffPageCb, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await show_staff_appointments_page(callback.message, callback_data.idx, data.get('staff_name'),
                                       data.get('company_name'), state)


@router.callback_query(StaffDeleteCb.filter(), StaffState.browsing_appointments)
async def process_staff_delete(callback: types.CallbackQuery, callback_data: StaffDeleteCb, state: FSMContext):
    print(f"[STAFF ACTION] Адмін видаляет запис ID: {callback_data.id}")
    status_code = await delete_api(f"book/{callback_data.id}/delete/")
    data = await state.get_data()

    if status_code in [200, 204]:
        await callback.answer("🗑 Запис успішно видалено!", show_alert=True)
    else:
        await callback.answer("🚨 Помилка видалення на сервері.", show_alert=True)

    await show_staff_appointments_page(callback.message, data.get('staff_page_idx', 0), data.get('staff_name'),
                                       data.get('company_name'), state)


# ==========================================
# ДОПОЛНИТЕЛЬНЫЕ КОЛБЕКИ ДЛЯ АДМИНКИ БОТА
# ==========================================
class StaffApproveCb(CallbackData, prefix="st_app"):
    id: int


# Стан для перемикання фільтрів в адмінці
class StaffState(StatesGroup):
    browsing_all = State()
    browsing_new = State()


# ==========================================
# ОБНОВЛЕННЫЙ ИНТЕРФЕЙС АДМИН-ПАНЕЛИ
# ==========================================

# Главное меню админки (вызывается по /staff)
async def show_staff_main_menu(message: types.Message, staff_name: str, company_name: str, state: FSMContext):
    appointments = await fetch_api('staff/appointments/') or []

    # Считаем статистику
    total_count = len(appointments)
    new_count = len([a for a in appointments if not a.get('is_approved', False)])
    total_earnings = sum(float(a['price']) for a in appointments if a.get('is_approved', False))

    text = (
        f"💼 **Адмін-панель працівника**\n"
        f"👤 Вітаємо, **{staff_name}**!\n"
        f"🏢 Компанія: `{company_name}`\n"
        f"───────────────────\n"
        f"📊 **Статистика майстерні:**\n"
        f"🔹 Всього активних записів: `{total_count}`\n"
        f"🔸 Очікують підтвердження: `{new_count}`\n"
        f"💰 Підтверджена каса: `{total_earnings:.2f} грн`"
    )

    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text=f"📥 Нові заявки ({new_count})", callback_data="staff_view_new"))
    kb.row(types.InlineKeyboardButton(text="📋 Всі записи по порядку", callback_data="staff_view_all"))
    kb.row(types.InlineKeyboardButton(text="🏠 Вийти на головну", callback_data="back_to_main"))

    await state.update_data(staff_name=staff_name, company_name=company_name)

    try:
        await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except Exception:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


# Экран листания записей (универсальный для "Всех" и "Новых")
async def show_staff_appointments_page(message: types.Message, page_index: int, state: FSMContext,
                                       filter_new_only=False):
    appointments = await fetch_api('staff/appointments/') or []
    user_data = await state.get_data()
    staff_name = user_data.get('staff_name', 'Працівник')
    company_name = user_data.get('company_name', 'Компанія')

    # Фильтруем, если админ нажал смотреть только новые
    if filter_new_only:
        appointments = [a for a in appointments if not a.get('is_approved', False)]
        await state.set_state(StaffState.browsing_new)
    else:
        await state.set_state(StaffState.browsing_all)

    if not appointments:
        mode_text = "нових записів, що очікують обробки," if filter_new_only else "записів у базі даних"
        text = f"👋 **{staff_name}**, наразі немає {mode_text}.\n\nВсі клієнти розібрані!"
        kb = InlineKeyboardBuilder().button(text="⬅️ Назад в адмінку", callback_data="staff_menu_home")
        await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
        return

    # Защита от выхода за границы списка
    if page_index >= len(appointments):
        page_index = 0
    elif page_index < 0:
        page_index = len(appointments) - 1

    apt = appointments[page_index]
    dt_display = datetime.strptime(apt['date'], "%Y-%m-%d").strftime("%d.%m.%Y")

    # Красивый статус подгверждения
    status_icon = "✅ ПІДТВЕРДЖЕНО" if apt.get('is_approved', False) else "⏳ ОЧІКУЄ ПІДТВЕРДЖЕННЯ"

    text = (
        f"📋 **Заявка №{apt['id']}** (Картка {page_index + 1} із {len(appointments)})\n"
        f"───────────────────\n"
        f"Статус: **{status_icon}**\n\n"
        f"👤 **Клієнт:** {apt['client_name']}\n"
        f"📱 **Нікнейм:** {apt['client_nickname']}\n"
        f"📅 **Дата:** {dt_display}\n"
        f"⏰ **Час візиту:** {apt['time_slot']}:00\n"
        f"💵 **Вартість:** {apt['price']} грн"
    )

    kb = InlineKeyboardBuilder()

    # Кнопки перелистывания (передаем кастомный префикс в зависимости от режима)
    kb.row(
        types.InlineKeyboardButton(text="⬅️ Минулий", callback_data=StaffPageCb(idx=page_index - 1).pack()),
        types.InlineKeyboardButton(text="Наступний ➡️", callback_data=StaffPageCb(idx=page_index + 1).pack())
    )

    # Кнопка подтверждения (показывается только если запись НЕ подтверждена)
    if not apt.get('is_approved', False):
        kb.row(
            types.InlineKeyboardButton(text="✅ Підтвердити запис", callback_data=StaffApproveCb(id=apt['id']).pack()))

    # Кнопка связи
    if apt['client_nickname'] and apt['client_nickname'] != "Приховано":
        kb.row(types.InlineKeyboardButton(text="💬 Написати клієнту",
                                          url=f"https://t.me/{apt['client_nickname'].replace('@', '')}"))

    kb.row(types.InlineKeyboardButton(text="❌ Видалити/Відхилити", callback_data=StaffDeleteCb(id=apt['id']).pack()))
    kb.row(types.InlineKeyboardButton(text="⬅️ Головне меню адмінки", callback_data="staff_menu_home"))

    await state.update_data(staff_page_idx=page_index)
    try:
        await message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except Exception:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")


# ==========================================
# ХЕНДЛЕРЫ АДМИНИСТРАТОРА
# ==========================================

# 1. Вход по команде /staff
@router.message(F.text == "/staff")
async def cmd_staff_login(message: types.Message, state: FSMContext):
    if not message.from_user.username:
        await message.answer("🚨 Для входу в адмінку у вас повинен бути встановлений Telegram Username.")
        return

    print(f"\n[STAFF TRY] Спроба входу в адмінку від @{message.from_user.username}")
    staff_data = await fetch_api(f"staff/check/{message.from_user.username}/")

    if staff_data and staff_data.get('is_staff'):
        print(f"[STAFF SUCCESS] Працівник {staff_data['name']} успішно авторизований!")
        await show_staff_main_menu(message, staff_data['name'], staff_data['company_name'], state)
    else:
        await message.answer("🛑 Ви не є зареєстрованим працівником. Доступ закритий.")


# Возврат в главное меню админки по кнопке
@router.callback_query(F.data == "staff_menu_home")
async def callback_staff_home(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await show_staff_main_menu(callback.message, data.get('staff_name'), data.get('company_name'), state)


# Выбор режима: Только Новые
@router.callback_query(F.data == "staff_view_new")
async def callback_view_new(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_staff_appointments_page(callback.message, 0, state, filter_new_only=True)


# Выбор режима: Все подряд
@router.callback_query(F.data == "staff_view_all")
async def callback_view_all(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_staff_appointments_page(callback.message, 0, state, filter_new_only=False)


# Листание страниц внутри админки
@router.callback_query(StaffPageCb.filter())
async def process_staff_pagination(callback: types.CallbackQuery, callback_data: StaffPageCb, state: FSMContext):
    await callback.answer()
    current_state = await state.get_state()
    filter_new = (current_state == StaffState.browsing_new.state)
    await show_staff_appointments_page(callback.message, callback_data.idx, state, filter_new_only=filter_new)


# Хендлер НАЖАТИЯ КНОПКИ "ПОДТВЕРДИТЬ ЗАПИСЬ"
@router.callback_query(StaffApproveCb.filter())
async def process_staff_approve(callback: types.CallbackQuery, callback_data: StaffApproveCb, state: FSMContext):
    print(f"[STAFF ACTION] Адмін підтверджує запис ID: {callback_data.id}")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{API_BASE_URL}book/{callback_data.id}/approve/") as response:
                if response.status == 200:
                    await callback.answer("✅ Запис успішно підтверджено!", show_alert=True)
                else:
                    await callback.answer("🚨 Помилка при підтвердженні на сервері.", show_alert=True)
        except Exception as e:
            print(f"[STAFF ERROR] Не вдалося з'єднатися з API для підтвердження: {e}")
            await callback.answer("🚨 Помилка з'єднання.", show_alert=True)

    data = await state.get_data()
    current_state = await state.get_state()
    filter_new = (current_state == StaffState.browsing_new.state)

    # Обновляем эту же страницу, чтобы пропала кнопка "Подтвердить" и изменился статус
    await show_staff_appointments_page(callback.message, data.get('staff_page_idx', 0), state,
                                       filter_new_only=filter_new)


# Хендлер НАЖАТИЯ КНОПКИ "УДАЛИТЬ/ОТКЛОНИТЬ"
@router.callback_query(StaffDeleteCb.filter())
async def process_staff_delete(callback: types.CallbackQuery, callback_data: StaffDeleteCb, state: FSMContext):
    print(f"[STAFF ACTION] Адмін видаляє запис ID: {callback_data.id}")
    status_code = await delete_api(f"book/{callback_data.id}/delete/")
    data = await state.get_data()

    if status_code in [200, 204]:
        await callback.answer("🗑 Запис видалено з бази!", show_alert=True)
    else:
        await callback.answer("🚨 Помилка видалення.", show_alert=True)

    current_state = await state.get_state()
    filter_new = (current_state == StaffState.browsing_new.state)

    # Смещаемся на ту же страницу (если она была последней, метод защитит от выхода за границы)
    await show_staff_appointments_page(callback.message, data.get('staff_page_idx', 0), state,
                                       filter_new_only=filter_new)
# ==========================================
# 7. ЗАПУСК
# ==========================================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("\n" + "=" * 50)
    print("[SERVER START] Бот успішно запущений! Ліміти та Мої записи активні.")
    print("=" * 50 + "\n")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())