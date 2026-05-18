import json
import sys
import requests

# 1. Load your existing config.json
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print("Error: config.json not found! Place this script in the same folder as your config file.")
    sys.exit(1)

# 2. Extract credentials
TELEGRAM_BOT_TOKEN = config.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = config.get("TELEGRAM_CHAT_ID")


def send_quick_msg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Error: Telegram credentials missing from config.json!")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ Message sent successfully!")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send message. Error: {e}")


if __name__ == "__main__":
    # Customize your test message here
    test_message = "My job is done bye bye (sorry for the two restarts)"
    print("Sending message...")
    send_quick_msg(test_message)