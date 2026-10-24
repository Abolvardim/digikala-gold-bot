
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
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            # Wait for the two price labels and their numeric values.
            page.wait_for_function(
                """() => {
                    const norm = s => s
                      .replace(/[۰-۹]/g, d =>
                        String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g, d =>
                        String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)));
                    const nodes = [...document.querySelectorAll('div')];
                    return nodes.some(el => {
                      const t = norm(el.innerText || '');
                      return t.includes('طلای ۱۸ عیار') &&
                             t.includes('نقره ۹۹۹') &&
                             /طلای ۱۸ عیار\\s*[\\d,٬]+/.test(t) &&
                             /نقره ۹۹۹\\s*[\\d,٬]+/.test(t);
                    });
                }""",
                timeout=45000
            )

            # Find the smallest container holding both labels and prices.
            card_text = page.locator("body").evaluate(
                """body => {
                    const norm = s => s
                      .replace(/[۰-۹]/g, d =>
                        String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g, d =>
                        String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)));
                    const matches = [...body.querySelectorAll('div')]
                      .filter(el => {
                        const t = norm(el.innerText || '');
                        return t.includes('طلای ۱۸ عیار') &&
                               t.includes('نقره ۹۹۹') &&
                               /طلای ۱۸ عیار\\s*[\\d,٬]+/.test(t) &&
                               /نقره ۹۹۹\\s*[\\d,٬]+/.test(t);
                      });
                    matches.sort((a, b) =>
                      a.innerText.length - b.innerText.length);
                    return matches.length ? matches[0].innerText : '';
                }"""
            )

            card_text = normalize_digits(card_text)

            def extract(label):
                pattern = re.escape(label) + r"\s*[:：]?\s*([\d,]+)"
                match = re.search(pattern, card_text)
                if not match:
                    raise ValueError(f"Price not found for {label}")
                value = int(match.group(1).replace(",", ""))
                if value <= 0:
                    raise ValueError(f"Invalid price for {label}")
                return value

            gold = extract("طلای 18 عیار")
            silver = extract("نقره 999")

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
