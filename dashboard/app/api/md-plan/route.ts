import { NextRequest, NextResponse } from 'next/server';
import { BigQuery } from '@google-cloud/bigquery';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

// MD計画・提案: ブランド(ショップ)別に、直近90日の受注実績をBigQueryから集計して返す。
//   従来はハードコードのサンプルだったが、本APIで「最新データ」連携にする（顧客要望2026）。
//   ・KPI: 売上金額 / 型数(品番数) / 値引率 / 販売数
//   ・カテゴリ別: 売上・数量・型数・値引率＋売上ベースのMDスコア（最大=100）＋強化/維持/見直し判定
//   ・売れ筋ランキング: 品番別 売上上位
const PROJECT = 'mono-back-office-system';
const A = `${PROJECT}.analytics_layer`;
const LOCATION = 'asia-northeast1';

let _bq: BigQuery | null = null;
const bq = () => (_bq ??= new BigQuery({ projectId: PROJECT }));

const num = (x: unknown): number => Number((x as { value?: unknown })?.value ?? x ?? 0) || 0;

export async function GET(req: NextRequest) {
  const brand = (new URL(req.url).searchParams.get('brand') || '').trim();
  if (!brand) return NextResponse.json({ error: 'brand を指定してください。' }, { status: 400 });

  const q = async (sql: string, params: Record<string, unknown>) => {
    const [rows] = await bq().query({ query: sql, params, location: LOCATION });
    return rows as Record<string, unknown>[];
  };

  try {
    // 共通CTE: 基準日=最新受注日、直近90日、ブランド(shop_name)で絞り、商品タイプ親(parent_item_type)を
    //   品番単位に重複排除して結合（SKU水増し防止）。カテゴリ=parent_item_type（受注で100%充足）。
    const COMMON = `WITH asof AS (SELECT MAX(sale_date) d FROM \`${A}.sales_daily\` WHERE source_file='orders'),
      pm AS (SELECT UPPER(TRIM(product_code)) pc, ANY_VALUE(parent_item_type) cat
             FROM \`${A}.product_master\` GROUP BY pc),
      f AS (
        SELECT s.product_code pc, s.sales_amount amt, s.sales_quantity q, s.proper_price pp, pm.cat
        FROM \`${A}.sales_daily\` s
        LEFT JOIN pm ON pm.pc=UPPER(TRIM(s.product_code))
        WHERE s.source_file='orders' AND UPPER(TRIM(s.shop_name))=UPPER(TRIM(@brand))
          AND s.sale_date BETWEEN DATE_SUB((SELECT d FROM asof), INTERVAL 89 DAY) AND (SELECT d FROM asof))`;

    const [kpiRows, catRows, rankRows, asofRow] = await Promise.all([
      q(`${COMMON}
         SELECT SUM(amt) sales, COUNT(DISTINCT pc) types, SUM(q) qty, SUM(pp*q) list FROM f`, { brand }),
      q(`${COMMON}
         SELECT COALESCE(cat,'(未分類)') cat, SUM(amt) sales, SUM(q) qty,
                COUNT(DISTINCT pc) types, SUM(pp*q) list
         FROM f GROUP BY cat ORDER BY sales DESC`, { brand }),
      // 売れ筋: f(品番別)で集計→名称は重複排除した品番マスタから付与（SKU水増しなし）。
      q(`${COMMON},
         nm AS (SELECT UPPER(TRIM(product_code)) pc, ANY_VALUE(product_name) nm
                FROM \`${A}.product_master\` GROUP BY pc)
         SELECT f.pc pc, ANY_VALUE(nm.nm) nm, ANY_VALUE(f.cat) cat, SUM(f.amt) sales, SUM(f.q) qty
         FROM f LEFT JOIN nm ON nm.pc=UPPER(TRIM(f.pc))
         GROUP BY f.pc ORDER BY sales DESC LIMIT 20`, { brand }),
      q(`SELECT CAST(MAX(sale_date) AS STRING) d FROM \`${A}.sales_daily\` WHERE source_file='orders'`, {}),
    ]);

    const k = kpiRows[0] ?? {};
    const sales = num(k.sales), list = num(k.list);
    const kpi = {
      sales, types: num(k.types), qty: num(k.qty),
      discount_pct: list > 0 ? Math.round((1 - sales / list) * 1000) / 10 : null,
    };

    // カテゴリMDスコア: 売上を最大100に正規化（売上が大きいほど高スコア）。
    const maxSales = Math.max(1, ...catRows.map((r) => num(r.sales)));
    const categories = catRows.map((r) => {
      const cs = num(r.sales), cl = num(r.list);
      const score = Math.round((cs / maxSales) * 1000) / 10;
      const disc = cl > 0 ? Math.round((1 - cs / cl) * 1000) / 10 : null;
      // 強化推奨=スコア上位(>=50) / 見直し=値引率が高い(>=40%) / それ以外=維持
      const label = score >= 50 ? '強化推奨' : (disc != null && disc >= 40 ? '見直し' : '維持');
      return { name: String(r.cat), sales: cs, qty: num(r.qty), types: num(r.types), discount_pct: disc, score, label };
    });

    const ranking = rankRows.map((r) => ({
      product_code: String(r.pc), product_name: (r.nm as string) ?? null,
      category: (r.cat as string) ?? null, sales: num(r.sales), qty: num(r.qty),
    }));

    return NextResponse.json({
      brand, asof: (asofRow[0]?.d as string) ?? null,
      period_days: 90, kpi, categories, ranking,
    });
  } catch (err) {
    console.error('[api/md-plan] Error:', err);
    return NextResponse.json({ error: 'MD計画の集計に失敗しました: ' + String(err).slice(0, 200) }, { status: 500 });
  }
}
