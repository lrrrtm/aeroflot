import time
import json
import requests
import traceback
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

import os

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID_HERE')

# Dates to check
DATES_TO_CHECK = ['2026-01-10', '2026-01-11']

# Route details
ORIGIN = "KGD"
DESTINATION = "LED"
PASSENGER_TYPE = "kgd_resident"
PROGRAM_ID = 55

# Check interval in seconds (1 hour)
CHECK_INTERVAL = 3600 
# ---------------------

def send_telegram_message(message):
    """Sends a message to the specified Telegram chat."""
    if TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("Telegram token not set. Skipping message.")
        print(f"Message would be: {message}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, data=data)
        if response.status_code != 200:
            print(f"Failed to send Telegram message: {response.text}")
    except Exception as e:
        print(f"Error sending telegram message: {e}")

def check_date(driver, date):
    """Checks for tickets on a specific date using the browser's fetch API."""
    print(f"Checking date: {date}...")
    
    payload = {
        "program_id": PROGRAM_ID,
        "routes": [{"origin": ORIGIN, "destination": DESTINATION, "departure_date": date}],
        "passengers": [{"passenger_type": PASSENGER_TYPE, "quantity": 1}],
        "lang": "ru"
    }
    
    # We use execute_script to run a fetch request inside the browser.
    # This ensures we use the correct cookies, headers, and TLS session established by the browser.
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
        # execute_async_script allows us to wait for the promise to resolve
        response_data = driver.execute_async_script(js_script)
        
        if not response_data:
            print(f"Empty response for {date}")
            return False
            
        if 'error' in response_data and response_data['error']:
            print(f"JS Fetch Error for {date}: {response_data['error']}")
            return False

        # Check for route_itineraries
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
    chrome_options.add_argument("--headless=new") # New headless mode is better
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Spoof user agent
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Exclude switches that might reveal automation
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    try:
        # Try using webdriver_manager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"Error initializing driver with webdriver_manager: {e}")
        print("Attempting to use default 'chromedriver' from PATH...")
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e2:
            print("Could not initialize driver. Make sure Chrome and Chromedriver are installed.")
            raise e2

    # Stealth: remove webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def main():
    print("--- Aeroflot Ticket Checker Started ---")
    print(f"Checking dates: {DATES_TO_CHECK}")
    print(f"Interval: {CHECK_INTERVAL} seconds")
    
    while True:
        driver = None
        try:
            driver = init_driver()
            
            # 1. Navigate to the main page to establish session and pass bot checks
            print("Navigating to Aeroflot website...")
            driver.get("https://www.aeroflot.ru/sb/subsidized/app/ru-ru")
            
            # Wait for page to load and any initial scripts/checks to run
            time.sleep(15)
            
            found_tickets = []
            
            for date in DATES_TO_CHECK:
                if check_date(driver, date):
                    found_tickets.append(date)
                # Random sleep between requests to be safe
                time.sleep(5)
            
            if found_tickets:
                msg = f"✈️ *Билеты найдены!* (KGD -> LED)\nДаты: {', '.join(found_tickets)}\n[Купить](https://www.aeroflot.ru/sb/subsidized/app/ru-ru)"
                send_telegram_message(msg)
            
        except Exception as e:
            print(f"An error occurred during the check cycle: {e}")
            traceback.print_exc()
        finally:
            if driver:
                print("Closing driver...")
                driver.quit()
        
        print(f"Sleeping for {CHECK_INTERVAL} seconds...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScript stopped by user.")
        sys.exit(0)
