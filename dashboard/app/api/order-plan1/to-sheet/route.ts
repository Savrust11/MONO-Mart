import { NextRequest, NextResponse } from 'next/server';
import { fetchPlan1, plan1ToMatrix } from '@/lib/order-plan';
import { buildPlan1Format } from '@/lib/plan1-sheet-format';
import { writeMatrixToNewSheet } from '@/lib/sheets-out';

// 顧客#9: ファイル名の日付（JST・出力日）= YYYYMMDD
const jstYmd = (): string => new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10).replace(/-/g, '');

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// 案1の書式は @/lib/plan1-sheet-format の buildPlan1Format を使用（統合出力と共用）。

// 案1 を共有スプレッドシートのタブ「案1」へ出力（№13＝スプシ確定）。
//   POST /api/order-plan1/to-sheet?product_code=sc491&start=...&end=...
export async function POST(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const pc = (searchParams.get('product_code') || '').trim();
  const start = searchParams.get('start') || '';
  const end = searchParams.get('end') || '';
  // 集計不要SKU（Plan1で✔）。スプシからも除外し、品番合計を再計算する。
  const exclude = new Set((searchParams.get('exclude') || '').split(',').map((s) => s.trim().toUpperCase()).filter(Boolean));
  if (!pc) return NextResponse.json({ error: '品番を指定してください。' }, { status: 400 });
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) {
    return NextResponse.json({ error: '日付は YYYY-MM-DD 形式で指定してください。' }, { status: 400 });
  }
  if (start > end) return NextResponse.json({ error: '開始日が終了日より後です。' }, { status: 400 });

  try {
    const plan = await fetchPlan1(pc, start, end);
    // 全SKUが集計不要のカラー＝「集計対象外カラー」。画像は別セクション（赤＋取消線＋赤枠）で参考表示。
    let excludedColors: Set<string> | undefined;
    if (exclude.size > 0) {
      const colors = new Set(plan.skus.map((s) => s.color_name).filter((c): c is string => !!c));
      excludedColors = new Set([...colors].filter((c) => {
        const g = plan.skus.filter((s) => s.color_name === c);
        return g.length > 0 && g.every((s) => exclude.has((s.sku_code ?? '').toUpperCase()));
      }));
      // 集計不要SKUを除外し、品番合計（粗利率/値引率/上代/枚数）を有効SKUで再計算（画面と一致）。
      const active = plan.skus.filter((s) => !exclude.has((s.sku_code ?? '').toUpperCase()));
      const rev = active.reduce((a, s) => a + (s.period_rev || 0), 0);
      const cost = active.reduce((a, s) => a + (s.period_cost || 0), 0);
      const lst = active.reduce((a, s) => a + (s.period_lst || 0), 0);
      const qty = active.reduce((a, s) => a + (s.sales_qty || 0), 0);
      plan.skus = active;
      plan.header = {
        ...plan.header,
        total_margin_pct: rev > 0 ? Math.round((rev - cost) / rev * 1000) / 10 : null,
        total_discount_pct: lst > 0 ? Math.round((1 - rev / lst) * 1000) / 10 : null,
        total_list_amount: lst,
        total_qty: qty,
      };
    }
    const matrix = plan1ToMatrix(plan, excludedColors);
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
