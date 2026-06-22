import { NextRequest, NextResponse } from 'next/server';
import { GoogleAuth } from 'google-auth-library';
import { fetchPeriodReport } from '@/lib/order-report';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// 出力先スプレッドシート（顧客が作成しSAに編集者共有したもの）
const SHEET_ID = process.env.SHEETS_OUTPUT_ID || '1DX9992gHjYk5FI5u2sYmPeseH7A5XeHX4z9yVxo-97Q';

// ② スプシ出力：品番×期間の発注管理表を、共有Googleスプレッドシートに書き込む。
//   POST /api/period-report/to-sheet?product_code=sc1032&start=2026-05-01&end=2026-05-31
export async function POST(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const pc = (searchParams.get('product_code') || '').trim();
  const start = searchParams.get('start') || '';
  const end = searchParams.get('end') || '';

  if (!pc) return NextResponse.json({ error: '品番を指定してください。' }, { status: 400 });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    return NextResponse.json({ error: '日付は YYYY-MM-DD 形式で指定してください。' }, { status: 400 });
  }
  if (start > end) return NextResponse.json({ error: '開始日が終了日より後です。' }, { status: 400 });

  try {
    const rows = await fetchPeriodReport(pc, start, end);

    // rows → 2D values（CSVと同じ 区分/項目/値/備考）
    const values: (string | number)[][] = [
      ['発注管理表（項目詳細）', `品番=${pc}`, `期間=${start}〜${end}`, ''],
      ['区分', '項目', '値', '備考'],
    ];
    let section = '';
    for (const r of rows) {
      if (r.kind === 'title' || r.kind === 'blank') continue;
      if (r.kind === 'sec') { section = r.label; continue; }
      values.push([section, r.label, r.value == null ? '' : String(r.value), r.note]);
    }

    // Sheets REST を SA トークンで叩く
    const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/spreadsheets'] });
    const client = await auth.getClient();
    const token = (await client.getAccessToken()).token;
    if (!token) throw new Error('認証トークン取得失敗');
    const base = `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}`;
    const hdr = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };

    // 先頭タブをクリア → 書き込み
    const clr = await fetch(`${base}/values/A1%3AZ3000:clear`, { method: 'POST', headers: hdr });
    if (!clr.ok) throw new Error(`clear失敗 ${clr.status}: ${(await clr.text()).slice(0, 150)}`);
    const upd = await fetch(`${base}/values/A1?valueInputOption=RAW`, {
      method: 'PUT', headers: hdr, body: JSON.stringify({ values }),
    });
    if (!upd.ok) throw new Error(`書込失敗 ${upd.status}: ${(await upd.text()).slice(0, 150)}`);

    return NextResponse.json({
      ok: true,
      rows: values.length,
      url: `https://docs.google.com/spreadsheets/d/${SHEET_ID}/edit`,
    });
  } catch (err) {
    console.error('[api/period-report/to-sheet] Error:', err);
    return NextResponse.json(
      { error: 'スプレッドシートへの書き込みに失敗しました: ' + String(err).slice(0, 200) },
      { status: 500 },
    );
  }
}
