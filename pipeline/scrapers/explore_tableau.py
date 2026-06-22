"""Explore Tableau Cloud using the saved session — list workbooks/views so we
can locate the 発注管理 / 発注明細 workbooks (入荷残 source). Read-only."""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

SESS = Path(__file__).parent / "sessions"
STATE = SESS / "tableau_state.json"
SITE = "https://prod-apnortheast-a.online.tableau.com/#/site/sitaterunext"


def main():
    if not STATE.exists():
        print("FATAL: tableau_state.json missing — run interactive_login first")
        return 2
    rep = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(STATE), locale="ja-JP",
                             viewport={"width": 1440, "height": 1000})
        pg = ctx.new_page()
        try:
            # Explore page lists all workbooks
            # List all workbooks then all views via the explore filters
            pg.goto(SITE + "/workbooks", wait_until="domcontentloaded", timeout=60_000)
            time.sleep(12)  # Tableau SPA renders content lazily
            rep["explore_url"] = pg.url
            rep["title"] = pg.title()
            pg.screenshot(path=str(SESS / "tableau_explore.png"), full_page=True)
            data = pg.evaluate(r"""() => {
              const norm = s => (s == null ? '' : String(s)).replace(/\s+/g, ' ').trim();
              const links = [...document.querySelectorAll('a')]
                .map(a => ({ t: norm(a.innerText || a.getAttribute('aria-label')).slice(0,60),
                             h: a.getAttribute('href') || '' }))
                .filter(x => x.h && (x.h.includes('/workbooks/') || x.h.includes('/views/')
                                     || x.h.includes('/workbook/')));
              const cards = [...document.querySelectorAll(
                '[data-tb-test-id], [role="row"], [class*="GridItem"], [class*="card"]')]
                .map(c => norm(c.innerText).slice(0,80)).filter(Boolean);
              const uniq = [...new Set(cards)];
              return { links: links.slice(0,80), cards: uniq.slice(0,50) };
            }""")
            rep["links"] = data["links"]
            rep["cards"] = data["cards"]
            # Also try the REST-ish content API the SPA uses
            try:
                r = ctx.request.get(
                    "https://prod-apnortheast-a.online.tableau.com/api/3.19/sites",
                    timeout=20_000)
                rep["api_sites_status"] = r.status
            except Exception as e:
                rep["api_err"] = str(e)[:100]
        except Exception as e:
            rep["error"] = str(e)[:200]
        finally:
            ctx.close(); b.close()
    (SESS / "tableau_explore.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("explore_url:", rep.get("explore_url"))
    print("title:", rep.get("title"))
    print("links:", len(rep.get("links", [])))
    for l in rep.get("links", [])[:25]:
        print("  ", repr(l["t"]), "->", l["h"][:80])
    print("cards:", rep.get("cards", [])[:15])
    print("error:", rep.get("error"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
