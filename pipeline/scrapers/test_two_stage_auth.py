"""
ZOZO 2-stage HTTP Basic Auth test

The ZOZO back office requires TWO sequential Basic Auth challenges:
  Stage 1 (proxy/CDN): <ZOZO_BASIC_USER> / <ZOZO_BASIC_PASSWORD>
  Stage 2 (app):       <ZOZO_LOGIN_ID> / <ZOZO_LOGIN_PASSWORD>

Playwright's `http_credentials` only handles ONE set, so we use route
interception to send the right Authorization header per request based on
which realm the server is challenging.
"""
import base64
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Route, Request

LOGIN_URL = "https://to.zozo.jp/to/"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Credentials
STAGE1_USER = os.environ.get("ZOZO_BASIC_USER",     "<ZOZO_BASIC_USER>")
STAGE1_PW   = os.environ.get("ZOZO_BASIC_PASSWORD", "<ZOZO_BASIC_PASSWORD>")
STAGE2_USER = os.environ.get("ZOZO_LOGIN_ID",       "<ZOZO_LOGIN_ID>")
STAGE2_PW   = os.environ.get("ZOZO_LOGIN_PASSWORD", "<ZOZO_LOGIN_PASSWORD>")


def basic_auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


# ── Strategy 1: try just stage 1 first (might be all that's needed) ──
print("=" * 70)
print("STRATEGY 1: Send only stage-1 credentials via http_credentials")
print("=" * 70)
print(f"Stage 1: {STAGE1_USER} / {'*' * len(STAGE1_PW)}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        locale="ja-JP",
        viewport={"width": 1280, "height": 800},
        http_credentials={"username": STAGE1_USER, "password": STAGE1_PW},
    )
    page = ctx.new_page()
    try:
        resp = page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20_000)
        print(f"   status={resp.status if resp else '?'}  url={page.url}")
        print(f"   title={page.title()[:80]}")
        body = page.inner_text("body")[:200].replace("\n", " ")
        print(f"   body={body}")
        page.screenshot(path=str(SCREENSHOT_DIR / "10_stage1_only.png"))
    except Exception as exc:
        print(f"   ERROR: {exc}")
    ctx.close()
    browser.close()

# ── Strategy 2: stage-1 via http_credentials, stage-2 via header injection ──
print()
print("=" * 70)
print("STRATEGY 2: Stage-1 via http_credentials, Stage-2 via Authorization header")
print("=" * 70)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        locale="ja-JP",
        viewport={"width": 1280, "height": 800},
        http_credentials={"username": STAGE1_USER, "password": STAGE1_PW},
        extra_http_headers={
            "Authorization": basic_auth_header(STAGE2_USER, STAGE2_PW),
        },
    )
    page = ctx.new_page()
    try:
        resp = page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20_000)
        print(f"   status={resp.status if resp else '?'}  url={page.url}")
        print(f"   title={page.title()[:80]}")
        body = page.inner_text("body")[:200].replace("\n", " ")
        print(f"   body={body}")
        page.screenshot(path=str(SCREENSHOT_DIR / "11_with_extra_header.png"))
    except Exception as exc:
        print(f"   ERROR: {exc}")
    ctx.close()
    browser.close()

# ── Strategy 3: route interception to control auth per realm ──
print()
print("=" * 70)
print("STRATEGY 3: Route interception — read WWW-Authenticate, respond per realm")
print("=" * 70)

# Track which auth attempt we're on per URL
auth_attempts: dict = {}

def handle_route(route: Route):
    req = route.request
    headers = dict(req.headers)
    # Always include both auth tokens; server picks the matching one
    # (Most servers ignore extra Authorization headers, but this works for
    # nested auth if the inner server reads from cookie / different header.)
    n = auth_attempts.get(req.url, 0)
    if n == 0:
        headers["Authorization"] = basic_auth_header(STAGE1_USER, STAGE1_PW)
    elif n == 1:
        headers["Authorization"] = basic_auth_header(STAGE2_USER, STAGE2_PW)
    auth_attempts[req.url] = n + 1
    route.continue_(headers=headers)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(locale="ja-JP", viewport={"width": 1280, "height": 800})
    page = ctx.new_page()

    page.route("**/*", handle_route)

    try:
        resp = page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20_000)
        print(f"   status={resp.status if resp else '?'}  url={page.url}")
        print(f"   title={page.title()[:80]}")
        body = page.inner_text("body")[:200].replace("\n", " ")
        print(f"   body={body}")
        page.screenshot(path=str(SCREENSHOT_DIR / "12_route_intercept.png"))
    except Exception as exc:
        print(f"   ERROR: {exc}")
    ctx.close()
    browser.close()

print("\nDone — see screenshots/ for visual confirmation")
