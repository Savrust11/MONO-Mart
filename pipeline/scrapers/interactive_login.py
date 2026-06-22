"""
Interactive login + session persistence for the external systems that the
non-ZOZO extractors depend on (Tableau Cloud, sitateru, MMS).

Why: these systems need a real browser login (Tableau also enforces 2FA).
We log in ONCE, save the authenticated browser session (cookies + local
storage) to a JSON file, and the production fetchers reuse that session so
no further interactive auth is needed until the session expires.

2FA handling WITHOUT needing to see the browser:
  After submitting credentials the script writes a marker file
    sessions/<target>.await2fa
  and then polls
    sessions/<target>.code
  for up to ~12 minutes. The operator just drops the 6-digit code (or any
  text the page expects) into that .code file (or it is written for them),
  the script types it, submits, and saves the session.

Usage:
  python interactive_login.py --target tableau
  python interactive_login.py --target sitateru
  python interactive_login.py --target mms

Env (credentials — set by the caller, never hard-coded):
  LOGIN_USER, LOGIN_PASS
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SESS = Path(__file__).parent / "sessions"
SESS.mkdir(exist_ok=True)

# Per-target login configuration. Selectors are best-effort and fall back to
# generic input[type=...] probing if the named selectors are not present.
TARGETS: dict[str, dict] = {
    # Tableau Cloud authenticates via Salesforce SSO. The redirect chain is:
    #   prod-apnortheast-a.online.tableau.com → login.salesforce.com (user/pass)
    #   → verify.salesforce.com/v1/verify (MFA code) → back to tableau host.
    # So the form selectors below target the Salesforce-hosted pages.
    "tableau": {
        "login_url": "https://prod-apnortheast-a.online.tableau.com/",
        # email-first: sso.online.tableau.com → #email + #login-submit →
        # identity.idp.tableau.com (password) → MFA code page
        "user_sel":  "#email, input[name='email'], input[type='email']",
        "email_next": "#login-submit, input[type='submit'], button[type='submit']",
        # password page = identity.idp.tableau.com (Auth0): #password +
        # #rememberCheckbox + #signInButton
        "pass_sel":  "#password, input[name='login_password'], input[type='password']",
        "user_next": "#signInButton, button[type='submit'], input[type='submit']",
        "remember_sel": "#rememberCheckbox, input[name='remember']",
        "has_2fa":   True,
        # Salesforce MFA code field candidates
        "code_sel":  "#emc, #smc, input[name='emc'], input[name='smc'], "
                     "input[autocomplete='one-time-code'], input[name*='code'], "
                     "input[name*='Verification'], input[type='tel']",
        "code_submit": "#save, #emc_save, input[name='save'], input[type='submit'], "
                       "button[type='submit']",
        "trust_sel": "#rememberUn, input[name='rememberUn'], "
                     "input[type='checkbox'][id*='trust'], input[type='checkbox'][name*='remember']",
        # logged in when URL is back on a tableau host (not salesforce/login/verify)
        "success_host": "online.tableau.com",
        "login_markers": ["salesforce.com", "signin", "login", "/auth", "/idp",
                          "mfa", "verify", "challenge"],
    },
    # sitateru: direct.sitateru.com is a landing page with a single
    # input[type=submit] "ログイン" → redirects to atelier.sitateru.com/my_id/login
    # (the real email+password form). entry_click reaches that form first.
    "sitateru": {
        "login_url": "https://direct.sitateru.com/",
        "entry_click": "input[type='submit'], a:has-text('ログイン'), "
                       "button:has-text('ログイン')",
        # atelier.sitateru.com/my_id/login form (verified)
        "user_sel":  "input[name='email'], #email, input[type='email']",
        "pass_sel":  "input[name='password'], #password, input[type='password']",
        "user_next": "input[name='commit'], button[type='submit'], input[type='submit']",
        "has_2fa":   False,
        "success_host": "direct.sitateru.com",
        "login_markers": ["my_id/login", "atelier.sitateru", "/oauth/authorize", "signin"],
    },
    # MMS: verified single-page form (id=user_id / passwd, no 2FA).
    "mms": {
        "login_url": "https://mms.a-rg.work/login.php",
        "user_sel":  "#user_id, input[name='user_id']",
        "pass_sel":  "#passwd, input[name='passwd']",
        "user_next": "button[type='submit'], input[type='submit']",
        "has_2fa":   False,
        "login_markers": ["login.php", "/login", "signin"],
    },
}


def _looks_logged_in(url: str, markers: list[str]) -> bool:
    u = url.lower()
    return not any(m in u for m in markers)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=list(TARGETS))
    ap.add_argument("--headless", default="1")
    ap.add_argument("--wait2fa", type=int, default=720, help="seconds to wait for 2FA code")
    args = ap.parse_args()

    cfg = TARGETS[args.target]
    user = os.environ.get("LOGIN_USER")
    pw   = os.environ.get("LOGIN_PASS")
    if not user or not pw:
        print("FATAL: LOGIN_USER / LOGIN_PASS not set")
        return 2

    state_path = SESS / f"{args.target}_state.json"
    code_file  = SESS / f"{args.target}.code"
    flag_file  = SESS / f"{args.target}.await2fa"
    done_file  = SESS / f"{args.target}.done"
    for f in (code_file, flag_file, done_file):
        f.unlink(missing_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless != "0")
        ctx = browser.new_context(locale="ja-JP", viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        def shot(tag: str) -> None:
            try:
                page.screenshot(path=str(SESS / f"{args.target}_{tag}.png"))
            except Exception:
                pass

        def logged_in() -> bool:
            host_ok = True
            if cfg.get("success_host"):
                host_ok = cfg["success_host"] in page.url.lower()
            return host_ok and _looks_logged_in(page.url, cfg["login_markers"])

        try:
            print(f"[{args.target}] opening {cfg['login_url']}")
            page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=45_000)
            time.sleep(3)
            print(f"[{args.target}] after-redirect url={page.url}")
            shot("01_login")

            # ── Entry button (landing pages with a 'login' button) ────────
            if cfg.get("entry_click"):
                try:
                    page.locator(cfg["entry_click"]).first.click(timeout=10_000)
                    time.sleep(4)
                    print(f"[{args.target}] entry clicked → url={page.url}")
                    shot("01b_after_entry")
                except Exception as e:
                    print(f"[{args.target}] entry click skipped: {str(e)[:100]}")

            # ── Username ──────────────────────────────────────────────────
            try:
                page.locator(cfg["user_sel"]).first.fill(user, timeout=20_000)
                print(f"[{args.target}] username filled")
            except Exception as e:
                print(f"[{args.target}] user field not found: {str(e)[:120]}")

            # Email-first flow (Tableau): click the email 'continue' button,
            # which redirects to the dedicated password page.
            if cfg.get("email_next") and page.locator(cfg["pass_sel"]).count() == 0:
                try:
                    page.locator(cfg["email_next"]).first.click(timeout=10_000)
                    time.sleep(5)
                    print(f"[{args.target}] email submitted → url={page.url}")
                    shot("01c_after_email")
                except Exception as e:
                    print(f"[{args.target}] email_next issue: {str(e)[:100]}")

            # Fallback: password still not present → try the generic next btn.
            if page.locator(cfg["pass_sel"]).count() == 0:
                try:
                    page.locator(cfg["user_next"]).first.click(timeout=8_000)
                    time.sleep(3)
                except Exception:
                    pass
            try:
                page.locator(cfg["pass_sel"]).first.fill(pw, timeout=20_000)
                print(f"[{args.target}] password filled")
            except Exception as e:
                print(f"[{args.target}] pass field not found: {str(e)[:120]}")

            # Tick a remember/trust checkbox so the session lasts longer.
            if cfg.get("remember_sel"):
                try:
                    rb = page.locator(cfg["remember_sel"])
                    if rb.count() > 0:
                        rb.first.check(timeout=4_000)
                        print(f"[{args.target}] remember-me checked")
                except Exception:
                    pass

            try:
                page.locator(cfg["user_next"]).first.click(timeout=12_000)
            except Exception:
                page.keyboard.press("Enter")
            time.sleep(6)
            print(f"[{args.target}] post-credentials url={page.url}")
            shot("02_after_creds")

            # ── 2FA (freshness-checked: ignore any pre-existing code file) ──
            if cfg["has_2fa"] and not logged_in():
                code_sel = cfg.get("code_sel",
                    "input[autocomplete='one-time-code'], input[name*='code'], "
                    "input[name*='otp'], input[id*='code'], input[name*='token'], "
                    "input[type='tel'], input[inputmode='numeric']")
                # Dump the MFA page DOM so we learn the exact code-field
                # selector even if submission fails (never waste a code twice).
                shot("03_mfa_page")
                try:
                    mfa_dom = page.evaluate("""() => {
                      const idsel = e => e.id ? ('#' + e.id)
                        : (e.name ? (e.tagName.toLowerCase() + '[name=' + JSON.stringify(e.name) + ']')
                        : e.tagName.toLowerCase());
                      return {
                        url: location.href,
                        inputs: Array.from(document.querySelectorAll('input,textarea')).map(e => ({
                          sel: idsel(e), name: e.name || null, id: e.id || null,
                          type: e.type || null, ph: e.placeholder || null,
                          vis: !!e.offsetParent })),
                        btns: Array.from(document.querySelectorAll("button,input[type='submit']")).map(e => ({
                          sel: idsel(e),
                          txt: (e.innerText || e.value || '').trim().slice(0, 30) }))
                      };
                    }""")
                    (SESS / f"{args.target}_mfa_dom.json").write_text(
                        __import__("json").dumps(mfa_dom, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                    print(f"[{args.target}] MFA DOM saved → {args.target}_mfa_dom.json")
                except Exception as e:
                    print(f"[{args.target}] MFA DOM dump failed: {str(e)[:80]}")
                code = None
                # ── Preferred: generate the TOTP code ourselves (no relay,
                #    no lockout risk — always the correct current code). ──────
                totp_secret = os.environ.get("TOTP_SECRET")
                if totp_secret:
                    try:
                        import pyotp
                        code = pyotp.TOTP(totp_secret).now()
                        print(f"[{args.target}] TOTP code generated programmatically")
                    except Exception as e:
                        print(f"[{args.target}] TOTP gen failed: {str(e)[:100]}")
                        code = None

                # ── Fallback: poll a fresh code file (operator-supplied). ─────
                if not code:
                    wait_started = time.time()
                    code_file.unlink(missing_ok=True)
                    flag_file.write_text(
                        f"2FA required for {args.target}. url={page.url} "
                        f"started={wait_started}\n", encoding="utf-8")
                    print(f"[{args.target}] >>> 2FA REQUIRED (url={page.url}). "
                          f"Waiting for FRESH code at {code_file} "
                          f"(up to {args.wait2fa}s) <<<")
                    deadline = time.time() + args.wait2fa
                    while time.time() < deadline:
                        if code_file.exists():
                            try:
                                mtime = code_file.stat().st_mtime
                            except OSError:
                                mtime = 0
                            if mtime >= wait_started:
                                c = code_file.read_text(encoding="utf-8").strip()
                                digits = "".join(ch for ch in c if ch.isdigit())
                                if len(digits) >= 4:
                                    code = digits
                                    break
                        time.sleep(3)
                    if not code:
                        print(f"[{args.target}] FATAL: no fresh 2FA code in time")
                        shot("03_2fa_timeout")
                        return 3
                print(f"[{args.target}] submitting 2FA code ({len(code)} digits)…")
                try:
                    page.locator(code_sel).first.fill(code, timeout=20_000)
                    if cfg.get("trust_sel"):
                        try:
                            t = page.locator(cfg["trust_sel"])
                            if t.count() > 0:
                                t.first.check(timeout=4_000)
                        except Exception:
                            pass
                    try:
                        page.locator(cfg.get("code_submit", cfg["user_next"])).first.click(timeout=12_000)
                    except Exception:
                        page.keyboard.press("Enter")
                except Exception as e:
                    print(f"[{args.target}] code submit issue: {str(e)[:120]}")
                    page.keyboard.press("Enter")
                time.sleep(8)
                print(f"[{args.target}] post-2FA url={page.url}")
                shot("04_after_2fa")
                flag_file.unlink(missing_ok=True)

            # ── Verify ────────────────────────────────────────────────────
            for _ in range(6):           # allow late redirects to settle
                if logged_in():
                    break
                time.sleep(3)
            final_url = page.url
            ok = logged_in()
            print(f"[{args.target}] final_url={final_url} logged_in={ok}")
            shot("05_final")
            if ok:
                ctx.storage_state(path=str(state_path))
                done_file.write_text(f"ok {final_url}", encoding="utf-8")
                print(f"[{args.target}] SESSION SAVED -> {state_path}")
                rc = 0
            else:
                print(f"[{args.target}] login NOT confirmed - session not saved")
                rc = 4
        except Exception as exc:
            print(f"[{args.target}] ERROR: {exc}")
            rc = 1
        finally:
            ctx.close()
            browser.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
