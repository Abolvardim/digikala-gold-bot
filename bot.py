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
                    const numeric = s => /^[0-9][0-9,]*$/.test(norm(s));
                    const labels = [...body.querySelectorAll('*')].filter(el => {
                        if (el.children.length) return false;
                        const t = norm(el.textContent);
                        return t.includes('قیمت لحظه‌ای') &&
                          t.includes('میلی‌گرم') && t.includes(metal);
                    });
                    for (const label of labels) {
                        // Walk up from the label; the site has changed wrapper
                        // classes before, so do not depend on a single CSS path.
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
                }""",
                metal,
            )

        def wait_for_price(metal, timeout=45000):
            # Wait for the numeric price, not merely for its label to appear.
            page.wait_for_function(
                """metal => {
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
                      norm(el.textContent).includes(metal));
                    return labels.some(label => {
                      let parent = label;
                      for (let depth = 0; parent && depth < 7; depth++, parent = parent.parentElement) {
                        if ([...parent.querySelectorAll('span,div,p,strong,b')]
                          .some(el => el.children.length === 0 && isNumber(el.textContent))) {
                          return true;
                        }
                      }
                      return false;
                    });
                }""",
                arg=metal,
                timeout=timeout,
            )
            value = read_visible_price(metal)
            if not value:
                raise ValueError(f"Price label appeared but its numeric {metal} price did not: {URL}")
            price = int(value.replace(",", ""))
            if price <= 0:
                raise ValueError(f"Invalid {metal} price: {value}")
            return price

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            gold = wait_for_price("طلا")

            # The silver quote is displayed after selecting the silver tab.
            clicked = page.evaluate(
                """() => {
                    const norm = s => s.replace(/\\s+/g, ' ').trim();
                    for (const selector of ['[role="tab"]', 'button', '[role="button"]', '[onclick]', 'a', 'div', 'span']) {
                      const candidates = [...document.querySelectorAll(selector)]
                        .filter(el => el.getClientRects().length &&
                          norm(el.innerText || el.textContent) === 'نقره');
                      const candidate = candidates.find(el => el.children.length < 3);
                      if (candidate) {
                        candidate.click();
                        return true;
                      }
                    }
                    return false;
                }"""
            )
            if not clicked:
                raise ValueError("Could not find the visible silver tab on the public page")
            silver = wait_for_price("نقره", timeout=30000)

            print(f"Extracted public prices (per milligram): gold={gold}, silver={silver}")
            return gold, silver

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
