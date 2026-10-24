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
        page = browser.new_page(
            locale="fa-IR",
            timezone_id="Asia/Tehran",
        )

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            # The public landing page renders prices client-side; no login/session
            # is needed. Locate the price row by its human-readable label rather
            # than relying on the site's long, frequently changing CSS path.
            page.wait_for_function(
                """() => {
                    const norm = s => s
                      .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
                      .replace(/[٬،]/g, ',')
                      .replace(/\\s+/g, ' ')
                      .trim();
                    const labels = [...document.querySelectorAll('span')]
                      .map(s => norm(s.textContent));
                    return labels.some(s => s.includes('قیمت لحظه‌ای') &&
                      s.includes('میلی‌گرم') && s.includes('طلا')) &&
                      labels.some(s => s.includes('قیمت لحظه‌ای') &&
                      s.includes('میلی‌گرم') && s.includes('نقره'));
                }""",
                timeout=45000,
            )

            prices = page.locator("body").evaluate(
                """body => {
                    const norm = s => s
                      .replace(/[۰-۹]/g, d => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d)))
                      .replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
                      .replace(/[٬،]/g, ',')
                      .replace(/\\s+/g, ' ')
                      .trim();

                    const spans = [...body.querySelectorAll('span')];

                    function getPrice(metal) {
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
                    }

                    return {
                        gold: getPrice('طلا'),
                        silver: getPrice('نقره')
                    };
                }"""
            )

            def parse_price(value, name):
                if not value:
                    raise ValueError(f"Could not find the public {name} price on {URL}")
                price = int(value.replace(",", ""))
                if price <= 0:
                    raise ValueError(f"Invalid {name} price: {value}")
                return price

            gold = parse_price(prices["gold"], "gold")
            silver = parse_price(prices["silver"], "silver")
            print(f"Extracted public prices (per milligram): gold={gold}, silver={silver}")
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
