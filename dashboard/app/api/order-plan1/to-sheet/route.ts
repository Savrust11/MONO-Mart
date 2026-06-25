import { NextRequest, NextResponse } from 'next/server';
import { fetchPlan1, plan1ToMatrix, PLAN1_GROUP_MARK, PLAN1_TABLE_COLS } from '@/lib/order-plan';
import { writeMatrixToNewSheet } from '@/lib/sheets-out';

// 顧客#9: ファイル名の日付（JST・出力日）= YYYYMMDD
const jstYmd = (): string => new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10).replace(/-/g, '');

export const dynamic = 'force-dynamic';
export const revalidate = 0;

type RGB = { red: number; green: number; blue: number };
const C = {
  gray:   { red: 0.95, green: 0.95, blue: 0.95 },
  sky:    { red: 0.85, green: 0.93, blue: 0.99 },
  teal:   { red: 0.85, green: 0.96, blue: 0.93 },
  violet: { red: 0.93, green: 0.90, blue: 0.98 },
  amber:  { red: 1.00, green: 0.96, blue: 0.85 },
  pink:   { red: 0.99, green: 0.85, blue: 0.90 },
  cyan:   { red: 0.82, green: 0.98, blue: 0.98 },
  hdr:    { red: 0.93, green: 0.93, blue: 0.93 },
};
const bgReq = (sheetId: number, r0: number, r1: number, c0: number, c1: number, bg: RGB, bold = false) => ({
  repeatCell: {
    range: { sheetId, startRowIndex: r0, endRowIndex: r1, startColumnIndex: c0, endColumnIndex: c1 },
    cell: { userEnteredFormat: { backgroundColor: bg, textFormat: { bold } } },
    fields: 'userEnteredFormat(backgroundColor,textFormat)',
  },
});

