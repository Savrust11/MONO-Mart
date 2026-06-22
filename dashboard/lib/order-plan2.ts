import { BigQuery } from '@google-cloud/bigquery';

/**
 * 発注管理表「案2」= 品番 × 指定期間 の 時系列ピボット。
 *   上段: 11指標（UU/CVR/お気に率/CP対象枚数比/粗利率/値引率/平均売価/合計販売数/
 *         予約販売数割合/入荷数量/在庫）を 月次 と 日次 で表示。
 *   下段: SKU(カラー×サイズ) × 日付 の販売数ピボット。
 *
 * 仕様の出所: data/tab1.xlsx「発注管理表 案2」「発注管理表項目詳細 ②内訳」。
 * 比率系（粗利率/値引率/CVR/お気に率/CP/予約割合）は日次の率を平均せず、
 * バケット内の分子・分母を合計してから割る（数量重み付き＝正しい集計）。
 *
 * ⚠ 月次と日次のレンジ: スプシ例は月次=長期/日次=短期と別レンジだが定義が曖昧。
 *    v1 は両方とも指定期間[start,end]で算出する（顧客確認事項）。
 */

const PROJECT = process.env.GCP_PROJECT_ID || 'mono-back-office-system';
const DS = process.env.BQ_DATASET_ANALYTICS ?? 'analytics_layer';
const LOC = process.env.BQ_LOCATION ?? 'asia-northeast1';

