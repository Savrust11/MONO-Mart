// Vercel など「ローカルADCが無い」サーバーレス環境向け。
// 環境変数 GCP_SA_KEY（サービスアカウント鍵JSONの中身）が設定されていれば、
// 起動時に /tmp へ書き出し GOOGLE_APPLICATION_CREDENTIALS を指すようにする。
// これにより既存の new BigQuery({projectId}) / new GoogleAuth() を一切改修せず認証できる。
// ローカル（GCP_SA_KEY未設定）では何もしない＝従来通りADCで動作。
export async function register() {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return;
  const key = process.env.GCP_SA_KEY;
  if (!key) return;                                   // 未設定: 既存ADCのまま
  if (process.env.GOOGLE_APPLICATION_CREDENTIALS) return; // 既にファイル指定済み
  try {
    const fs = await import('fs');
    const os = await import('os');
    const path = await import('path');
    const p = path.join(os.tmpdir(), 'gcp-sa-key.json');
    fs.writeFileSync(p, key, { encoding: 'utf8', mode: 0o600 });
    process.env.GOOGLE_APPLICATION_CREDENTIALS = p;
  } catch (e) {
    console.error('[instrumentation] GCP鍵の書き出しに失敗:', e);
  }
}
