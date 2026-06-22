"""Safely reach + dump the DEEPER login pages (password step) for
tableau and sitateru. Enters the EMAIL/username only and clicks the
continue button — NEVER a password or 2FA code — so this triggers no
2FA and cannot lock the account.
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "sessions"
USER = "yujin-yamaguchi@mono-mart.jp"   # email is non-sensitive; no pw entered


def dump(page):
    return page.evaluate(r"""() => {
      const sel = e => e.id ? '#'+e.id
        : (e.name ? e.tagName.toLowerCase()+"[name='"+e.name+"']"
        : e.tagName.toLowerCase()+(e.type?"[type='"+e.type+"']":""));
      return { url: location.href, title: document.title,
        inputs: [...document.querySelectorAll('input,textarea')].map(e=>({
          sel: sel(e), name:e.name||null, id:e.id||null, type:e.type||null,
          ph:e.placeholder||null, vis:!!e.offsetParent})),
        btns: [...document.querySelectorAll("button,input[type='submit'],a")]
          .map(e=>({sel:sel(e),type:e.type||null,
            txt:(e.innerText||e.value||'').trim().slice(0,30),vis:!!e.offsetParent}))
          .filter(b=>b.txt||b.type==='submit').slice(0,20) };
    }""")


def main():
    rep = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width":1440,"height":900})

        # ── Tableau: email → continue → password page ──────────────────
        pg = ctx.new_page()
        try:
            pg.goto("https://prod-apnortheast-a.online.tableau.com/",
                    wait_until="domcontentloaded", timeout=45_000)
            time.sleep(4)
            pg.locator("#email, input[type='email']").first.fill(USER, timeout=15_000)
            pg.locator("#login-submit, input[type='submit']").first.click(timeout=10_000)
            time.sleep(6)               # redirect to identity.idp.tableau.com
            rep["tableau_pw_page"] = dump(pg)
            pg.screenshot(path=str(OUT/"inspect_tableau_pw.png"))
            print("[tableau] pw-page url=", rep["tableau_pw_page"]["url"])
        except Exception as e:
            rep["tableau_pw_page"] = {"error": str(e)[:200]}
            print("[tableau] ERR", str(e)[:140])
        finally:
            pg.close()

        # ── sitateru: click ログイン → atelier login form ───────────────
        pg = ctx.new_page()
        try:
            pg.goto("https://direct.sitateru.com/",
                    wait_until="domcontentloaded", timeout=45_000)
            time.sleep(4)
            try:
                pg.locator("input[type='submit'], a:has-text('ログイン'), "
                           "button:has-text('ログイン')").first.click(timeout=10_000)
                time.sleep(6)
            except Exception as e:
                print("[sitateru] entry click:", str(e)[:100])
            rep["sitateru_login"] = dump(pg)
            pg.screenshot(path=str(OUT/"inspect_sitateru_login.png"))
            print("[sitateru] login url=", rep["sitateru_login"]["url"])
        except Exception as e:
            rep["sitateru_login"] = {"error": str(e)[:200]}
            print("[sitateru] ERR", str(e)[:140])
        finally:
            pg.close()

        ctx.close(); b.close()
    (OUT/"inspect_deep.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved sessions/inspect_deep.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
