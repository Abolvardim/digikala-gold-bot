import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

URL = "https://www.digikala.com/wealth/landing/"
TELEGRAM_API = "https://api.telegram.org"

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]


def fetch_prices():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="fa-IR", timezone_id="Asia/Tehran")

        def read_visible_price(metal):
            return page.locator("body").evaluate(
                """(body, metal) => {
                    const norm = s => s
                      .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
                      .replace(/[٬،]/g, ',')
                      .replace(/\\s+/g, ' ')
                      .trim();
                    const spans = [...body.querySelectorAll('span')];
                    const label = spans.find(s => {
                        const t = norm(s.textContent);
                        return t.includes('قیمت لحظه‌ای') &&
                          t.includes('میلی‌گرم') && t.includes(metal);
                    });
                    if (!label) return null;

                    const row = label.closest(
                      'div.flex.justify-between.items-center.mb-5'
                    );
                    if (!row) return null;
                    const values = [...row.querySelectorAll('span')]
                      .map(s => norm(s.textContent))
                      .filter(s => /^[0-9][0-9,]*$/.test(s));
                    return values.length ? values[values.length - 1] : null;
                }""",
                metal,
            )

        def parse_price(value, name):
            if not value:
                raise ValueError(f"Could not find the visible {name} price on {URL}")
            price = int(value.replace(",", ""))
            if price <= 0:
                raise ValueError(f"Invalid {name} price: {value}")
            return price

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            # The landing page initially selects gold. Read it first.
            page.wait_for_function(
                """() => [...document.querySelectorAll('span')].some(s =>
                    s.textContent.includes('قیمت لحظه‌ای') &&
                    s.textContent.includes('میلی‌گرم') &&
                    s.textContent.includes('طلا'))""",
                timeout=45000,
            )
            gold = parse_price(read_visible_price("طلا"), "gold")

            # Silver is a separate tab; its price label is not present until
            # that tab is selected. Click the actual tab/button, not any
            # unrelated mention of silver elsewhere on the page.
            clicked = page.evaluate(
                """() => {
                    const norm = s => s.replace(/\\s+/g, ' ').trim();
                    const selectors = [
                      '[role="tab"]', 'button', '[role="button"]', '[onclick]'
                    ];
                    for (const selector of selectors) {
                      const candidates = [...document.querySelectorAll(selector)]
                        .filter(el => el.getClientRects().length &&
                          norm(el.innerText || el.textContent) === 'نقره');
                      if (candidates.length) {
                        candidates[0].click();
                        return true;
                      }
                    }
                    return false;
                }"""
            )
            if not clicked:
                raise ValueError("Could not find the visible silver tab on the public page")

            page.wait_for_function(
                """() => [...document.querySelectorAll('span')].some(s =>
                    s.textContent.includes('قیمت لحظه‌ای') &&
                    s.textContent.includes('میلی‌گرم') &&
                    s.textContent.includes('نقره'))""",
                timeout=15000,
            )
            silver = parse_price(read_visible_price("نقره"), "silver")

            print(f"Extracted public prices (per milligram): gold={gold}, silver={silver}")
            return gold, silver

        except Exception:
            print("Page URL:", page.url)
            print("Page title:", page.title())
            print("Page text (first 3500 chars):", page.locator("body").inner_text()[:3500])
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


def main():
    gold, silver = fetch_prices()
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    timestamp = now.strftime("%Y-%m-%d | %H:%M:%S")

    message = (
        "🪙 <b>قیمت لحظه‌ای طلا و نقره دیجی‌کالا</b>\n\n"
        f"🟡 <b>طلا</b> — هر ۱ میلی‌گرم\n"
        f"<code>{gold:,}</code> ریال\n\n"
        f"⚪ <b>نقره</b> — هر ۱ میلی‌گرم\n"
        f"<code>{silver:,}</code> ریال\n\n"
        f"🕒 آخرین بررسی: {timestamp}\n"
        '<a href="https://www.digikala.com/wealth/landing/">'
        "منبع: دیجی‌کالا</a>"
    )
    send_telegram_message(message)
    print(f"Published successfully: gold={gold}, silver={silver}")


if __name__ == "__main__":
    main()
