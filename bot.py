import base64
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

URL = "https://www.digikala.com/wealth/my-assets/"
TELEGRAM_API = "https://api.telegram.org"

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
# Export Playwright storage_state from a logged-in Digikala browser, base64-encode
# the JSON, and save it as the DIGIKALA_STORAGE_STATE_B64 Actions secret.
STORAGE_STATE_B64 = os.environ.get("DIGIKALA_STORAGE_STATE_B64", "").strip()


def normalize_digits(text):
    table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )
    return text.translate(table).replace("٬", ",").replace("،", ",").strip()


def load_storage_state():
    if not STORAGE_STATE_B64:
        raise RuntimeError(
            "Missing DIGIKALA_STORAGE_STATE_B64 GitHub Actions secret. "
            "This account requires SMS verification, which cannot be completed "
            "interactively in a scheduled GitHub Actions run. Add a fresh "
            "Playwright storage_state JSON encoded as base64."
        )
    try:
        state = json.loads(base64.b64decode(STORAGE_STATE_B64).decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "DIGIKALA_STORAGE_STATE_B64 is not valid base64-encoded Playwright "
            "storage_state JSON."
        ) from exc
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list):
        raise RuntimeError(
            "Storage state must be Playwright storage_state JSON with a cookies array."
        )
    return state


def fetch_prices():
    storage_state = load_storage_state()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            locale="fa-IR",
            timezone_id="Asia/Tehran",
            storage_state=storage_state
        )
        page = context.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)

            if "login" in page.url.lower():
                raise RuntimeError(
                    "Digikala redirected to login. The saved session may have "
                    "expired or needs SMS verification again. Refresh the "
                    "DIGIKALA_STORAGE_STATE_B64 secret after logging in again."
                )

            # Wait briefly for the client-rendered asset cards.
            page.wait_for_function(
                """() => {
                    const norm = s => s
                      .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
                      .trim();
                    const spans = [...document.querySelectorAll('span')];
                    return spans.some(s => norm(s.textContent) === 'طلای 18 عیار') &&
                           spans.some(s => norm(s.textContent) === 'نقره 999');
                }""",
                timeout=30000
            )

            prices = page.locator("body").evaluate(
                """body => {
                    const norm = s => s
                      .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
                      .replace(/[٬،]/g, ',')
                      .trim();
                    const spans = [...body.querySelectorAll('span')];
                    function getPrice(label) {
                        const el = spans.find(s => norm(s.textContent) === label);
                        if (!el || !el.parentElement) return null;
                        const values = [...el.parentElement.querySelectorAll('span')]
                          .map(s => norm(s.textContent))
                          .filter(s => /^[0-9][0-9,]*$/.test(s));
                        return values.length ? values[values.length - 1] : null;
                    }
                    return {
                        gold: getPrice('طلای 18 عیار'),
                        silver: getPrice('نقره 999')
                    };
                }"""
            )

            def parse_price(value, name):
                if not value:
                    raise ValueError(f"Price not found: {name}")
                price = int(value.replace(",", ""))
                if price <= 0:
                    raise ValueError(f"Invalid price: {name}")
                return price

            gold = parse_price(prices["gold"], "gold")
            silver = parse_price(prices["silver"], "silver")
            print(f"Extracted prices: gold={gold}, silver={silver}")
            return gold, silver
        except Exception:
            print("Page URL:", page.url)
            print("Page title:", page.title())
            print("Page text (first 2500 chars):", page.locator("body").inner_text()[:2500])
            raise
        finally:
            browser.close()


def send_telegram_message(message):
    response = requests.post(
        f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=30
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def main():
    gold, silver = fetch_prices()
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    timestamp = now.strftime("%Y-%m-%d | %H:%M:%S")
    message = (
        "🪙 <b>قیمت لحظه‌ای طلا و نقره دیجی‌کالا</b>\n\n"
        f"🟡 <b>طلای ۱۸ عیار</b> — هر ۱ میلی‌گرم\n"
        f"<code>{gold:,}</code> ریال\n\n"
        f"⚪ <b>نقره ۹۹۹</b> — هر ۱ میلی‌گرم\n"
        f"<code>{silver:,}</code> ریال\n\n"
        f"🕒 آخرین بررسی: {timestamp}\n"
        '<a href="https://www.digikala.com/wealth/my-assets/">'
        "منبع: دیجی‌کالا</a>"
    )
    send_telegram_message(message)
    print(f"Published successfully: gold={gold}, silver={silver}")


if __name__ == "__main__":
    main()
