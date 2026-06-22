import os
from google.cloud import secretmanager

client = secretmanager.SecretManagerServiceClient()
project = "mono-back-office-system"

try:
    client.create_secret(request={
        "parent": f"projects/{project}",
        "secret_id": "IMAP_PASS",
        "secret": {"replication": {"automatic": {}}},
    })
    print("Secret created.")
except Exception as e:
    print(f"(Secret may already exist: {e})")

r = client.add_secret_version(request={
    "parent": f"projects/{project}/secrets/IMAP_PASS",
    "payload": {"data": os.environ["IMAP_PASS"].encode()},  # 値は環境変数から
})
print("OK:", r.name)
