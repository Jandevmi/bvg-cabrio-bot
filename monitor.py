import json
import time
import hashlib
import requests
from bs4 import BeautifulSoup
import sys

# Load configuration from JSON file
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print("Error: config.json not found! Make sure it is copied into the Docker image.")
    sys.exit(1)

URL = "https://www.bvg.de/de/service-und-kontakt/erlebe-berlin/u-bahn-cabrio"
TELEGRAM_BOT_TOKEN = config.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = config.get("TELEGRAM_CHAT_ID")
CHECK_INTERVAL_HOURS = config.get("CHECK_INTERVAL_HOURS", 2)
ALIVE_MESSAGE_AFTER_X_CHECKS = config.get("ALIVE_MESSAGE_AFTER_X_CHECKS", 12)

# Convert hours to seconds for time.sleep()
check_interval_seconds = CHECK_INTERVAL_HOURS * 3600


def send_telegram_msg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    requests.post(url, json=payload)


def main():
    previous_hash = None
    checks_since_last_update = 0
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    startup_msg = (f"🚇 BVG Monitor started! Checking every {CHECK_INTERVAL_HOURS} hour(s). "
                   f"Will send a status update every {ALIVE_MESSAGE_AFTER_X_CHECKS} checks.")
    print(startup_msg)
    send_telegram_msg(startup_msg)

    while True:
        try:
            response = requests.get(URL, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            main_content = soup.find('main')
            text_to_hash = main_content.get_text(strip=True) if main_content else response.text

            current_hash = hashlib.md5(text_to_hash.encode('utf-8')).hexdigest()

            # Check for changes
            if previous_hash is not None and current_hash != previous_hash:
                print("Change detected!")
                send_telegram_msg(f"🚨 BVG U-Bahn Cabrio website changed! Go check: {URL}")
            else:
                print("No change detected.")

            previous_hash = current_hash
            checks_since_last_update += 1

            # Send heartbeat message if threshold is reached
            if checks_since_last_update >= ALIVE_MESSAGE_AFTER_X_CHECKS:
                send_telegram_msg(
                    f"ℹ️ Status Update: BVG Monitor is still running.. "
                    f"No changes detected in the last {ALIVE_MESSAGE_AFTER_X_CHECKS} checks.")
                checks_since_last_update = 0  # Reset the counter

        except Exception as e:
            error_msg = f"⚠️ Error checking BVG website: {e}"
            print(error_msg)
            # Optional: send error to Telegram so you know if the site is down
            # send_telegram_msg(error_msg)

        time.sleep(check_interval_seconds)


if __name__ == "__main__":
    main()