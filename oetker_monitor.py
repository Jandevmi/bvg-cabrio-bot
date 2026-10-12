import json
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# Load configuration from JSON file (mounted from a k8s Secret)
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
try:
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"Error: {CONFIG_PATH} not found! Make sure the secret is mounted.")
    sys.exit(1)

PAGES = {
    "Geführter Rundgang": "https://oetker-welt.oetker.de/dr-oetker-welt-gefuehrter-rundgang",
    "Freier Rundgang": "https://oetker-welt.oetker.de/dr-oetker-welt-freier-rundgang",
    "Weihnachtsmarkt": "https://oetker-welt.oetker.de/dr-oetker-welt-weihnachtsmarkt",
}
TELEGRAM_BOT_TOKEN = config.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = config.get("TELEGRAM_CHAT_ID")
CHECK_INTERVAL_HOURS = config.get("CHECK_INTERVAL_HOURS", 3)
ALIVE_MESSAGE_AFTER_X_CHECKS = config.get("ALIVE_MESSAGE_AFTER_X_CHECKS", 8)
# Only events on these days (Europe/Berlin) are watched; empty list = watch everything
WATCH_DATES = set(config.get("WATCH_DATES", [
    "2026-10-18", "2026-10-19",
    "2026-11-21", "2026-11-22",
    "2026-11-28", "2026-11-29",
]))

check_interval_seconds = CHECK_INTERVAL_HOURS * 3600
TZ = ZoneInfo("Europe/Berlin")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
# Each event in the Next.js payload looks like:
# {"id":..,"slug":..,"type":..,"startTimestamp":"2026-11-26T15:00:00.000+0000",...,"availableTickets":0}
EVENT_RE = re.compile(r'"startTimestamp":"([^"]+)"(?:(?!"startTimestamp").)*?"availableTickets":(-?\d+)', re.S)
TELEGRAM_MAX_LEN = 4000


def send_telegram_msg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing!")
        return
    if len(msg) > TELEGRAM_MAX_LEN:
        msg = msg[:TELEGRAM_MAX_LEN] + "\n…"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload, timeout=10).raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to send Telegram message: {e}")


def to_local(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(TZ)


def fmt_date(ts):
    return to_local(ts).strftime("%a %d.%m.%Y %H:%M")


def filter_dates(events):
    if not WATCH_DATES:
        return events
    return {ts: n for ts, n in events.items() if to_local(ts).date().isoformat() in WATCH_DATES}


def fetch_events(url):
    """Return {startTimestamp: availableTickets} for all events listed on the page."""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    # Decode the streamed React Server Component payload (self.__next_f.push([1,"..."]))
    payload = ""
    for script in soup.find_all("script"):
        text = script.string or ""
        for chunk in re.findall(r'self\.__next_f\.push\(\[1,(".*")\]\)', text, re.S):
            payload += json.loads(chunk)

    events = {ts: int(n) for ts, n in EVENT_RE.findall(payload)}
    if events:
        return events

    # Fallback: schema.org JSON-LD (less precise, overbooked events show as "Scheduled")
    for script in soup.find_all("script", type="application/ld+json"):
        data = json.loads(script.string)
        for e in data.get("subEvent", []):
            events[e["startDate"]] = 0 if e["eventStatus"].endswith("EventSoldOut") else 1
    if not events:
        raise ValueError("No events found on page — page structure may have changed")
    return events


def summary(name, events):
    now = datetime.now(TZ)
    upcoming = [ts for ts in events if to_local(ts) > now]
    available = [ts for ts in upcoming if events[ts] > 0]
    return f"{name}: {len(available)}/{len(upcoming)} Termine buchbar"


def main():
    previous = {name: None for name in PAGES}
    checks_since_last_update = 0
    first_run = True

    watched = ", ".join(datetime.fromisoformat(d).strftime("%d.%m.") for d in sorted(WATCH_DATES)) or "alle"
    startup_msg = (f"🍮 Dr. Oetker Welt Monitor started! Checking every {CHECK_INTERVAL_HOURS} hour(s). "
                   f"Will send a status update every {ALIVE_MESSAGE_AFTER_X_CHECKS} checks.\n"
                   f"Beobachtete Tage: {watched}")
    print(startup_msg)
    send_telegram_msg(startup_msg)

    while True:
        lines = []
        for name, url in PAGES.items():
            try:
                events = filter_dates(fetch_events(url))
                old = previous[name]
                if old is None:
                    lines.append(summary(name, events))
                else:
                    # Event became bookable: was sold out/overbooked (or did not exist) and now has tickets
                    newly_available = sorted(ts for ts, n in events.items() if n > 0 and old.get(ts, 0) <= 0)
                    if newly_available:
                        print(f"{name}: {len(newly_available)} newly available event(s)")
                        msg_lines = [f"🚨 {name}: neue Termine verfügbar!"]
                        msg_lines += [f"• {fmt_date(ts)} ({events[ts]} Plätze)" for ts in newly_available]
                        msg_lines.append(url)
                        send_telegram_msg("\n".join(msg_lines))
                    else:
                        print(f"{name}: No change detected.")
                previous[name] = events
            except Exception as e:
                print(f"⚠️ Error checking {name}: {e}")
                lines.append(f"⚠️ {name}: Fehler beim Abrufen ({e})")

        # First run: report the current state (later errors are only logged)
        if first_run:
            send_telegram_msg("Aktueller Stand:\n" + "\n".join(lines))
            first_run = False

        checks_since_last_update += 1

        if checks_since_last_update >= ALIVE_MESSAGE_AFTER_X_CHECKS:
            status = [summary(name, ev) for name, ev in previous.items() if ev is not None]
            send_telegram_msg("ℹ️ Status Update: Dr. Oetker Welt Monitor is still running.\n" + "\n".join(status))
            checks_since_last_update = 0

        time.sleep(check_interval_seconds)


if __name__ == "__main__":
    main()
