import sys, io, time
from pathlib import Path
sys.path.insert(0, r"C:\Users\Administrator\Downloads\system\pipeline")
KEY = Path(r"C:\Users\Administrator\Downloads\system\pipeline\sheets-sa-key.json")
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
sys.path.insert(0, r"C:\Users\Administrator\Downloads\system\pipeline\scrapers")
import backfill_drive_to_gcs as B

creds = Credentials.from_service_account_file(str(KEY), scopes=["https://www.googleapis.com/auth/drive.readonly"])
drive = build("drive","v3",credentials=creds,cache_discovery=False)
def find(fid,name):
    return drive.files().list(q=f"'{fid}' in parents and trashed=false and name='{name}'",
        fields="files(id,name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute().get("files",[])
def dl(fid):
    buf=io.BytesIO(); d=MediaIoBaseDownload(buf, drive.files().get_media(fileId=fid,supportsAllDrives=True)); done=False
    while not done: _,done=d.next_chunk()
    return buf.getvalue()

mf=find("1eRZoby0Bo8J4c6anWoe0PSGpDaGjePaR","202407")
of=find(mf[0]["id"],"2024_07_15.xlsx")
raw=dl(of[0]["id"])
print(f"downloaded {len(raw):,} bytes")
t=time.time()
csv=B._xlsx_to_csv(raw)
dt=time.time()-t
print(f"calamine convert: {dt:.2f}s  -> {len(csv):,} csv bytes")
# show first 2 lines
head=csv.decode('utf-8-sig').splitlines()[:2]
for h in head: print("  ", h[:140])
