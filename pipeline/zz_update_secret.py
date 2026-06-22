from google.cloud import secretmanager
client = secretmanager.SecretManagerServiceClient()
PROJECT = "mono-back-office-system"
updates = {"ZOZO_USER": "<ZOZO_LOGIN_ID>", "ZOZO_PASS": "<ZOZO_LOGIN_PASSWORD>"}
for secret_id, value in updates.items():
    parent = f"projects/{PROJECT}/secrets/{secret_id}"
    try:
        resp = client.add_secret_version(request={"parent": parent, "payload": {"data": value.encode("utf-8")}})
        print(f"  {secret_id}: new version added -> {resp.name.split('/')[-1]}")
    except Exception as e:
        print(f"  {secret_id}: FAILED {type(e).__name__}: {str(e)[:160]}")
