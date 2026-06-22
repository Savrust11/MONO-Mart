"""Explore the 商品別実績(新) Looker dashboard inside ZOZO BO.
Login → LookerDashboards.asp → open 商品別実績(新) → dump frames,
the ショップ名 filter, the 3-dot/Download controls, screenshots.
Read-only assessment (no download committed)."""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
BASE = "https://to.zozo.jp/to/"
OUT = Path(__file__).parent / "html"


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def controls(scope):
    try:
        return scope.evaluate(r"""()=>{
          const norm=s=>(s==null?'':String(s)).replace(/\s+/g,' ').trim();
          return [...document.querySelectorAll('button,[role=button],a,[aria-label],[data-testid]')]
            .map(e=>({tag:e.tagName,
              al:norm(e.getAttribute&&e.getAttribute('aria-label')),
              tid:e.getAttribute&&e.getAttribute('data-testid')||null,
              tx:norm(e.innerText).slice(0,24),vis:!!e.offsetParent}))
            .filter(x=>(x.al||x.tid||x.tx) &&
              /download|ダウンロ|csv|menu|more|⋮|options|gear|filter|shop|ショップ|描画|render|run|実行/i
              .test((x.al||'')+(x.tid||'')+(x.tx||''))).slice(0,30);
        }""")
    except Exception as e:
        return [{"err": str(e)[:80]}]


def main():
    rep = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width": 1680, "height": 1050},
            accept_downloads=True,
            http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                              "password": os.environ["ZOZO_BASIC_PASSWORD"]})
        pg = ctx.new_page()
        try:
            login(pg)
            # 1) dashboards list
            pg.goto(BASE + "LookerDashboards.asp",
                    wait_until="domcontentloaded", timeout=45_000)
            time.sleep(8)
            rep["dash_url"] = pg.url
            pg.screenshot(path=str(OUT / "looker_01_list.png"), full_page=True)
            links = pg.evaluate(r"""()=>{
              const norm=s=>(s==null?'':String(s)).replace(/\s+/g,' ').trim();
              return [...document.querySelectorAll('a,[role=link],div,span')]
                .map(e=>({t:norm(e.innerText).slice(0,30),
                  h:e.getAttribute&&e.getAttribute('href')||'',
                  oc:(e.getAttribute&&e.getAttribute('onclick')||'').slice(0,120)}))
                .filter(x=>/商品別実績|実績\(新\)|Looker|dashboard/i.test(x.t+x.h+x.oc));
            }""")
            rep["dash_links"] = links[:20]
            # 2) try to open 商品別実績(新)
            opened = False
            for sel in ["text=商品別実績(新)", "text=商品別実績（新）",
                        "a:has-text('商品別実績')", "[aria-label*='商品別実績']"]:
                try:
                    loc = pg.locator(sel)
                    if loc.count() > 0:
                        loc.first.click(timeout=8000)
                        opened = True
                        time.sleep(15)
                        break
                except Exception:
                    continue
            rep["opened"] = opened
            rep["after_url"] = pg.url
            pg.screenshot(path=str(OUT / "looker_02_dash.png"), full_page=True)
            rep["frames"] = [f.url for f in pg.frames]
            rep["main_controls"] = controls(pg)
            rep["frame_controls"] = {}
            for fr in pg.frames:
                if fr == pg.main_frame:
                    continue
                rep["frame_controls"][fr.url[:90]] = controls(fr)
        except Exception as e:
            rep["fatal"] = str(e)[:200]
        finally:
            ctx.close(); b.close()
    (OUT / "looker_probe.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("dash_url:", rep.get("dash_url"))
    print("dash_links:", rep.get("dash_links"))
    print("opened:", rep.get("opened"), "after_url:", rep.get("after_url"))
    print("frames:", rep.get("frames"))
    print("main_controls:", rep.get("main_controls"))
    for k, v in rep.get("frame_controls", {}).items():
        print("FRAME", k)
        for c in v[:15]:
            print("  ", c)
    print("fatal:", rep.get("fatal"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
