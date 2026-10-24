import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

URL = "https://www.digikala.com/wealth/landing/"
TELEGRAM_API = "https://api.telegram.org"

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]


def fetch_gold_price():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="fa-IR", timezone_id="Asia/Tehran")
        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            page.wait_for_function(
                """() => {
                    const norm = s => s
                      .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
                      .replace(/[٬،]/g, ',')
                      .replace(/\\s+/g, ' ')
                      .trim();
                    const isNumber = s => /^[0-9][0-9,]*$/.test(norm(s));
                    const labels = [...document.querySelectorAll('*')].filter(el =>
                      el.children.length === 0 &&
                      norm(el.textContent).includes('قیمت لحظه‌ای') &&
                      norm(el.textContent).includes('میلی‌گرم') &&
                      norm(el.textContent).includes('طلا'));
                    return labels.some(label => {
                      let parent = label;
                      for (let depth = 0; parent && depth < 7; depth++, parent = parent.parentElement) {
                        if ([...parent.querySelectorAll('span,div,p,strong,b')]
                          .some(el => el.children.length === 0 && isNumber(el.textContent))) return true;
                      }
                      return false;
                    });
                }""",
                timeout=45000,
            )

            gold = page.locator("body").evaluate(
                """body => {
                    const norm = s => s
                      .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
                      .replace(/[٬،]/g, ',')
                      .replace(/\\s+/g, ' ')
                      .trim();
                    const numeric = s => /^[0-9][0-9,]*$/.test(norm(s));
                    const labels = [...body.querySelectorAll('*')].filter(el =>
                      el.children.length === 0 &&
                      norm(el.textContent).includes('قیمت لحظه‌ای') &&
                      norm(el.textContent).includes('میلی‌گرم') &&
                      norm(el.textContent).includes('طلا'));
                    for (const label of labels) {
                      let parent = label;
                      for (let depth = 0; parent && depth < 7; depth++, parent = parent.parentElement) {
                        const values = [...parent.querySelectorAll('span,div,p,strong,b')]
                          .filter(el => el.children.length === 0)
                          .map(el => norm(el.textContent))
                          .filter(numeric);
                        if (values.length) return values[values.length - 1];
                      }
                    }
                    return null;
                }"""
            )
            if not gold:
                raise ValueError(f"Could not extract gold price from {URL}")
            price = int(gold.replace(",", ""))
            if price <= 0:
                raise ValueError(f"Invalid gold price: {gold}")
            print(f"Extracted public gold price (per milligram): {price}")
            return price
        except Exception:
            print("Page URL:", page.url)
            print("Page title:", page.title())
            print("Page text (first 5000 chars):", page.locator("body").inner_text()[:5000])
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
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    result = data.get("result", {})
    chat = result.get("chat", {})
    print(
        "Telegram accepted message: "
        f"destination_type={chat.get('type')}, "
        f"destination_id={chat.get('id')}, "
        f"message_id={result.get('message_id')}"
    )


def main():
    gold = fetch_gold_price()
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    timestamp = now.strftime("%Y-%m-%d | %H:%M:%S")
    gold_million_tomans = gold / 10_000
    gold_display = f"{gold_million_tomans:.2f}"
    message = (
        "🪙 <b>قیمت لحظه‌ای طلای دیجی‌کالا</b>\n\n"
        f"🟡 <b>طلا</b> — هر ۱ میلی‌گرم\n"
        f"<code>{gold:,}</code> ریال\n"
        f"({gold_display} M)\n\n"
        f"🕒 آخرین بررسی: {timestamp}\n"
        '<a href="https://www.digikala.com/wealth/landing/">'
        "منبع: دیجی‌کالا</a>"
    )
    send_telegram_message(message)
    print(f"Published successfully: gold={gold}")


if __name__ == "__main__":
    main()
