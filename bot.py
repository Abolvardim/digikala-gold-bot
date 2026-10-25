import base64
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

URL = "https://www.digikala.com/wealth/landing/"
TELEGRAM_API = "https://api.telegram.org"
GITHUB_API = "https://api.github.com"

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]
GITHUB_BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
STATE_FILE = ".price_alert_state.json"

# Price targets in millions of tomans per gram of melted gold.
# Edit this list to add/remove your own buying targets.
PRICE_TARGETS_MILLION_TOMANS = [26.0, 25.5, 25.0]


def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_alert_state():
    url = f"{GITHUB_API}/repos/{GITHUB_REPOSITORY}/contents/{STATE_FILE}"
    response = requests.get(
        url,
        headers=github_headers(),
        params={"ref": GITHUB_BRANCH},
        timeout=20,
    )
    if response.status_code == 404:
        return {}, None
    response.raise_for_status()
    data = response.json()
    raw = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(raw), data["sha"]


def save_alert_state(state, current_sha):
    url = f"{GITHUB_API}/repos/{GITHUB_REPOSITORY}/contents/{STATE_FILE}"
    encoded = base64.b64encode(
        (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    ).decode("ascii")
    payload = {
        "message": "Update gold price reminder state",
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if current_sha:
        payload["sha"] = current_sha

    response = requests.put(
        url, headers=github_headers(), json=payload, timeout=20
    )
    response.raise_for_status()
    print("Saved price reminder state to GitHub.")


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
    message_id = result.get("message_id")
    print(
        "Telegram accepted message: "
        f"destination_type={chat.get('type')}, "
        f"destination_id={chat.get('id')}, "
        f"message_id={message_id}"
    )
    return message_id


def pin_telegram_message(message_id):
    response = requests.post(
        f"{TELEGRAM_API}/bot{BOT_TOKEN}/pinChatMessage",
        json={
            "chat_id": CHANNEL_ID,
            "message_id": message_id,
            "disable_notification": True,
        },
        timeout=20,
    )
    if response.ok and response.json().get("ok"):
        print(f"Pinned first-crossing alert message: {message_id}")
    else:
        print(
            "Could not pin alert message (the bot may need admin/pin permission): "
            f"{response.status_code} {response.text[:500]}"
        )


def main():
    gold = fetch_gold_price()
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    timestamp = now.strftime("%Y-%m-%d | %H:%M:%S")
    gold_million_tomans = gold / 10_000
    gold_display = f"{gold_million_tomans:.2f}"

    previous_state, state_sha = load_alert_state()
    current_state = {}
    newly_triggered = []

    for target in PRICE_TARGETS_MILLION_TOMANS:
        key = f"{target:.2f}"
        active_now = gold_million_tomans <= target
        was_active = bool(previous_state.get(key, False))
        current_state[key] = active_now
        if active_now and not was_active:
            newly_triggered.append(target)

    target_lines = []
    for target in sorted(PRICE_TARGETS_MILLION_TOMANS):
        key = f"{target:.2f}"
        if current_state[key]:
            marker = "🔔" if target in newly_triggered else "🟢"
            status = "هشدار تازه" if target in newly_triggered else "هنوز زیر"
            target_lines.append(
                f"{marker} <b> {target:g} M:</b> {status} (≤ {target:g} میلیون تومان)"
                
            )

    message = (
        "🟡 <b>قیمت لحظه‌ای طلای دیجی‌کالا</b>\n\n"
        f" <b>طلا</b> — هر ۱ میلی‌گرم\n"
        f"<code>{gold:,}</code> ریال\n"
        f"({gold_display} M)\n"
    )
    if target_lines:
        message += "\n" + "\n".join(target_lines) + "\n"
    message += (
        f"\n آخرین بررسی: {timestamp}\n"
        '<a href="https://www.digikala.com/wealth/landing/">'
        " دیجی‌کالا</a>"
    )

    message_id = send_telegram_message(message)

    if newly_triggered and message_id:
        pin_telegram_message(message_id)

    if current_state != previous_state:
        save_alert_state(current_state, state_sha)

    print(
        f"Published successfully: gold={gold}; "
        f"active_targets={[t for t in PRICE_TARGETS_MILLION_TOMANS if current_state[f'{t:.2f}']]}; "
        f"new_targets={newly_triggered}"
    )


if __name__ == "__main__":
    main()
