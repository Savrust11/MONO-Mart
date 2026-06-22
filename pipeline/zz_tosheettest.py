import json, urllib.request
# 1) スプシ出力APIをPOST
url="http://localhost:3000/api/period-report/to-sheet?product_code=sc1032&start=2026-05-01&end=2026-05-31"
req=urllib.request.Request(url, method="POST")
try:
    j=json.load(urllib.request.urlopen(req, timeout=120))
    print("POST結果:", j)
except urllib.error.HTTPError as e:
    print("POST失敗:", e.read().decode("utf-8","replace")[:300]); raise SystemExit
# 2) シートを読み返して確認
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
creds=Credentials.from_service_account_file(r"C:\Users\Administrator\Downloads\system\pipeline\sheets-sa-key.json", scopes=["https://www.googleapis.com/auth/spreadsheets"])
svc=build("sheets","v4",credentials=creds)
vals=svc.spreadsheets().values().get(spreadsheetId="1DX9992gHjYk5FI5u2sYmPeseH7A5XeHX4z9yVxo-97Q", range="A1:D12").execute().get("values",[])
print(f"\nシートの中身（先頭{len(vals)}行）:")
for row in vals:
    print("  ", " | ".join(str(c) for c in row))
