# =============================================================================
# ZOZOAD リトライスケジュールをタスクスケジューラに登録。
#   トリガー: 12:30 / 13:30 / 14:30 / 15:30 / 18:00 / 翌07:00（毎日）
#   各回 run_zozoad.ps1 を実行。本日成功済みなら scraper 側でスキップ。
#   → 12:30で成功すれば以降は何もしない。失敗（データ未反映）なら次の時刻で再取得。
# =============================================================================
$taskName = "MONO-BackOffice-ZOZOAD-Retry"
$runner   = "C:\Users\Administrator\Downloads\system\run_zozoad.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""

$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At 12:30),
    (New-ScheduledTaskTrigger -Daily -At 13:30),
    (New-ScheduledTaskTrigger -Daily -At 14:30),
    (New-ScheduledTaskTrigger -Daily -At 15:30),
    (New-ScheduledTaskTrigger -Daily -At 18:00),
    (New-ScheduledTaskTrigger -Daily -At 07:00)
)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers `
    -Settings $settings -Description "ZOZOAD 4種類CSV 失敗時リトライ (成功したらスキップ)" -Force | Out-Null

Write-Output "登録完了: $taskName  (トリガー 12:30/13:30/14:30/15:30/18:00/07:00)"
