# =============================================================================
# ZOZOAD 4種類CSV 取得ランナー（タスクスケジューラから呼ばれる）。
# 成功マーカー方式：本日すでに成功していれば fetch_zozoad_report.py 側でスキップ。
# =============================================================================
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$env:PYTHONIOENCODING = "utf-8"
$env:GOOGLE_APPLICATION_CREDENTIALS = Join-Path $ROOT "pipeline\sheets-sa-key.json"
$env:GCS_RAW_BUCKET = "mono-back-office-system-raw-data"
$env:HEADLESS = "1"

# secrets (BASIC auth) + 正しいログインアカウントで上書き
$secretsOut = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>$null
foreach ($line in $secretsOut) { if ($line -match "^(\w+)=(.+)$") { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] } }
# 認証情報はローカル機密ファイル（secrets.local.ps1・gitignore）から読み込む。
if (Test-Path "$PSScriptRoot\secrets.local.ps1") { . "$PSScriptRoot\secrets.local.ps1" }

& $PY (Join-Path $ROOT "pipeline\scrapers\fetch_zozoad_report.py")
exit $LASTEXITCODE
