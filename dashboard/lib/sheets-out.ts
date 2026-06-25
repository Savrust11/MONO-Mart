import { GoogleAuth } from 'google-auth-library';

// 出力先スプレッドシート（顧客が作成しSAに編集者共有したもの・№13＝スプシ確定）
export const SHEET_ID = process.env.SHEETS_OUTPUT_ID || '1DX9992gHjYk5FI5u2sYmPeseH7A5XeHX4z9yVxo-97Q';

// 顧客#8: 出力先フォルダ（出力ごとに独立スプシを新規作成する先）。
//   ⚠ サービスアカウントがファイルを作るには「共有ドライブ(Shared Drive)」のフォルダが必須。
//   マイドライブのフォルダは storageQuotaExceeded で失敗する。
// 出力先＝共有ドライブ「AI商品発注判断支援プロジェクト」内のフォルダ「MONO発注表出力」。
// 前提: SA(sheets-fetcher@…) がこの共有ドライブで「コンテンツ管理者」であること（顧客側で付与）。
export const OUTPUT_FOLDER_ID = process.env.SHEETS_OUTPUT_FOLDER_ID || '1PHZjJkkAtzochl9r7XWzSR9GeiYhZqaW';

async function getToken(scopes: string[]): Promise<string> {
  const auth = new GoogleAuth({ scopes });
  const client = await auth.getClient();
  const token = (await client.getAccessToken()).token;
  if (!token) throw new Error('認証トークン取得失敗');
  return token;
}

// 顧客#8 Plan B: Drive出力は「ユーザー(yujin-yamaguchi)名義」で行う。
//   SAは外部のため共有ドライブでファイル作成不可。ユーザーはコンテンツ管理者なので作成できる。
//   認証情報は gitignore の user-drive-oauth.json（または env GOOGLE_OAUTH_USER_CREDENTIALS）。
let _userTok: { token: string; exp: number } | null = null;
async function getUserDriveToken(): Promise<string> {
  if (_userTok && Date.now() < _userTok.exp) return _userTok.token;
  const path = await import('path');
  const fs = await import('fs');
  const p = process.env.GOOGLE_OAUTH_USER_CREDENTIALS || path.join(process.cwd(), 'user-drive-oauth.json');
  const c = JSON.parse(fs.readFileSync(p, 'utf8'));
  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: c.client_id, client_secret: c.client_secret,
      refresh_token: c.refresh_token, grant_type: 'refresh_token',
    }),
  });
  if (!res.ok) throw new Error(`ユーザー認証の更新に失敗 ${res.status}: ${(await res.text()).slice(0, 150)}`);
  const j = await res.json();
  _userTok = { token: j.access_token as string, exp: Date.now() + ((j.expires_in ?? 3600) - 60) * 1000 };
  return _userTok.token;
}

type WriteOpts = {
  valueInputOption?: 'RAW' | 'USER_ENTERED';
  // セル書式（背景色など）。タブの sheetId と書き込んだ values を受けて batchUpdate requests を返す。
  format?: (sheetId: number, values: (string | number)[][]) => unknown[];
};

// 2次元配列を、指定スプレッドシートの「名前付きタブ」に書き込む。
//   タブが無ければ作成 → 範囲クリア → A1 から書き込み（既定RAW）→ 任意で書式適用。
//   案1/案2/項目詳細を別タブに出すことで相互に上書きしないようにする。
export async function writeMatrixToTab(
  tab: string, values: (string | number)[][], opts: WriteOpts = {},
): Promise<{ rows: number; url: string }> {
  const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/spreadsheets'] });
  const client = await auth.getClient();
  const token = (await client.getAccessToken()).token;
  if (!token) throw new Error('認証トークン取得失敗');
  const base = `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}`;
  const hdr = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // 既存タブ一覧を取得（sheetId も取る）
  const metaRes = await fetch(`${base}?fields=sheets(properties(sheetId,title))`, { headers: hdr });
  if (!metaRes.ok) throw new Error(`メタ取得失敗 ${metaRes.status}: ${(await metaRes.text()).slice(0, 150)}`);
  const meta = await metaRes.json();
  const found = (meta.sheets || []).find((s: any) => s.properties?.title === tab);
  let sheetId: number | undefined = found?.properties?.sheetId;

  // 無ければタブ追加（既存スプレッドシートへのタブ追加はSA編集権限で可能）
  if (!found) {
    const add = await fetch(`${base}:batchUpdate`, {
      method: 'POST', headers: hdr,
      body: JSON.stringify({ requests: [{ addSheet: { properties: { title: tab } } }] }),
    });
    if (!add.ok) throw new Error(`タブ作成失敗 ${add.status}: ${(await add.text()).slice(0, 150)}`);
    const addJson = await add.json();
    sheetId = addJson.replies?.[0]?.addSheet?.properties?.sheetId;
  }

  const range = (r: string) => encodeURIComponent(`'${tab}'!${r}`);
  const clr = await fetch(`${base}/values/${range('A1:ZZ5000')}:clear`, { method: 'POST', headers: hdr });
  if (!clr.ok) throw new Error(`クリア失敗 ${clr.status}: ${(await clr.text()).slice(0, 150)}`);
  const upd = await fetch(`${base}/values/${range('A1')}?valueInputOption=${opts.valueInputOption ?? 'RAW'}`, {
    method: 'PUT', headers: hdr, body: JSON.stringify({ values }),
  });
  if (!upd.ok) throw new Error(`書込失敗 ${upd.status}: ${(await upd.text()).slice(0, 150)}`);

  // 任意：セル書式（背景色など）を適用
  if (opts.format && sheetId != null) {
    const requests = opts.format(sheetId, values);
    if (requests.length) {
      const fmt = await fetch(`${base}:batchUpdate`, {
        method: 'POST', headers: hdr, body: JSON.stringify({ requests }),
      });
      if (!fmt.ok) throw new Error(`書式適用失敗 ${fmt.status}: ${(await fmt.text()).slice(0, 150)}`);
    }
  }

  return { rows: values.length, url: `https://docs.google.com/spreadsheets/d/${SHEET_ID}/edit` };
}