let _bq: BigQuery | null = null;
const bq = () => (_bq ??= new BigQuery({ projectId: PROJECT }));
const T = (n: string) => `\`${PROJECT}.${DS}.${n}\``;
async function q(sql: string, params: Record<string, unknown>): Promise<any[]> {
  const [rows] = await bq().query({ query: sql, params, location: LOC });
  return rows;
}
const num = (x: unknown): number => Number((x as any)?.value ?? x ?? 0) || 0;
const dstr = (x: any): string | null => (x == null ? null : (x.value ?? String(x)));
function addDays(iso: string, n: number): string {
  const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export type MetricFormat = 'int' | 'yen' | 'pct';
export interface Plan2Metric {
  key: string; label: string; format: MetricFormat;
  monthly: (number | null)[]; daily: (number | null)[];
}
export interface Plan2SkuRow {
  color_name: string | null; size: string | null; sku_code: string | null;
  daily: number[]; monthly: number[];
}
export interface Plan2 {
  product_code: string; start: string; end: string;
  months: string[]; days: string[];
  metrics: Plan2Metric[];
  skuPivot: Plan2SkuRow[];
  note: string;
}

// 案2 → 2次元配列（CSV/スプシ共通シリアライズ）
export function plan2ToMatrix(p: Plan2): (string | number)[][] {
  const m: (string | number)[][] = [];
  const v = (x: number | null) => (x == null ? '' : x);
  m.push(['発注管理表 案2', `品番=${p.product_code}`, `期間=${p.start}〜${p.end}`]);
  m.push([]);
  m.push(['【月次】指標', ...p.months]);
  for (const mt of p.metrics) m.push([mt.label, ...mt.monthly.map(v)]);
  m.push([]);
  m.push(['【日次】指標', ...p.days]);
  for (const mt of p.metrics) m.push([mt.label, ...mt.daily.map(v)]);
  m.push([]);
  m.push(['【SKU×日付 販売数】']);
  m.push(['カラー', 'サイズ', 'SKU品番', ...p.days]);
  for (const s of p.skuPivot) m.push([s.color_name ?? '', s.size ?? '', s.sku_code ?? '', ...s.daily]);
  return m;
}

// 期間内の日付・月を列挙
function enumDays(start: string, end: string): string[] {
  const out: string[] = []; let d = start;
  for (let i = 0; i < 800 && d <= end; i++) { out.push(d); d = addDays(d, 1); }
  return out;
}
function enumMonths(days: string[]): string[] {
  const set = new Set<string>(); for (const d of days) set.add(d.slice(0, 7));
  return [...set].sort();
}
// end の月から monthsBack ヶ月さかのぼった月初を返す（#6 月次レンジ用）。
function monthStartIso(end: string, monthsBack: number): string {
  const [y, m] = end.split('-').map(Number);
  return new Date(Date.UTC(y, (m - 1) - (monthsBack - 1), 1)).toISOString().slice(0, 10);
}

export async function fetchPlan2(pc: string, start: string, end: string): Promise<Plan2> {
  // #6 月次/日次は別レンジ（顧客スプシ準拠）: 月次=長期・日次=短期。
  //    既定 月次=直近MONTHLY_MONTHSヶ月 / 日次=直近DAILY_DAYS日（end起点）。正式な遡及幅は顧客確認後に調整。
  const MONTHLY_MONTHS = 12, DAILY_DAYS = 31;
  const dailyStart = addDays(end, -(DAILY_DAYS - 1));
  const monthlyStart = monthStartIso(end, MONTHLY_MONTHS);
  const fetchStart = monthlyStart < dailyStart ? monthlyStart : dailyStart; // 取得は広い方（=月次）に合わせる
  const allDays = enumDays(fetchStart, end);   // 取得・月次集計の母集合
  const days = enumDays(dailyStart, end);      // 日次の表示列（短期）
  const months = enumMonths(allDays);          // 月次の表示列（長期）

  const [ordRows, uuRows, costRows, incRows, stkRows, cdaysRows, exclRows, pivRows] = await Promise.all([
    // 日次 受注（販売数/売上/上代/予約販売数）
    q(`SELECT CAST(sale_date AS STRING) d, SUM(sales_quantity) qty, SUM(sales_amount) rev,
         SUM(proper_price*sales_quantity) lst, SUM(IF(sale_type LIKE '%予約%', sales_quantity, 0)) yqty
       FROM ${T('sales_daily')} WHERE product_code=@pc AND source_file='orders'
         AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) GROUP BY d`, { pc, sd: fetchStart, ed: end }),
    // 日次 UU/お気に入り（商品別実績(新)＝source_file 指定なしで合算）
    q(`SELECT CAST(sale_date AS STRING) d, SUM(unique_visitors) uu, SUM(favorites) fav
       FROM ${T('sales_daily')} WHERE product_code=@pc
         AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) GROUP BY d`, { pc, sd: fetchStart, ed: end }),
    // 日次 原価（粗利率用）: SKU別販売×最新評価額
    q(`WITH s AS (SELECT CAST(sale_date AS STRING) d, UPPER(TRIM(sku_code)) sk, SUM(sales_quantity) qty
                  FROM ${T('sales_daily')} WHERE product_code=@pc AND source_file='orders'
                    AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) GROUP BY d, sk),
            c AS (SELECT UPPER(TRIM(sku_code)) sk, ANY_VALUE(valuation_price) vp FROM ${T('cost_master')}
                  WHERE product_code=@pc GROUP BY sk)
       SELECT s.d, SUM(s.qty*COALESCE(c.vp,0)) cost FROM s LEFT JOIN c ON c.sk=s.sk GROUP BY s.d`,
      { pc, sd: fetchStart, ed: end }),
    // 入荷数量（着日別・最新スナップショット）
    q(`SELECT CAST(SAFE_CAST(REPLACE(earliest_arrival_date,'/','-') AS DATE) AS STRING) d, SUM(incoming_qty) q
       FROM ${T('incoming_stock')} WHERE product_code=@pc AND earliest_arrival_date IS NOT NULL
         AND source_date=(SELECT MAX(source_date) FROM ${T('incoming_stock')} WHERE product_code=@pc)
       GROUP BY d HAVING d IS NOT NULL`, { pc }),
    // 在庫（当時・日次スナップショット）
    q(`SELECT CAST(snapshot_date AS STRING) d, SUM(available_qty) s FROM ${T('stock_analysis')}
       WHERE product_code=@pc AND snapshot_date BETWEEN DATE(@sd) AND DATE(@ed) GROUP BY d`,
      { pc, sd: fetchStart, ed: end }),
    // クーポン実施日（ショップ単位）
    q(`SELECT DISTINCT CAST(exclusion_date AS STRING) d FROM ${T('coupon_exclusion')}
       WHERE brand_name=(SELECT ANY_VALUE(shop_name) FROM ${T('product_master')}
                         WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)))`, { pc }),
    // クーポン除外日（この品番）
    q(`SELECT DISTINCT CAST(exclusion_date AS STRING) d FROM ${T('coupon_exclusion')}
       WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))`, { pc }),
    // SKU × 日付 販売数ピボット
    q(`SELECT UPPER(TRIM(sku_code)) sk, ANY_VALUE(color_name) cn, ANY_VALUE(size) sz,
         CAST(sale_date AS STRING) d, SUM(sales_quantity) q
       FROM ${T('sales_daily')} WHERE product_code=@pc AND source_file='orders'
         AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) AND sales_quantity>0
       GROUP BY sk, d`, { pc, sd: fetchStart, ed: end }),
  ]);

  // 日次マップ化
  const mapBy = (rows: any[], f: (r: any) => any) => {
    const o: Record<string, any> = {}; for (const r of rows) o[dstr(r.d) ?? ''] = f(r); return o;
  };
  const ord = mapBy(ordRows, (r) => ({ qty: num(r.qty), rev: num(r.rev), lst: num(r.lst), yqty: num(r.yqty) }));
  const uu = mapBy(uuRows, (r) => ({ uu: num(r.uu), fav: num(r.fav) }));
  const cost = mapBy(costRows, (r) => num(r.cost));
  const inc = mapBy(incRows, (r) => num(r.q));
  const stk = mapBy(stkRows, (r) => num(r.s));
  const cdays = new Set(cdaysRows.map((r) => dstr(r.d)));
  const excl = new Set(exclRows.map((r) => dstr(r.d)));

  // 日次の成分（分子分母）
  type Comp = { qty: number; rev: number; lst: number; cost: number; uu: number; fav: number; yqty: number; cp: number; inc: number; stk: number | null };
  const comp: Record<string, Comp> = {};
  for (const d of allDays) {
    const o = ord[d] ?? { qty: 0, rev: 0, lst: 0, yqty: 0 };
    const u = uu[d] ?? { uu: 0, fav: 0 };
    const isCP = cdays.has(d) && !excl.has(d);
    comp[d] = {
      qty: o.qty, rev: o.rev, lst: o.lst, cost: cost[d] ?? 0, uu: u.uu, fav: u.fav, yqty: o.yqty,
      cp: isCP ? o.qty : 0, inc: inc[d] ?? 0, stk: d in stk ? stk[d] : null,
    };
  }

  // 集約ヘルパ（バケット内の成分合計から比率系を導出）
  const sum = (ds: string[], pick: (c: Comp) => number) => ds.reduce((a, d) => a + pick(comp[d]), 0);
  const lastStock = (ds: string[]): number | null => {
    for (let i = ds.length - 1; i >= 0; i--) { const s = comp[ds[i]].stk; if (s != null) return s; }
    return null;
  };
  const pct = (n: number, d: number) => (d ? Math.round((n / d) * 1000) / 10 : null);
  const r1 = (x: number) => Math.round(x * 10) / 10;

  const metricDefs: { key: string; label: string; format: MetricFormat; calc: (ds: string[]) => number | null }[] = [
    { key: 'uu', label: 'UU', format: 'int', calc: (ds) => sum(ds, (c) => c.uu) || null },
    { key: 'cvr', label: 'CVR', format: 'pct', calc: (ds) => pct(sum(ds, (c) => c.qty), sum(ds, (c) => c.uu)) },
    { key: 'fav_rate', label: 'お気に率', format: 'pct', calc: (ds) => pct(sum(ds, (c) => c.fav), sum(ds, (c) => c.uu)) },
    { key: 'cp_rate', label: 'CP対象枚数比', format: 'pct', calc: (ds) => pct(sum(ds, (c) => c.cp), sum(ds, (c) => c.qty)) },
    { key: 'margin', label: '粗利率', format: 'pct', calc: (ds) => { const r = sum(ds, (c) => c.rev); return r ? r1((r - sum(ds, (c) => c.cost)) / r * 100) : null; } },
    { key: 'discount', label: '値引率', format: 'pct', calc: (ds) => { const l = sum(ds, (c) => c.lst); return l ? r1((1 - sum(ds, (c) => c.rev) / l) * 100) : null; } },
    { key: 'avg_price', label: '平均売価', format: 'yen', calc: (ds) => { const qd = sum(ds, (c) => c.qty); return qd ? Math.round(sum(ds, (c) => c.rev) / qd) : null; } },
    { key: 'total_qty', label: '合計販売数', format: 'int', calc: (ds) => sum(ds, (c) => c.qty) || null },
    { key: 'yoyaku_rate', label: '予約販売数割合', format: 'pct', calc: (ds) => pct(sum(ds, (c) => c.yqty), sum(ds, (c) => c.qty)) },
    { key: 'incoming', label: '入荷数量', format: 'int', calc: (ds) => sum(ds, (c) => c.inc) || null },
    { key: 'stock', label: '在庫', format: 'int', calc: (ds) => lastStock(ds) },
  ];

  const daysByMonth: Record<string, string[]> = {};
  for (const d of allDays) (daysByMonth[d.slice(0, 7)] ??= []).push(d);

  const metrics: Plan2Metric[] = metricDefs.map((m) => ({
    key: m.key, label: m.label, format: m.format,
    monthly: months.map((mm) => m.calc(daysByMonth[mm] ?? [])),
    daily: days.map((d) => m.calc([d])),
  }));

  // SKU × 日付 ピボット
  const skuMap: Record<string, { cn: string | null; sz: string | null; byDay: Record<string, number> }> = {};
  for (const r of pivRows) {
    const sk = r.sk as string;
    (skuMap[sk] ??= { cn: r.cn ?? null, sz: r.sz ?? null, byDay: {} }).byDay[dstr(r.d) ?? ''] = num(r.q);
  }
  const skuPivot: Plan2SkuRow[] = Object.entries(skuMap)
    .map(([sk, v]) => ({
      color_name: v.cn, size: v.sz, sku_code: sk,
      daily: days.map((d) => v.byDay[d] ?? 0),
      monthly: months.map((mm) => (daysByMonth[mm] ?? []).reduce((a, d) => a + (v.byDay[d] ?? 0), 0)),
    }))
    .sort((a, b) => (a.color_name ?? '').localeCompare(b.color_name ?? '') || (a.size ?? '').localeCompare(b.size ?? ''));

  return {
    product_code: pc, start: fetchStart, end, months, days, metrics, skuPivot,
    note: `月次=直近${months.length}ヶ月 / 日次=直近${days.length}日（別レンジ）`,
  };
}
