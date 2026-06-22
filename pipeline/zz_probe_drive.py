import sys, json
from pathlib import Path
sys.path.insert(0, r"C:\Users\Administrator\Downloads\system\pipeline")
KEY = Path(r"C:\Users\Administrator\Downloads\system\pipeline\sheets-sa-key.json")
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
creds = Credentials.from_service_account_file(str(KEY), scopes=SCOPES)
print("SA:", json.loads(KEY.read_text(encoding="utf-8")).get("client_email"))
drive = build("drive", "v3", credentials=creds, cache_discovery=False)

FOLDERS = {"orders": "1eRZoby0Bo8J4c6anWoe0PSGpDaGjePaR", "shipped": "1kSuIgbkOtpfOu474A-rFRWKcLN0wKjJK"}

def listing(fid):
    res = drive.files().list(q=f"'{fid}' in parents and trashed=false",
        fields="files(id,name,mimeType,size)", supportsAllDrives=True,
        includeItemsFromAllDrives=True, orderBy="name", pageSize=1000).execute()
    return res.get("files", [])

for key, fid in FOLDERS.items():
    try:
        items = listing(fid)
    except Exception as e:
        print(f"\n[{key}] ACCESS FAILED: {type(e).__name__}: {str(e)[:200]}")
        continue
    folders = [f for f in items if f["mimeType"].endswith("folder")]
    files   = [f for f in items if not f["mimeType"].endswith("folder")]
    print(f"\n=== {key} ({fid}) ===")
    print(f"  direct subfolders: {len(folders)}  direct files: {len(files)}")
    print(f"  subfolder names (first 20): {[f['name'] for f in folders[:20]]}")
    if files:
        print(f"  direct file names (first 5): {[f['name'] for f in files[:5]]}")
    if folders:
        sub = folders[0]
        subitems = listing(sub["id"])
        subfiles = [f for f in subitems if not f["mimeType"].endswith("folder")]
        print(f"  -> inside '{sub['name']}': {len(subitems)} items, sample files: {[f['name'] for f in subfiles[:5]]}")
        print(f"  -> sample mimeType: {subfiles[0]['mimeType'] if subfiles else 'n/a'}")
