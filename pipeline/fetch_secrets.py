"""
Fetch credentials from GCP Secret Manager and print KEY=VALUE lines.
Called by run_daily.ps1 / run_zozoad_noon.ps1 instead of gcloud CLI.
Exit 0 on success, exit 1 on failure.

REQUIRED secrets (failure exits 1 and aborts daily run):
  ZOZO_BASIC_USER / ZOZO_BASIC_PASS / ZOZO_USER / ZOZO_PASS

OPTIONAL secrets (missing = silently skipped, daily run continues):
  IMAP_PASS       -- Gmail app-password for yujin-yamaguchi@mono-mart.jp
  SITATERU_USER   -- Sitateru login email (only needed when session file expires)
  SITATERU_PASS   -- Sitateru login password
"""
import sys
from google.cloud import secretmanager

PROJECT = "mono-back-office-system"

REQUIRED_SECRETS = {
    "ZOZO_BASIC_USER":     "ZOZO_BASIC_USER",
    "ZOZO_BASIC_PASSWORD": "ZOZO_BASIC_PASS",
    "ZOZO_LOGIN_ID":       "ZOZO_USER",
    "ZOZO_LOGIN_PASSWORD": "ZOZO_PASS",
}

OPTIONAL_SECRETS = {
    "IMAP_PASS":     "IMAP_PASS",
    "SITATERU_USER": "SITATERU_USER",
    "SITATERU_PASS": "SITATERU_PASS",
}

try:
    client = secretmanager.SecretManagerServiceClient()

    for env_key, secret_id in REQUIRED_SECRETS.items():
        name = f"projects/{PROJECT}/secrets/{secret_id}/versions/latest"
        resp = client.access_secret_version(request={"name": name})
        print(f"{env_key}={resp.payload.data.decode('utf-8')}")

    for env_key, secret_id in OPTIONAL_SECRETS.items():
        try:
            name = f"projects/{PROJECT}/secrets/{secret_id}/versions/latest"
            resp = client.access_secret_version(request={"name": name})
            print(f"{env_key}={resp.payload.data.decode('utf-8')}")
        except Exception:
            pass  # optional — missing secret is not fatal

    sys.exit(0)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
