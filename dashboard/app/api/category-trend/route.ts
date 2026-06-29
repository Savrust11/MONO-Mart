import { NextRequest, NextResponse } from 'next/server';
import { BigQuery } from '@google-cloud/bigquery';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// 顧客要望2026: カテゴリ別52週トレンド。商品タイプ親/子を選び、週次の売上・点数を
//   2025 vs 2026 で比較してグラフ表示。ピーク週/推移を直感的に見て、発注・販促タイミングの
//   参考にする。基準週比%（後述）はフロント側で算出。
//   ※ TOP10ランキングは不要との指定のため含めない。
const PROJECT = 'mono-back-office-system';
const A = `${PROJECT}.analytics_layer`;
const LOCATION = 'asia-northeast1';

let _bq: BigQuery | null = null;
const bq = () => (_bq ??= new BigQuery({ projectId: PROJECT }));
const num = (x: unknown): number => Number((x as { value?: unknown })?.value ?? x ?? 0) || 0;

export async function GET(req: NextRequest) {
  const sp = new URL(req.url).searchParams;
  const parent = (sp.get('parent') || '').trim();
  const child = (sp.get('child') || '').trim();   // 空＝親の全子を合算

  const q = async (sql: string, params: Record<string, unknown>) => {
    const [rows] = await bq().query({ query: sql, params, location: LOCATION });
    return rows as Record<string, unknown>[];
  };

  try {
    // 商品タイプ 親→子 の選択肢（product_master）
    const optRows = await q(
      `SELECT parent_item_type p, child_item_type c
       FROM \`${A}.product_master\`
       WHERE parent_item_type IS NOT NULL AND parent_item_type!=''
         AND child_item_type IS NOT NULL AND child_item_type!=''
       GROUP BY p, c ORDER BY p, c`, {});
    const optMap = new Map<string, string[]>();
    for (const r of optRows) {
      const p = String(r.p); const c = String(r.c);
      if (!optMap.has(p)) optMap.set(p, []);
      optMap.get(p)!.push(c);
    }
    const options = [...optMap.entries()].map(([p, children]) => ({ parent: p, children }));

    // 親が未指定なら選択肢だけ返す（初回ロード用）
    if (!parent) return NextResponse.json({ options, parent: '', child: '', weeks: [] });

    // 週次トレンド（ISO週 × ISO年）。親（＋任意で子）で絞る。
    const childCond = child ? 'AND pm.c=@child' : '';
    const rows = await q(
      `WITH pm AS (SELECT UPPER(TRIM(product_code)) pc, ANY_VALUE(parent_item_type) p, ANY_VALUE(child_item_type) c
                   FROM \`${A}.product_master\` GROUP BY pc)
       SELECT EXTRACT(ISOWEEK FROM s.sale_date) wk, EXTRACT(ISOYEAR FROM s.sale_date) yr,
              SUM(s.sales_amount) amt, SUM(s.sales_quantity) qty
       FROM \`${A}.sales_daily\` s JOIN pm ON pm.pc=UPPER(TRIM(s.product_code))
       WHERE s.source_file='orders' AND pm.p=@parent ${childCond}
         AND EXTRACT(ISOWEEK FROM s.sale_date) BETWEEN 1 AND 53
       GROUP BY wk, yr`,
      child ? { parent, child } : { parent });

    // 週(1..53)にピボット
    const wk: Record<number, { wk: number; amt2025: number; qty2025: number; amt2026: number; qty2026: number }> = {};
    for (let w = 1; w <= 53; w++) wk[w] = { wk: w, amt2025: 0, qty2025: 0, amt2026: 0, qty2026: 0 };
    for (const r of rows) {
      const w = num(r.wk); const yr = num(r.yr);
      if (!wk[w]) continue;
      if (yr === 2025) { wk[w].amt2025 = num(r.amt); wk[w].qty2025 = num(r.qty); }
      else if (yr === 2026) { wk[w].amt2026 = num(r.amt); wk[w].qty2026 = num(r.qty); }
    }
    // 末尾の全ゼロ週を落とす（最大53週だが実データのある範囲まで）
    const weeks = Object.values(wk).filter((x) => x.wk <= 52 || x.amt2025 || x.amt2026);

    return NextResponse.json({ options, parent, child, weeks });
  } catch (err) {
    console.error('[api/category-trend] Error:', err);
    return NextResponse.json({ error: 'カテゴリ別トレンドの集計に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
