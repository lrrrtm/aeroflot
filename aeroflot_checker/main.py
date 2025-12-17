import os
import time
import json
import requests
import traceback
import sys
import sqlite3
import threading
import calendar
import telebot
from telebot import types
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
# TELEGRAM_CHAT_ID is no longer needed as we send to subscribed users

# Route details
ORIGIN = "KGD"
DESTINATION = "LED"
PASSENGER_TYPE = "kgd_resident"
PROGRAM_ID = 55

# Check interval in seconds (1 hour)
CHECK_INTERVAL = 3600 

# Database file
DB_FILE = "aeroflot_bot.db"

# Initialize Bot
if not TELEGRAM_BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN not found in environment variables.")
    sys.exit(1)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# --- DATABASE FUNCTIONS ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date)
        )
    ''')
    conn.commit()
    conn.close()

def add_watch(user_id, date):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO watches (user_id, date) VALUES (?, ?)', (user_id, date))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False # Already exists

def remove_watch(user_id, date):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM watches WHERE user_id = ? AND date = ?', (user_id, date))
    conn.commit()
    conn.close()

def get_user_watches(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT date FROM watches WHERE user_id = ? ORDER BY date', (user_id,))
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def get_all_unique_dates():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT date FROM watches')
    dates = [row[0] for row in cursor.fetchall()]
    conn.close()
    return dates

def get_users_for_date(date):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM watches WHERE date = ?', (date,))
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# --- AEROFLOT CHECKER LOGIC ---

def check_date(driver, date):
    """Checks for tickets on a specific date using the browser's fetch API."""
    print(f"Checking date: {date}...")
    
    payload = {
        "program_id": PROGRAM_ID,
        "routes": [{"origin": ORIGIN, "destination": DESTINATION, "departure_date": date}],
        "passengers": [{"passenger_type": PASSENGER_TYPE, "quantity": 1}],
        "lang": "ru"
    }
    
    js_script = f"""
    var callback = arguments[arguments.length - 1];
    
    fetch("https://www.aeroflot.ru/se/api/app/flight/subsidized/search/v3", {{
        "headers": {{
            "accept": "application/json",
            "content-type": "application/json"
        }},
        "body": JSON.stringify({json.dumps(payload)}),
        "method": "POST"
    }})
    .then(response => response.json())
    .then(data => callback(data))
    .catch(err => callback({{'error': err.toString()}}));
    """
    
    try:
        response_data = driver.execute_async_script(js_script)
        
        if not response_data:
            print(f"Empty response for {date}")
            return False
            
        if 'error' in response_data and response_data['error']:
            print(f"JS Fetch Error for {date}: {response_data['error']}")
            return False

        data_obj = response_data.get('data', {})
        route_itineraries = data_obj.get('route_itineraries', [])
        
        if route_itineraries:
            print(f"[SUCCESS] Tickets found for {date}!")
            return True
        else:
            print(f"No tickets for {date}")
            return False
            
    except Exception as e:
        print(f"Error executing script for {date}: {e}")
        return False

def init_driver():
    """Initializes the Chrome driver with anti-detection options."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Error initializing driver with webdriver_manager: {e}")
        print("Attempting to use default 'chromedriver' from PATH...")
        driver = webdriver.Chrome(options=chrome_options)

    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def checker_loop():
    """Background thread that checks for tickets periodically."""
    print("--- Checker Thread Started ---")
    while True:
        try:
            dates_to_check = get_all_unique_dates()
            if not dates_to_check:
                print("No dates to check. Sleeping...")
                time.sleep(CHECK_INTERVAL)
                continue

            print(f"Dates to check: {dates_to_check}")
            
            driver = init_driver()
            try:
                print("Navigating to Aeroflot website...")
                driver.get("https://www.aeroflot.ru/sb/subsidized/app/ru-ru")
                time.sleep(15)
                
                for date in dates_to_check:
                    if check_date(driver, date):
                        # Tickets found! Notify users.
                        users = get_users_for_date(date)
                        for user_id in users:
                            msg = f"✈️ *Билеты найдены!* (KGD -> LED)\n📅 Дата: {date}\n[Купить](https://www.aeroflot.ru/sb/subsidized/app/ru-ru)"
                            try:
                                bot.send_message(user_id, msg, parse_mode="Markdown")
                            except Exception as e:
                                print(f"Failed to send message to {user_id}: {e}")
                    
                    time.sleep(5) # Pause between checks
            finally:
                driver.quit()
                
        except Exception as e:
            print(f"Error in checker loop: {e}")
            traceback.print_exc()
        
        print(f"Checker sleeping for {CHECK_INTERVAL} seconds...")
        time.sleep(CHECK_INTERVAL)

# --- BOT HANDLERS ---

RU_MONTHS = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

def create_calendar(year, month):
    markup = types.InlineKeyboardMarkup()
    markup.row_width = 7
    
    # Month and Year Header
    markup.add(types.InlineKeyboardButton(f"{RU_MONTHS[month]} {year}", callback_data="IGNORE"))
    
    # Week days
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    row_days = [types.InlineKeyboardButton(day, callback_data="IGNORE") for day in days]
    markup.add(*row_days)
    
    # Days
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day in week:
            if day == 0:
                row.append(types.InlineKeyboardButton(" ", callback_data="IGNORE"))
            else:
                # Format: CALENDAR|SELECT|YYYY|MM|DD
                callback_data = f"CALENDAR|SELECT|{year}|{month}|{day}"
                row.append(types.InlineKeyboardButton(str(day), callback_data=callback_data))
        markup.add(*row)
    
    # Navigation
    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1
    
    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1
        
    markup.row(
        types.InlineKeyboardButton("<", callback_data=f"CALENDAR|PREV|{prev_year}|{prev_month}|0"),
        types.InlineKeyboardButton(" ", callback_data="IGNORE"),
        types.InlineKeyboardButton(">", callback_data=f"CALENDAR|NEXT|{next_year}|{next_month}|0")
    )
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, 
                 "Привет! Я бот для поиска субсидированных билетов Аэрофлота (Калининград -> СПб).\n\n"
                 "Команды:\n"
                 "/add - Добавить дату для отслеживания (через календарь)\n"
                 "/list - Показать мои отслеживаемые даты\n"
                 "/ping - Проверить статус бота")

@bot.message_handler(commands=['ping'])
def send_ping(message):
    bot.reply_to(message, "Pong! 🏓 Я работаю.")

@bot.message_handler(commands=['add'])
def add_date_command(message):
    now = datetime.now()
    bot.send_message(message.chat.id, "Выберите дату:", reply_markup=create_calendar(now.year, now.month))

@bot.callback_query_handler(func=lambda call: call.data.startswith('CALENDAR|'))
def callback_calendar(call):
    try:
        _, action, year, month, day = call.data.split('|')
        year, month, day = int(year), int(month), int(day)
        
        if action == 'IGNORE':
            bot.answer_callback_query(call.id)
            return
            
        if action == 'SELECT':
            date_str = f"{year}-{month:02d}-{day:02d}"
            if add_watch(call.message.chat.id, date_str):
                bot.edit_message_text(f"✅ Дата {date_str} добавлена в список отслеживания.", call.message.chat.id, call.message.message_id)
            else:
                bot.edit_message_text(f"ℹ️ Дата {date_str} уже отслеживается.", call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id, f"Выбрана дата: {date_str}")
                
        elif action == 'PREV' or action == 'NEXT':
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_calendar(year, month))
            bot.answer_callback_query(call.id)
            
    except Exception as e:
        print(f"Calendar error: {e}")
        bot.answer_callback_query(call.id, "Ошибка календаря")

@bot.message_handler(commands=['list'])
def list_dates_command(message):
    dates = get_user_watches(message.chat.id)
    if not dates:
        bot.reply_to(message, "У вас нет отслеживаемых дат. Используйте /add чтобы добавить.")
        return

    keyboard = types.InlineKeyboardMarkup()
    for date in dates:
        # Callback data: "del_2026-01-10"
        btn = types.InlineKeyboardButton(text=f"🗑 {date}", callback_data=f"del_{date}")
        keyboard.add(btn)
    
    bot.send_message(message.chat.id, "Ваши отслеживаемые даты (нажмите, чтобы удалить):", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def callback_delete_date(call):
    date_to_remove = call.data.split('_')[1]
    remove_watch(call.message.chat.id, date_to_remove)
    
    # Update the list
    dates = get_user_watches(call.message.chat.id)
    if not dates:
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Список пуст.")
    else:
        keyboard = types.InlineKeyboardMarkup()
        for date in dates:
            btn = types.InlineKeyboardButton(text=f"🗑 {date}", callback_data=f"del_{date}")
            keyboard.add(btn)
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="Ваши отслеживаемые даты (нажмите, чтобы удалить):", reply_markup=keyboard)
    
    bot.answer_callback_query(call.id, f"Дата {date_to_remove} удалена.")

def main():
    init_db()
    
    # Start checker in background thread
    checker_thread = threading.Thread(target=checker_loop, daemon=True)
    checker_thread.start()
    
    # Start bot polling
    print("--- Bot Polling Started ---")
    bot.infinity_polling()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
        sys.exit(0)
