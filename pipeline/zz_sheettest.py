import importlib
for lib in ["gspread","googleapiclient","google.oauth2.service_account"]:
    try:
        importlib.import_module(lib); print(f"OK  {lib}")
    except Exception as e:
        print(f"NG  {lib}: {str(e)[:50]}")
# SAがスプレッドシート作成できるか試す
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    SCOPES=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds=Credentials.from_service_account_file(r"C:\Users\Administrator\Downloads\system\pipeline\sheets-sa-key.json",scopes=SCOPES)
    print("SA email:", creds.service_account_email)
    svc=build("sheets","v4",credentials=creds)
    ss=svc.spreadsheets().create(body={"properties":{"title":"【テスト】発注管理表_接続確認"}}).execute()
    sid=ss["spreadsheetId"]
    print("作成成功 spreadsheetId:", sid)
    print("URL:", ss["spreadsheetUrl"])
    # 後始末（削除）
    drive=build("drive","v3",credentials=creds)
    drive.files().delete(fileId=sid).execute()
    print("テストシート削除OK（権限フル確認）")
except Exception as e:
    print("作成テスト失敗:", str(e)[:300])
