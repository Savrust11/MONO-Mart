"""
Probe multiple ZOZO URLs to find the actual login endpoint.
"""
import os
import time
from playwright.sync_api import sync_playwright

URLS_TO_TRY = [
    "https://to.zozo.jp/to/",
    "https://to.zozo.jp/to/login",
    "https://to.zozo.jp/",
    "https://to.zozo.jp/login",
    "https://backoffice.zozo.jp/",
    "https://zozoad.com/",
]

basic_user = os.environ.get("ZOZO_BASIC_USER", "")
basic_pw   = os.environ.get("ZOZO_BASIC_PASSWORD", "")
ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    for url in URLS_TO_TRY:
        print(f"\n=== Probing: {url} ===")
        for use_basic in [True, False]:
            kwargs = {
                "locale": "ja-JP",
                "viewport": {"width": 1440, "height": 900},
                "user_agent": ua,
            }
            if use_basic and basic_user:
                kwargs["http_credentials"] = {"username": basic_user, "password": basic_pw}

            context = browser.new_context(**kwargs)
            page = context.new_page()
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                title = page.title()[:80]
                final_url = page.url
                status = resp.status if resp else "?"
                body = page.inner_text("body")[:120].replace("\n", " ").strip()
                tag = "with-basic" if use_basic else "no-basic"
                print(f"   [{tag:10}] status={status} title='{title}'")
                print(f"                 final={final_url}")
                print(f"                 body={body[:100]}")
            except Exception as exc:
                print(f"   [{('with-basic' if use_basic else 'no-basic'):10}] ERROR: {str(exc)[:100]}")
            context.close()

    browser.close()
