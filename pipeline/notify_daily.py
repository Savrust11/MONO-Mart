"""Daily acquisition alert — verify the target day landed, post status to a webhook.

Usage:  python notify_daily.py <YYYY-MM-DD>
Env:    ALERT_WEBHOOK_URL  (Slack / Google Chat / Discord incoming webhook)
        ALERT_ON           "always" (default) | "failure"  — when to send

Signal = data presence for the target day. orders/在庫/在庫SKU/予約 are next-day
available, so 0 rows => acquisition failed. performance has ZOZO's ~3-day lag so it
is reported for info only (never triggers an alert).
"""
import os, sys, json, urllib.request
from google.cloud import bigquery

PROJECT = "mono-back-office-system"
A = f"{PROJECT}.analytics_layer"
target = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
bq = bigquery.Client(project=PROJECT)
n = lambda sql: list(bq.query(sql))[0]["n"]

# next-day-available sources (0 rows => failure)
checks = {
    "orders(受注)":        f"SELECT COUNT(*) n FROM `{A}.sales_daily` WHERE source_file='orders' AND sale_date='{target}'",
    "stock(在庫)":         f"SELECT COUNT(*) n FROM `{A}.stock_analysis` WHERE snapshot_date='{target}'",
    "inventory(倉庫在庫)":  f"SELECT COUNT(*) n FROM `{A}.inventory_snapshot` WHERE snapshot_date='{target}'",
    "reservations(予約)":  f"SELECT COUNT(*) n FROM `{A}.reservations` WHERE reservation_date='{target}'",
}
res = {k: n(v) for k, v in checks.items()}
missing = [k for k, c in res.items() if c == 0]
ok = not missing

perf_latest = list(bq.query(f"SELECT MAX(sale_date) m FROM `{A}.sales_daily` WHERE source_file='performance'"))[0]["m"]

head = f"{'✅ 成功' if ok else '❌ 取得失敗'} — MONO日次取得 {target}"
body = "\n".join(f"{'✅' if res[k] else '❌'} {k}: {res[k]:,}行" for k in checks)
note = f"\nℹ️ performance(UU/CVR)はZOZO約3日遅れ。最新={perf_latest}"
if missing:
    note += f"\n⚠️ 欠損: {', '.join(missing)} → 自動取得が失敗した可能性。run_daily_linux.sh のログを確認してください。"
msg = f"{head}\n{body}{note}"
print(msg)

mode = os.environ.get("ALERT_ON", "always").lower()
send = (mode == "always") or (mode == "failure" and not ok)


def send_email():
    import smtplib
    from email.mime.text import MIMEText
    from email.header import Header
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user, pw, to = os.environ["SMTP_USER"], os.environ["SMTP_PASS"], os.environ["ALERT_EMAIL_TO"]
    m = MIMEText(msg, "plain", "utf-8")
    m["Subject"], m["From"], m["To"] = Header(head, "utf-8"), user, to
    recipients = [a.strip() for a in to.split(",") if a.strip()]
    if port == 465:                                   # 暗黙SSL（Xserver等）
        s = smtplib.SMTP_SSL(host, port, timeout=25)
    else:                                             # 587 = STARTTLS
        s = smtplib.SMTP(host, port, timeout=25); s.starttls()
    s.login(user, pw)
    s.sendmail(user, recipients, m.as_string()); s.quit()


def send_webhook(url):
    payload = {"content": msg} if "discord" in url else {"text": msg}  # Discord=content / Slack・Chat=text
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=15)


url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
have_email = all(os.environ.get(k) for k in ("SMTP_USER", "SMTP_PASS", "ALERT_EMAIL_TO"))
if not (url or have_email):
    print("[notify] 通知先未設定（メール/Webhook）— 表示のみ")
elif not send:
    print("[notify] 成功のため送信スキップ (ALERT_ON=failure)")
else:
    if have_email:
        try: send_email(); print("[notify] メール送信OK")
        except Exception as e: print("[notify] メール送信失敗:", str(e)[:160])
    if url:
        try: send_webhook(url); print("[notify] webhook送信OK")
        except Exception as e: print("[notify] webhook送信失敗:", str(e)[:160])

sys.exit(0 if ok else 1)
