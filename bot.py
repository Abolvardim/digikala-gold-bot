
import os
import re
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

URL = "https://www.digikala.com/wealth/my-assets/"
TELEGRAM_API = "https://api.telegram.org"

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]


def normalize_digits(text):
    """Convert Persian and Arabic-Indic digits to English digits."""
    table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )
    return text.translate(table).replace("٬", ",").replace("،", ",")



def fetch_prices():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            locale="fa-IR",
            timezone_id="Asia/Tehran"
        )

        try:
            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_function(
                """() => {
                    const norm = s => s
                      .replace(/[۰-۹]/g,
                        d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g,
                        d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
                      .trim();

                    const spans = [...document.querySelectorAll('span')];

                    function getPrice(label) {
                        const el = spans.find(
                            s => norm(s.textContent) === label
                        );
                        if (!el || !el.parentElement) return null;

                        const values = [
                            ...el.parentElement.querySelectorAll('span')
                        ]
                        .map(s => norm(s.textContent))
                        .filter(s => /^\\d[\\d,]*$/.test(s));

                        return values.length ? values[values.length - 1] : null;
                    }

                    return Boolean(
                        getPrice('طلای 18 عیار') &&
                        getPrice('نقره 999')
                    );
                }""",
                timeout=45000
            )

            prices = page.locator("body").evaluate(
                """body => {
                    const norm = s => s
                      .replace(/[۰-۹]/g,
                        d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g,
                        d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
                      .trim();

                    const spans = [...body.querySelectorAll('span')];

                    function getPrice(label) {
                        const el = spans.find(
                            s => norm(s.textContent) === label
                        );
                        if (!el || !el.parentElement) return null;

                        const values = [
                            ...el.parentElement.querySelectorAll('span')
                        ]
                        .map(s => norm(s.textContent))
                        .filter(s => /^\\d[\\d,]*$/.test(s));

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
        '🔗 <a href="https://www.digikala.com/wealth/my-assets/">'
        "منبع: دیجی‌کالا</a>"
    )

    send_telegram_message(message)
    print(f"Published successfully: gold={gold}, silver={silver}")


if __name__ == "__main__":
    main()
