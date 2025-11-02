
import time
import requests
from playwright.sync_api import sync_playwright

# --- tiny health server for Render (HTTP 200) ---
import os, threading
from flask import Flask

app = Flask(__name__)

@app.route("/")
def ok():
    return "RainBot is running!", 200

def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port),
        daemon=True
    ).start()
    print(f"Health server listening on port {port}")

# --- end health server ---

# =========================
# RainBot Configuration
# =========================
VERSION = "RainBot-English-v2-mentions"

WEBHOOK_URL = "https://discordapp.com/api/webhooks/1434470166481338519/7c_bwalFDEkz3Q2f2O9PZgkC79DP2_qnp2eBDrATtohSd560kQnc-u2p1F3564wUpDhJ"   # <-- PUT YOUR WEBHOOK HERE
CHECK_URL   = "https://bandit.camp"
POLL_SECONDS = 20

# Mentions (choose ONE: everyone OR a specific role)
PING_EVERYONE = False
ROLE_ID = "1434479776525058109"

# What to detect on the page to know rain is live
RAIN_TEXTS = ["join rain event", "rakeback rain"]
RAIN_SELECTORS = [
    "text=JOIN RAIN EVENT",
    "text=Rakeback Rain",
    "button:has-text('JOIN RAIN EVENT')",
]

# =========================
# Discord notifier (embed + optional mention)
# =========================
def send_discord(msg: str):
    # Build mention payload (optional)
    mention_content = ""
    allowed_mentions = {"parse": []}

    if PING_EVERYONE:
        mention_content = "@everyone"
        allowed_mentions["parse"].append("everyone")
    elif ROLE_ID:
        mention_content = f"<@&{ROLE_ID}>"
        allowed_mentions["roles"] = [ROLE_ID]

    embed = {
        "title": "🌧️ Rain event is live!",
        "description": f"{msg}\n**Check it out:** {CHECK_URL}",
        "url": CHECK_URL,
        "color": 0x3498db,
        "footer": {"text": "RainBot – Live Alert"},
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
    }

    payload = {
        "username": "RainBot",
        "content": mention_content,           # the actual ping text (can be empty)
        "allowed_mentions": allowed_mentions, # allow Discord to ping
        "embeds": [embed],
    }

    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=12)
        r.raise_for_status()
        print("✅ Discord embed sent.")
    except Exception as e:
        print("Webhook error:", e)

# =========================
# Detection logic
# =========================
def page_has_rain(page) -> bool:
    # Let the page render JS content
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)
    page.wait_for_load_state("networkidle")
    time.sleep(1)

    # 1) Try selectors
    for sel in RAIN_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                return True
        except Exception:
            pass

    # 2) Fallback: plain text search
    content = page.content().lower()
    return any(t in content for t in RAIN_TEXTS)

# =========================
# Main loop
# =========================
def run():
    last_seen = False  # prevents multiple alerts for the same rain
    print(f"RainBot (Playwright) started → {CHECK_URL} | {VERSION}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36")
        )
        page = context.new_page()

        while True:
            try:
                page.goto(CHECK_URL, wait_until="networkidle", timeout=60000)

                # Try to dismiss cookie banners if present
                for btn_text in ["Accept All", "I Agree", "Accept", "Allow Cookies", "OK"]:
                    try:
                        page.locator(f"button:has-text('{btn_text}')").first.click(timeout=1500)
                    except Exception:
                        pass

                live = page_has_rain(page)

            except Exception as e:
                print("Navigation error:", e)
                live = False

            if live and not last_seen:
                print("RAIN DETECTED → sending Discord notification")
                send_discord("A new rain event just started! 🌦️")
                last_seen = True
            elif not live and last_seen:
                print("Rain ended → reset state")
                last_seen = False
            else:
                print("No rain detected.")

            time.sleep(POLL_SECONDS)

# =========================
# Entry point
# =========================
if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("Stopped by user")
# --- main loop ---
if __name__ == "__main__":
    start_health_server()  # start de mini server zodat Render denkt dat de bot "leeft"
    try:
        run()
    except KeyboardInterrupt:
        print("Stopped by user")