// 案1の書式（顧客スプシ画像に一致）：画像セルのサムネイル表示・グループ見出しの色帯・推奨/確定発注数のハイライト
function buildPlan1Format(sheetId: number, values: (string | number)[][]): unknown[] {
  const reqs: unknown[] = [];

  // 画像（=IMAGE）セルがある行を高く＋画像列(H〜L)を広く＝サムネイル表示
  const imgRows: number[] = [];
  values.forEach((row, ri) => {
    if (row.some((c) => typeof c === 'string' && c.startsWith('=IMAGE'))) imgRows.push(ri);
  });
  for (const ri of imgRows) {
    reqs.push({ updateDimensionProperties: {
      range: { sheetId, dimension: 'ROWS', startIndex: ri, endIndex: ri + 1 },
      properties: { pixelSize: 96 }, fields: 'pixelSize' } });
  }
  if (imgRows.length) {
    reqs.push({ updateDimensionProperties: {
      range: { sheetId, dimension: 'COLUMNS', startIndex: 7, endIndex: 12 },
      properties: { pixelSize: 96 }, fields: 'pixelSize' } });
  }

  // テーブルの色帯・ハイライト
  const g = values.findIndex((row) => row[0] === PLAN1_GROUP_MARK); // グループ見出し行
  if (g >= 0) {
    const h = g + 1; // 列見出し行
    const N = PLAN1_TABLE_COLS;
    reqs.push(
      bgReq(sheetId, g, g + 1, 0, 15, C.gray, true),
      bgReq(sheetId, g, g + 1, 15, 19, C.sky, true),
      bgReq(sheetId, g, g + 1, 19, 23, C.teal, true),
      bgReq(sheetId, g, g + 1, 23, 26, C.violet, true),
      bgReq(sheetId, g, g + 1, 26, N, C.amber, true),
      bgReq(sheetId, h, h + 1, 0, N, C.hdr, true),
      bgReq(sheetId, h, values.length, 13, 14, C.pink),
      bgReq(sheetId, h, values.length, 14, 15, C.cyan),
    );

    // 顧客#11: 数値書式・整列をダッシュボードに合わせる（データ行＝列見出しの次〜末尾）
    const d0 = h + 1, d1 = values.length;
    const numFmt = (c0: number, c1: number, pattern: string, type = 'NUMBER') => ({
      repeatCell: {
        range: { sheetId, startRowIndex: d0, endRowIndex: d1, startColumnIndex: c0, endColumnIndex: c1 },
        cell: { userEnteredFormat: { numberFormat: { type, pattern } } },
        fields: 'userEnteredFormat.numberFormat',
      },
    });
    const align = (c0: number, c1: number, a: 'LEFT' | 'RIGHT') => ({
      repeatCell: {
        range: { sheetId, startRowIndex: d0, endRowIndex: d1, startColumnIndex: c0, endColumnIndex: c1 },
        cell: { userEnteredFormat: { horizontalAlignment: a } },
        fields: 'userEnteredFormat.horizontalAlignment',
      },
    });
    // 桁区切り（上代/原価/枚数/在庫/入荷数など）
    for (const c of [3, 5, 6, 9, 10, 12, 13, 14, 15, 19, 23, 25, 27, 29, 31]) reqs.push(numFmt(c, c + 1, '#,##0'));
    // 日販（小数1桁）
    for (const c of [16, 20]) reqs.push(numFmt(c, c + 1, '#,##0.0'));
    // 在庫日数（〇日）
    for (const c of [17, 21, 24]) reqs.push(numFmt(c, c + 1, '0"日"'));
    // FKU枚数構成（〇%）
    reqs.push(numFmt(7, 8, '0%', 'PERCENT'));
    // 日付（yyyy-mm-dd）
    for (const c of [8, 11, 18, 22, 26, 28, 30]) reqs.push(numFmt(c, c + 1, 'yyyy-mm-dd', 'DATE'));
    // 整列：文字列＝左、数値＝右、日付＝左（ダッシュボードと同じ）
    reqs.push(align(0, 3, 'LEFT'), align(4, 5, 'LEFT'), align(3, 4, 'RIGHT'), align(5, N, 'RIGHT'));
    for (const c of [8, 11, 18, 22, 26, 28, 30]) reqs.push(align(c, c + 1, 'LEFT'));

    // ヘッダ「合計」値セル（B列）: 粗利率/値引率=〇.〇%、上代額=〇円、枚数=桁区切り
    const hdrFmt = (row: number, pattern: string, type = 'NUMBER') => ({
      repeatCell: {
        range: { sheetId, startRowIndex: row, endRowIndex: row + 1, startColumnIndex: 1, endColumnIndex: 2 },
        cell: { userEnteredFormat: { numberFormat: { type, pattern } } },
        fields: 'userEnteredFormat.numberFormat',
      },
    });
    reqs.push(hdrFmt(12, '0.0%', 'PERCENT'), hdrFmt(13, '0.0%', 'PERCENT'), hdrFmt(14, '#,##0"円"'), hdrFmt(15, '#,##0'));
  }
  return reqs;
}

// 案1 を共有スプレッドシートのタブ「案1」へ出力（№13＝スプシ確定）。
//   POST /api/order-plan1/to-sheet?product_code=sc491&start=...&end=...
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
    const plan = await fetchPlan1(pc, start, end);
    const matrix = plan1ToMatrix(plan);
    // 顧客#8/#9/#10: 出力ごとに独立スプシを `品番-日付-連番` で新規作成（上書き・色残り解消）
    // =IMAGE / %表示のため USER_ENTERED、書式（色帯・ハイライト）も適用
    const res = await writeMatrixToNewSheet(`${pc}-${jstYmd()}`, '期間集計', matrix, {
      valueInputOption: 'USER_ENTERED',
      format: buildPlan1Format,
    });
    return NextResponse.json({ ok: true, ...res });
  } catch (err) {
    console.error('[api/order-plan1/to-sheet] Error:', err);
    return NextResponse.json({ error: 'スプレッドシート出力に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
