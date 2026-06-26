import { NextRequest, NextResponse } from 'next/server';
import { fetchPlan2, plan2ToMatrix } from '@/lib/order-plan2';
import { writeMatrixToNewSheet } from '@/lib/sheets-out';

// 顧客#9: ファイル名の日付（JST・出力日）= YYYYMMDD
const jstYmd = (): string => new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10).replace(/-/g, '');

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// 案2 を共有スプレッドシートのタブ「案2」へ出力（№13＝スプシ確定）。
//   POST /api/order-plan2/to-sheet?product_code=sc491&start=...&end=...
export async function POST(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const pc = (searchParams.get('product_code') || '').trim();
  const start = searchParams.get('start') || '';
  const end = searchParams.get('end') || '';
  // 集計不要SKU（Plan1で✔）。品番合計から除外＋SKU行も出力しない。
  const exclude = (searchParams.get('exclude') || '').split(',').map((s) => s.trim()).filter(Boolean);
  const exSet = new Set(exclude.map((s) => s.toUpperCase()));
  if (!pc) return NextResponse.json({ error: '品番を指定してください。' }, { status: 400 });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    return NextResponse.json({ error: '日付は YYYY-MM-DD 形式で指定してください。' }, { status: 400 });
  }
  if (start > end) return NextResponse.json({ error: '開始日が終了日より後です。' }, { status: 400 });

  try {
    const plan = await fetchPlan2(pc, start, end, exclude);  // 品番合計はサーバ側で除外再計算
    if (exSet.size > 0) plan.skuPivot = plan.skuPivot.filter((s) => !exSet.has((s.sku_code ?? '').toUpperCase()));
    // 顧客#8/#9/#10: 出力ごとに独立スプシを `品番-日付-連番` で新規作成
    const res = await writeMatrixToNewSheet(`${pc}-${jstYmd()}`, '推移集計', plan2ToMatrix(plan));
    return NextResponse.json({ ok: true, ...res });
  } catch (err) {
    console.error('[api/order-plan2/to-sheet] Error:', err);
    return NextResponse.json({ error: 'スプレッドシート出力に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
