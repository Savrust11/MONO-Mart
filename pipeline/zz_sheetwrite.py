from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
SHEET_ID = "1DX9992gHjYk5FI5u2sYmPeseH7A5XeHX4z9yVxo-97Q"
KEY = r"C:\Users\Administrator\Downloads\system\pipeline\sheets-sa-key.json"
try:
    creds = Credentials.from_service_account_file(KEY, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    svc = build("sheets", "v4", credentials=creds)
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    print("読み取りOK タイトル:", meta["properties"]["title"])
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range="A1", valueInputOption="RAW",
        body={"values": [["接続テストOK"], ["この行は後で発注管理表で上書きされます"]]}).execute()
    print("✅ 書き込みOK → 編集者共有 成功。スプシ出力の実装に進めます。")
    print("   （シートのA1に『接続テストOK』が入っているはずです。ご確認ください）")
except Exception as e:
    msg = str(e)
    print("失敗:", "403/権限なし（まだ編集者共有が反映されていない可能性）" if ("403" in msg or "permission" in msg.lower()) else msg[:200])
