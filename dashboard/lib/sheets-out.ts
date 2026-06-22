import { GoogleAuth } from 'google-auth-library';

// 出力先スプレッドシート（顧客が作成しSAに編集者共有したもの・№13＝スプシ確定）
export const SHEET_ID = process.env.SHEETS_OUTPUT_ID || '1DX9992gHjYk5FI5u2sYmPeseH7A5XeHX4z9yVxo-97Q';

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

// 2次元配列 → CSV文字列（UTF-8 BOM, Excel文字化け回避）
export function matrixToCsv(values: (string | number)[][]): string {
  const esc = (s: unknown): string => {
    const v = s == null ? '' : String(s);
    return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
  };
  return '﻿' + values.map((row) => row.map(esc).join(',')).join('\r\n') + '\r\n';
}
