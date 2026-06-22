import { NextRequest, NextResponse } from 'next/server';
import { fetchPlan2, plan2ToMatrix } from '@/lib/order-plan2';
import { writeMatrixToTab } from '@/lib/sheets-out';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// 案2 を共有スプレッドシートのタブ「案2」へ出力（№13＝スプシ確定）。
//   POST /api/order-plan2/to-sheet?product_code=sc491&start=...&end=...
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
    const plan = await fetchPlan2(pc, start, end);
    const res = await writeMatrixToTab('案2', plan2ToMatrix(plan));
    return NextResponse.json({ ok: true, ...res });
  } catch (err) {
    console.error('[api/order-plan2/to-sheet] Error:', err);
    return NextResponse.json({ error: 'スプレッドシート出力に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
