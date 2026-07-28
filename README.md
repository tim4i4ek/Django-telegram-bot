# 🤖 Telegram Appointment Bot for Small Business

An automated, 24/7 Telegram bot built with **Aiogram** and **Django REST Framework** designed to streamline appointment scheduling for small businesses. It connects users directly to a backend database, minimizing manual management and saving time.

---

## 🚀 Features

* **Interactive Booking Flow:** Step-by-step user interface powered by Aiogram FSM (Finite State Machines) to capture client appointments seamlessly.
* **Backend Integration:** Communicates with a robust Django REST API to securely store and retrieve client data.
* **Database Persistence:** Stores appointments and user info reliably in PostgreSQL/SQLite.
* **Automated Management:** Handles real-time appointment logging and reduces the need for manual scheduling.

---

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **Bot Framework:** Aiogram (Async Telegram Bot API)
* **Backend API:** Django & Django REST Framework (DRF)
* **Database:** PostgreSQL / SQLite
* **Testing Tool:** Postman

---

## ⚙️ Installation & Setup

Follow these steps to run the bot and backend locally:

1. **Clone the repository:**

Create and activate a virtual environment:

python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
Install dependencies:

pip install -r requirements.txt
Configure environment variables:
Create a .env file and add your Telegram Bot Token and database settings:
BOT_TOKEN=your_telegram_bot_token_here
DATABASE_URL=your_database_connection_string

Apply database migrations:
python manage.py makemigrations
python manage.py migrate

Run the backend server and the bot:
# Run Django API
python manage.py runserver

# In a separate terminal, run the bot
python bot.py
🧪 Testing with Postman
You can test the underlying API endpoints that the bot communicates with:
GET http://127.0.0.1:8000/appointments/ — View all scheduled appointments
POST http://127.0.0.1:8000/appointments/ — Create a new appointment record via API