// 顧客#8/#9/#10: 出力ごとに「独立した新規スプレッドシート」を OUTPUT_FOLDER_ID に作成する。
//   ファイル名 = `${baseName}-${連番}`（同名が既にあれば連番を+1。例 sc1032-20260624-1, -2…）。
//   毎回まっさらな新ファイルなので、上書き・前回の色残り・手直しの消失が起きない。
export async function writeMatrixToNewSheet(
  baseName: string, tabName: string, values: (string | number)[][], opts: WriteOpts = {},
): Promise<{ rows: number; url: string; filename: string }> {
  const token = await getUserDriveToken(); // Plan B: ユーザー名義（共有ドライブで作成可能）
  const hdr = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

  // 1) 連番を決定：フォルダ内の `baseName-数字` を走査して最大値+1
  const q = `'${OUTPUT_FOLDER_ID}' in parents and name contains '${baseName}' and trashed=false`;
  const listUrl = `https://www.googleapis.com/drive/v3/files?q=${encodeURIComponent(q)}`
    + `&fields=files(name)&pageSize=1000&supportsAllDrives=true&includeItemsFromAllDrives=true`;
  const listRes = await fetch(listUrl, { headers: hdr });
  if (!listRes.ok) throw new Error(`フォルダ照会失敗 ${listRes.status}: ${(await listRes.text()).slice(0, 200)}`);
  const listJson = await listRes.json();
  const re = new RegExp('^' + baseName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '-(\\d+)$');
  let maxN = 0;
  for (const f of (listJson.files || [])) {
    const m = re.exec(f.name || ''); if (m) maxN = Math.max(maxN, parseInt(m[1], 10));
  }
  const filename = `${baseName}-${maxN + 1}`;

  // 2) フォルダ内に空のスプレッドシートを新規作成
  const createRes = await fetch(
    'https://www.googleapis.com/drive/v3/files?supportsAllDrives=true&fields=id',
    { method: 'POST', headers: hdr, body: JSON.stringify({
        name: filename, mimeType: 'application/vnd.google-apps.spreadsheet', parents: [OUTPUT_FOLDER_ID],
      }) });
  if (!createRes.ok) {
    const body = await createRes.text();
    let hint = '';
    if (/Insufficient permissions for the specified parent/.test(body))
      hint = '【出力先の共有ドライブで SA「sheets-fetcher@mono-back-office-system.iam.gserviceaccount.com」を“コンテンツ管理者”に設定してください】';
    else if (/storageQuotaExceeded/.test(body))
      hint = '【出力先はマイドライブではなく「共有ドライブ」のフォルダにしてください】';
    throw new Error(`新規スプシ作成失敗 ${createRes.status}${hint}: ${body.slice(0, 200)}`);
  }
  const ssId = (await createRes.json()).id as string;

  // 3) 既定シートのIDを取得し、タブ名を変更（期間集計/推移集計）
  const metaRes = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${ssId}?fields=sheets(properties(sheetId,title))`, { headers: hdr });
  if (!metaRes.ok) throw new Error(`メタ取得失敗 ${metaRes.status}`);
  const sheetId = (await metaRes.json()).sheets[0].properties.sheetId as number;
  await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${ssId}:batchUpdate`, {
    method: 'POST', headers: hdr,
    body: JSON.stringify({ requests: [{ updateSheetProperties: { properties: { sheetId, title: tabName }, fields: 'title' } }] }),
  });

  // 4) 値を書き込み（A1から）
  const range = encodeURIComponent(`'${tabName}'!A1`);
  const upd = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${ssId}/values/${range}?valueInputOption=${opts.valueInputOption ?? 'RAW'}`, {
    method: 'PUT', headers: hdr, body: JSON.stringify({ values }),
  });
  if (!upd.ok) throw new Error(`書込失敗 ${upd.status}: ${(await upd.text()).slice(0, 150)}`);

  // 5) 任意：書式（色帯・ハイライト等）を適用
  if (opts.format) {
    const requests = opts.format(sheetId, values);
    if (requests.length) {
      const fmt = await fetch(`https://sheets.googleapis.com/v4/spreadsheets/${ssId}:batchUpdate`, {
        method: 'POST', headers: hdr, body: JSON.stringify({ requests }),
      });
      if (!fmt.ok) throw new Error(`書式適用失敗 ${fmt.status}: ${(await fmt.text()).slice(0, 150)}`);
    }
  }

  return { rows: values.length, url: `https://docs.google.com/spreadsheets/d/${ssId}/edit`, filename };
}

// 2次元配列 → CSV文字列（UTF-8 BOM, Excel文字化け回避）
export function matrixToCsv(values: (string | number)[][]): string {
  const esc = (s: unknown): string => {
    const v = s == null ? '' : String(s);
    return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  };
  return '﻿' + values.map((row) => row.map(esc).join(',')).join('\r\n') + '\r\n';
}
