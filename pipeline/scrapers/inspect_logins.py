"""Safely inspect the REAL login-page DOM for tableau / sitateru / mms.

Submits NOTHING — only navigates to the login URL, follows redirects to the
actual IdP page, optionally clicks an obvious 'login' entry button, and dumps
every input/button + the final URL. This does not trigger 2FA or risk
account lockout (no credentials are entered).
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).parent / "sessions"
OUT.mkdir(exist_ok=True)

TARGETS = {
    "tableau":  "https://prod-apnortheast-a.online.tableau.com/",
    "sitateru": "https://direct.sitateru.com/",
    "mms":      "https://mms.a-rg.work/login.php",
}
# optional entry-button texts to reach the real form
ENTRY = ["ログイン", "Log In", "Login", "Sign In", "サインイン", "メールアドレスでログイン"]


def dump(page):
    return page.evaluate(r"""() => {
      const sel = e => {
        if (e.id) return '#' + e.id;
        if (e.name) return e.tagName.toLowerCase() + "[name='" + e.name + "']";
        return e.tagName.toLowerCase() + (e.type ? "[type='"+e.type+"']" : "");
      };
      const inputs = [...document.querySelectorAll('input,textarea')].map(e => ({
        sel: sel(e), name: e.name||null, id: e.id||null, type: e.type||null,
        ph: e.placeholder||null, vis: !!e.offsetParent }));
      const btns = [...document.querySelectorAll("button,input[type='submit'],a")]
        .map(e => ({ sel: sel(e), type: e.type||null,
          txt: (e.innerText||e.value||'').trim().slice(0,30),
          vis: !!e.offsetParent }))
        .filter(b => b.txt || b.type === 'submit');
      return { url: location.href, title: document.title,
               inputs, btns: btns.slice(0, 25) };
    }""")


def main():
    rep = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width": 1440, "height": 900})
        for name, url in TARGETS.items():
            pg = ctx.new_page()
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=45_000)
                time.sleep(4)
                step1 = dump(pg)
                # If no password field visible, try an entry button then re-dump
                has_pw = any(i["type"] == "password" for i in step1["inputs"])
                step2 = None
                if not has_pw:
                    for t in ENTRY:
                        try:
                            loc = pg.locator(f"a:has-text('{t}'), button:has-text('{t}')")
                            if loc.count() > 0:
                                loc.first.click(timeout=6_000)
                                time.sleep(4)
                                step2 = dump(pg)
                                break
                        except Exception:
                            continue
                pg.screenshot(path=str(OUT / f"inspect_{name}.png"))
                rep[name] = {"start_url": url, "step1": step1, "step2": step2}
                print(f"[{name}] final={ (step2 or step1)['url'] }  "
                      f"pw_field={ any(i['type']=='password' for i in (step2 or step1)['inputs']) }")
            except Exception as e:
                rep[name] = {"error": str(e)[:200]}
                print(f"[{name}] ERROR {str(e)[:120]}")
            finally:
                pg.close()
        ctx.close(); b.close()
    (OUT / "inspect_report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved sessions/inspect_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
