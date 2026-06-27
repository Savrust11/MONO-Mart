#!/bin/bash
# =============================================================================
# 取得リトライ・スケジュール（顧客2026 画像）。
#   1回目12:30 → 失敗時 13:30/14:30/15:30/18:00 → 翌朝07:00(最終) と
#   「成功するまで」リトライ。成功した日は以降スキップ（二重取得しない）。
#   cron 例:  30 12,13,14,15 * * *  /…/run_acquire_retry.sh
#             0 18 * * *            /…/run_acquire_retry.sh
#             0 7  * * *            /…/run_acquire_retry.sh
# 成功判定＝鮮度チェック(data_freshness.py --needs-acquire)が「全ソース想定ラグ内」。
# =============================================================================
set -uo pipefail
ROOT=/home/myuser/Downloads/system
cd "$ROOT" || exit 3
LOGDIR="$ROOT/logs"; mkdir -p "$LOGDIR"
DAY=$(date +%F)
MARKER="$LOGDIR/.acquire_ok_$DAY"
LOG="$LOGDIR/acquire_retry_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "===== ACQUIRE RETRY START $(date) ====="

# 既に本日成功済みなら何もしない（リトライ終了）
if [ -f "$MARKER" ]; then
  echo "本日は取得成功済み → スキップ"; exit 0
fi

# 多重起動防止（前のスロットがまだ走っていたら今回はスキップ）
exec 9>"$LOGDIR/.acquire.lock"
if ! flock -n 9; then
  echo "別の取得が実行中 → 今回はスキップ"; exit 0
fi

# 取得本体（全ソース＝zozoad含む）。idempotent なので何度走っても安全。
echo "----- 取得実行 -----"
"$ROOT/run_daily_linux.sh"
echo "----- 取得実行 done -----"

# 成功判定: 全ソースが想定ラグ内なら本日完了マーク（以降のスロットはスキップ）
source .venv/bin/activate
export GOOGLE_APPLICATION_CREDENTIALS="$ROOT/pipeline/sheets-sa-key.json"
if python pipeline/data_freshness.py --needs-acquire; then
  touch "$MARKER"
  echo "✅ 全ソース最新 → 本日完了（以降のスロットはスキップ）"
else
  echo "⚠️ まだ取得できていないソースあり → 次のスロットでリトライ"
fi
echo "===== ACQUIRE RETRY DONE $(date) ====="
