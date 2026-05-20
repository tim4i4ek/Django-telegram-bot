import logging
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Завантажуємо токен з .env файлу
load_dotenv()

API_BASE_URL = 'http://127.0.0.1:8000/api/'
# Базовий URL для медіа-файлів, щоб бот міг завантажувати картинки з Django сервера
BASE_URL = 'http://127.0.0.1:8000'
BOT_TOKEN = os.getenv('BOT_TOKEN')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class BookingState(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()


async def fetch_api(endpoint):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{API_BASE_URL}{endpoint}") as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            logging.error(f"API Error: {e}")
            return None


async def post_appointment(data):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{API_BASE_URL}book/", json=data) as response:
                return await response.json(), response.status
        except Exception as e:
            logging.error(f"API Post Error: {e}")
            return {"non_field_errors": ["Помилка з'єднання з сервером."]}, 500


async def show_main_menu(message_or_callback):
    text = (
        "👋 **Ласкаво просимо до нашої майстерні!**\n\n"
        "🔧 Ми спеціалізуємося на професійному обслуговуванні та ремонті.\n"
        "📅 Тут ви можете швидко та зручно переглянути вільні години та записатися на візит.\n\n"
        "Оберіть дію нижче:"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Записатися на послугу", callback_data="start_booking")

    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        # Якщо ми повернулися з меню з фотографією, edit_text може впасти, тому безпечніше надіслати нове повідомлення
        try:
            await message_or_callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
        except Exception:
            await message_or_callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")


@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await show_main_menu(message)


@dp.callback_query(F.data == "back_to_main")
async def back_to_main_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(callback)


@dp.callback_query(F.data == "start_booking")
async def show_services(callback: types.CallbackQuery, state: FSMContext):
    services = await fetch_api('services/')

    if not services:
        await callback.answer("Список послуг тимчасово порожній.", show_alert=True)
        return

    # Видаляємо старе текстове повідомлення меню, бо зараз будемо виводити картки послуг
    await callback.message.delete()

    for s in services:
        # Перевіряємо, чи доступна послуга для запису
        if not s.get('available', True):
            continue

        builder = InlineKeyboardBuilder()
        builder.button(
            text=f"✅ Вибрати: {s['proposition']}",
            callback_data=f"srv_{s['id']}_{s['price']}_{s['proposition']}"
        )
        builder.adjust(1)

        caption = f"🛠 **{s['proposition']}**\n\n💰 Ціна: {s['price']} грн"

        # Якщо у моделі є завантажене фото, відправляємо картку з фото
        if s.get('image'):
            photo_url = f"{BASE_URL}{s['image']}" if s['image'].startswith('/') else s['image']
            await callback.message.answer_photo(
                photo=photo_url,
                caption=caption,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
        else:
            # Якщо фото немає — просто відправляємо гарний текст
            await callback.message.answer(
                caption,
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )

    # Окрема кнопка повернення в самому кінці списку
    back_builder = InlineKeyboardBuilder()
    back_builder.button(text="⬅️ Головне меню", callback_data="back_to_main")
    await callback.message.answer("Або поверніться назад:", reply_markup=back_builder.as_markup())

    await state.set_state(BookingState.choosing_service)


@dp.callback_query(F.data.startswith("srv_"))
async def show_dates(callback: types.CallbackQuery, state: FSMContext):
    _, s_id, price, name = callback.data.split("_", 3)
    await state.update_data(service_id=s_id, price=price, service_name=name)

    schedule = await fetch_api('schedule/')
    if schedule is None:
        await callback.answer("Помилка завантаження графіка.", show_alert=True)
        return

    working_days_map = {d['day_index']: d['is_working'] for d in schedule}

    builder = InlineKeyboardBuilder()
    start_date = datetime.now()

    date_buttons = []
    for i in range(1, 31):
        current_date = start_date + timedelta(days=i)
        date_str = current_date.strftime("%Y-%m-%d")
        display_str = current_date.strftime("%d.%m")
        weekday = current_date.weekday()

        is_working = working_days_map.get(weekday, False)

        if is_working:
            btn_text = f"{display_str}"
            cb_data = f"date_{date_str}"
        else:
            btn_text = f"❌ {display_str}"
            cb_data = f"off_{display_str}"

        date_buttons.append(types.InlineKeyboardButton(text=btn_text, callback_data=cb_data))

    builder.row(*date_buttons)
    builder.adjust(4)

    nav_builder = InlineKeyboardBuilder()
    nav_builder.button(text="⬅️ Змінити послугу", callback_data="start_booking")
    nav_builder.button(text="🏠 Головне меню", callback_data="back_to_main")
    nav_builder.adjust(2)

    builder.attach(nav_builder)

    # Оскільки на попередньому кроці ми могли відправити фото, краще надіслати нове чисте повідомлення для календаря
    await callback.message.delete()
    await callback.message.answer(
        f"📅 **Крок 2: Оберіть дату**\nПослуга: *{name}*\n\n❌ — день позначений в адмінці як вихідний.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(BookingState.choosing_date)


@dp.callback_query(F.data.startswith("off_"))
async def weekend_clicked(callback: types.CallbackQuery):
    date_clicked = callback.data.split("_")[1]
    await callback.answer(f"{date_clicked} — це вихідний день! Оберіть іншу дату.", show_alert=True)


@dp.callback_query(F.data.startswith("date_"))
async def show_times(callback: types.CallbackQuery, state: FSMContext):
    date_val = callback.data.split("_")[1]
    await state.update_data(date=date_val)

    user_data = await state.get_data()
    service_name = user_data.get('service_name', '')

    schedule = await fetch_api('schedule/')
    dt_obj = datetime.strptime(date_val, "%Y-%m-%d")
    weekday = dt_obj.weekday()

    day_config = next((d for d in schedule if d['day_index'] == weekday), None)

    if not day_config or not day_config['hours']:
        await callback.answer("На цей день немає вільних годин.", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    time_buttons = []

    # Динамічно розбираємо години, які прийшли з нашого нового серіалізатора Django
    for slot in day_config['hours']:
        time_display = slot['hour']  # Рядок на кшталт "10:00", "11:00" або "14:30"
        time_buttons.append(types.InlineKeyboardButton(
            text=f"🕒 {time_display}",
            callback_data=f"time_{time_display}"
        ))

    builder.row(*time_buttons)
    builder.adjust(3)

    nav_builder = InlineKeyboardBuilder()
    srv_id = user_data['service_id']
    price = user_data['price']
    nav_builder.button(text="⬅️ Інша дата", callback_data=f"srv_{srv_id}_{price}_{service_name}")
    nav_builder.button(text="🏠 Головне меню", callback_data="back_to_main")
    nav_builder.adjust(2)

    builder.attach(nav_builder)

    display_date = dt_obj.strftime("%d.%m.%Y")
    await callback.message.edit_text(
        f"⏰ **Крок 3: Оберіть час**\nДата: *{display_date}*\nПослуга: *{service_name}*",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await state.set_state(BookingState.choosing_time)


@dp.callback_query(F.data.startswith("time_"))
async def confirm_booking(callback: types.CallbackQuery, state: FSMContext):
    time_val = callback.data.split("_")[1]  # Отримуємо "10:00"
    user_data = await state.get_data()

    # Оскільки у моделі Appointment поле time_slot — це IntegerField,
    # ми забираємо лише число години (наприклад, з "14:30" візьметься 14)
    hour_int = int(time_val.split(":")[0])

    # Забираємо нікнейм користувача. Якщо нікнейму немає — ставимо "Немає нікнейму"
    username = callback.from_user.username
    client_nickname = f"@{username}" if username else "Немає нікнейму"

    payload = {
        "client_name": callback.from_user.full_name,
        "client_nickname": client_nickname,  # Додано під нову модель!
        "date": user_data['date'],
        "time_slot": hour_int,
        "proposition": int(user_data['service_id']),
        "price": user_data['price']
    }

    result, status = await post_appointment(payload)

    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Повернутися в головне меню", callback_data="back_to_main")

    if status == 201:
        dt_display = datetime.strptime(user_data['date'], "%Y-%m-%d").strftime("%d.%m.%Y")
        await callback.message.edit_text(
            f"✅ **Заявку успішно створено!**\n\n"
            f"👤 **Клієнт:** {callback.from_user.full_name} ({client_nickname})\n"
            f"🛠 **Послуга:** {user_data['service_name']}\n"
            f"📅 **Дата:** {dt_display}\n"
            f"⏰ **Час:** {time_val}\n"
            f"💵 **До сплати:** {user_data['price']} грн\n\n"
            f"⏳ *Запис очікує на підтвердження майстром в адмінці!*",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )
    else:
        # Обробка помилок валідації від Django REST Framework
        if isinstance(result, dict):
            error_msg = result.get('time_slot',
                                   result.get('date', result.get('non_field_errors', ['Помилка запису.'])[0]))
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
        else:
            error_msg = "Цей час уже зайнятий або недоступний."

        await callback.message.edit_text(
            f"❌ **Помилка запису**\n\nПричина: {error_msg}",
            reply_markup=builder.as_markup(),
            parse_mode="Markdown"
        )

    await state.clear()


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())