// 案1（期間集計）スプレッドシートの書式。order-plan1/to-sheet と 統合出力(order-plan/to-sheet)で共用。
import { PLAN1_GROUP_MARK, PLAN1_TABLE_COLS, PLAN1_EXCLUDED_MARK } from '@/lib/order-plan';

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

export function buildPlan1Format(sheetId: number, values: (string | number)[][]): unknown[] {
  const reqs: unknown[] = [];

  // 画像（=IMAGE）セルがある行だけを高くしてサムネイル表示。
  const imgRows: number[] = [];
  values.forEach((row, ri) => {
    if (row.some((c) => typeof c === 'string' && c.startsWith('=IMAGE'))) imgRows.push(ri);
  });
  for (const ri of imgRows) {
    reqs.push({ updateDimensionProperties: {
      range: { sheetId, dimension: 'ROWS', startIndex: ri, endIndex: ri + 1 },
      properties: { pixelSize: 96 }, fields: 'pixelSize' } });
  }

  // 集計対象外カラー: 名前セルを赤＋取消線に、直上の画像セルを赤枠で囲む。
  const red = { red: 0.86, green: 0.15, blue: 0.15 };
  values.forEach((row, ri) => {
    row.forEach((c, ci) => {
      if (typeof c === 'string' && c.endsWith(PLAN1_EXCLUDED_MARK)) {
        reqs.push({ repeatCell: {
          range: { sheetId, startRowIndex: ri, endRowIndex: ri + 1, startColumnIndex: ci, endColumnIndex: ci + 1 },
          cell: { userEnteredFormat: { textFormat: { foregroundColor: red, strikethrough: true, bold: true } } },
          fields: 'userEnteredFormat.textFormat' } });
        if (ri > 0) reqs.push({ updateBorders: {
          range: { sheetId, startRowIndex: ri - 1, endRowIndex: ri, startColumnIndex: ci, endColumnIndex: ci + 1 },
          top: { style: 'SOLID_THICK', color: red }, bottom: { style: 'SOLID_THICK', color: red },
          left: { style: 'SOLID_THICK', color: red }, right: { style: 'SOLID_THICK', color: red } } });
      }
    });
  });

  // テーブルの色帯・ハイライト
  const g = values.findIndex((row) => row[0] === PLAN1_GROUP_MARK);
  if (g >= 0) {
    const h = g + 1;
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
    for (const c of [3, 5, 6, 9, 10, 12, 13, 14, 15, 19, 23, 25, 27, 29, 31]) reqs.push(numFmt(c, c + 1, '#,##0'));
    for (const c of [16, 20]) reqs.push(numFmt(c, c + 1, '#,##0.0'));   // 日販（小数1桁）
    for (const c of [17, 21, 24]) reqs.push(numFmt(c, c + 1, '0"日"')); // 在庫日数（整数・〇日）
    reqs.push(numFmt(7, 8, '0%', 'PERCENT'));
    for (const c of [8, 11, 18, 22, 26, 28, 30]) reqs.push(numFmt(c, c + 1, 'yyyy-mm-dd', 'DATE'));
    reqs.push(align(0, 3, 'LEFT'), align(4, 5, 'LEFT'), align(3, 4, 'RIGHT'), align(5, N, 'RIGHT'));
    for (const c of [8, 11, 18, 22, 26, 28, 30]) reqs.push(align(c, c + 1, 'LEFT'));

    // ヘッダ「合計」値セル（B列）: 粗利率/値引率=〇.〇%、販売額=〇円、枚数=桁区切り（データ基準日で1行ずれ → 13-16）
    const hdrFmt = (row: number, pattern: string, type = 'NUMBER') => ({
      repeatCell: {
        range: { sheetId, startRowIndex: row, endRowIndex: row + 1, startColumnIndex: 1, endColumnIndex: 2 },
        cell: { userEnteredFormat: { numberFormat: { type, pattern } } },
        fields: 'userEnteredFormat.numberFormat',
      },
    });
    reqs.push(hdrFmt(13, '0.0%', 'PERCENT'), hdrFmt(14, '0.0%', 'PERCENT'), hdrFmt(15, '#,##0"円"'), hdrFmt(16, '#,##0'));
  }
  return reqs;
}
