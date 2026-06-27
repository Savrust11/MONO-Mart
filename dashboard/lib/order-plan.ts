import { BigQuery } from '@google-cloud/bigquery';

/**
 * 発注管理表「案1」= 品番 × 指定期間 の SKU別 発注管理表（明細ビュー）。
 *
 * 仕様の出所: data/tab1.xlsx「発注管理表 案1」「発注管理表項目詳細」「社内で決めること」。
 * 計算ルールは確定事項（№1 在庫=S列/予約0, №2 販売開始日=期間内初回受注日,
 * №3 フリー在庫, №11 お気に入り=在庫分析daily, №12 最終入荷日除外3条件）に準拠。
 *
 * ⚠ 推奨発注数(R35) の式はスプシ未定義（項目詳細 B35 の計算欄が空白）。
 *    現状は Phase1 暫定式を用い、recommended_provisional=true で UI に明示する。
 *    顧客確定後に差し替える。
 */

const PROJECT = process.env.GCP_PROJECT_ID || 'mono-back-office-system';
const DS = process.env.BQ_DATASET_ANALYTICS ?? 'analytics_layer';
const LOC = process.env.BQ_LOCATION ?? 'asia-northeast1';
const WIN_SHORT = 7;
const WIN_LONG = 30;
const COVERAGE_WEEKS = 8; // Phase1 暫定（推奨発注数用）

let _bq: BigQuery | null = null;
const bq = () => (_bq ??= new BigQuery({ projectId: PROJECT }));
const T = (n: string) => `\`${PROJECT}.${DS}.${n}\``;
async function q(sql: string, params: Record<string, unknown>): Promise<any[]> {
  const [rows] = await bq().query({ query: sql, params, location: LOC });
  return rows;
}
const num = (x: unknown): number => Number((x as any)?.value ?? x ?? 0) || 0;
const r1 = (x: number) => Math.round(x * 10) / 10;
// 顧客No.5 (2026-06-24 山口): 着荷が asof から N日より先の入荷予定は「将来の発注」と
// みなし、フリー在庫に含めない（過大計上＝過小発注の防止）。着荷日なし・期日超過(過去日)は含める。
const FUTURE_ARRIVAL_CUTOFF_DAYS = 180;
const r2 = (x: number) => Math.round(x * 100) / 100;
const dval = (x: any): string | null => (x == null ? null : (x.value ?? String(x)));
function median(a: number[]): number {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
function addDays(iso: string, n: number): string {
  const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
}

export interface Plan1Sku {
  color_name: string | null;
  size: string | null;
  sku_code: string | null;
  retail_price: number | null;       // 上代
  sale_type: string | null;          // 販売タイプ
  favorites: number | null;          // お気に入り
  sales_qty: number;                 // 販売数（指定期間）
  period_rev: number;                // 期間売上（顧客#1: 集計対象外SKUを引いた合計再計算用）
  period_cost: number;               // 期間原価（PF優先, 同上）
  period_lst: number;                // 期間上代額（同上）
  fku_share: number | null;          // FKU枚数構成（品番&カラー）
  last_order_date: string | null;    // 前回発注日
  last_cost: number | null;          // 前回原価
  latest_avg_cost: number | null;    // 最新加重平均原価
  last_arrival_date: string | null;  // 最終入荷日
  current_stock: number;             // 現在庫数（予約は0）
  recommended_qty: number | null;    // 推奨発注数（暫定式）
  corrected_velo: number;            // 欠品補正された日販（実数 or シミュ）
  velo_basis: 'actual' | 'simulated'; // 補正日販が実数か推定か（色分け用）
  recommended_provisional: boolean;
  confirmed_qty: null;               // 確定発注数（入力欄・空白）
  // 直近7日
  s7_qty: number; s7_daily_avg: number | null; s7_stock_days: number | null; s7_sellout: string | null;
  // 直近30日
  l30_qty: number; l30_daily_median: number | null; l30_stock_days: number | null; l30_sellout: string | null;
  // フリー在庫
  free_stock: number; free_stock_days: number | null; reserved_pending: number;
  // 入荷山（品番単位・全SKU共通）
  arr1_date: string | null; arr1_qty: number | null;
  arr2_date: string | null; arr2_qty: number | null;
  arr3_date: string | null; arr3_qty: number | null;
}

// サイズの並び順（小→大）。文字サイズは規定順、数値サイズ(36/90等)は数値昇順、
// フリー/不明は末尾。client 2026: 「サイズは小さいサイズから昇順」。
const _SIZE_ORDER = ['XXS', 'XS', 'SS', 'S', 'M', 'L', 'LL', 'XL', '2L',
                     'XXL', '3L', 'XXXL', '4L', '5L', '6L'];
export function sizeRank(sz: string | null | undefined): number {
  if (sz == null || String(sz).trim() === '') return 99999;
  const s = String(sz).trim().toUpperCase();
  const idx = _SIZE_ORDER.indexOf(s);
  if (idx >= 0) return idx;                                   // 規定の文字サイズ
  if (/^\d+(\.\d+)?$/.test(s)) return 1000 + parseFloat(s);   // 数値サイズ昇順
  if (s === 'F' || s === 'FREE' || s.includes('フリー')) return 5000;
  return 8000;                                                // 未知サイズは末尾寄り
}

export interface Plan1Image { color: string; url: string; }
export interface Plan1 {
  images: Plan1Image[];   // 商品画像（カラー別）R02
  header: {
    created_at: string; data_asof: string; start: string; end: string;
    product_code: string; product_name: string | null; shop: string | null;
    brand: string | null; item_type_parent: string | null; item_type_child: string | null;
    review_count: number | null; review_avg: number | null;
    total_margin_pct: number | null; total_discount_pct: number | null;
    total_list_amount: number | null; total_revenue: number | null; total_qty: number;
  };
  skus: Plan1Sku[];
}

export async function fetchPlan1(pc: string, start: string, end: string,
  cutoffDays: number = FUTURE_ARRIVAL_CUTOFF_DAYS): Promise<Plan1> {
  const today = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);  // JST当日
  const asofRow = (await q(
    `SELECT LEAST(@t, CAST(MAX(sale_date) AS STRING)) d FROM ${T('sales_daily')} WHERE source_file='orders'`,
    { t: today },
  ))[0];
  const asof: string = dval(asofRow?.d) ?? today;
  const dl30 = addDays(asof, -(WIN_LONG - 1));

  // 品番のケースを保存通りに正規化。在庫/入荷/予約系クエリは product_code=@pc（ケース依存）
  // のため、入力ケースが違うと在庫=0になる不具合を防ぐ（販売系は UPPER(TRIM) 済み）。
  const canonRow = (await q(
    `SELECT ANY_VALUE(product_code) p FROM ${T('product_master')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))`,
    { pc }))[0];
  if (canonRow?.p) pc = canonRow.p;

  // ── 販売開始日（確定№2）: 期間内初回受注日 ──
  const sd0 = (await q(
    `SELECT MIN(sale_date) d FROM ${T('sales_daily')} WHERE product_code=@pc AND source_file='orders'
       AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) AND sales_quantity>0`, { pc, sd: start, ed: end },
  ))[0];
  const saleStart = dval(sd0?.d);
  let elapsed = WIN_SHORT;
  if (saleStart) elapsed = Math.min(WIN_SHORT, daysBetween(saleStart, asof) + 1);
  elapsed = Math.max(1, elapsed);

  // ── 並行取得 ──
  const [
    skuMaster, periodSales, colorSales, stockRows, dailySku, dailyStk,
    arrRows, lastOrd, costRows, sitRows, resvRows, incRemain, arrivals, header, imgRows, pfRows,
    seasonalRows, elapsedRows, firstSaleRows, colorOrderRows,
  ] = await Promise.all([
    // SKUマスタ（product_master 起点で全登録SKU）
    q(`SELECT UPPER(TRIM(sku_code)) sk, ANY_VALUE(color_name) color_name, ANY_VALUE(size) size,
         ANY_VALUE(proper_price) retail, ANY_VALUE(sale_type) sale_type
       FROM ${T('product_master')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) GROUP BY sk`, { pc }),
    // 期間販売（SKU別）
    q(`SELECT UPPER(TRIM(sku_code)) sk, SUM(sales_quantity) qty, SUM(sales_amount) rev,
         SUM(proper_price*sales_quantity) lst, ANY_VALUE(color_name) cn, ANY_VALUE(size) sz
       FROM ${T('sales_daily')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND source_file='orders'
         AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) GROUP BY sk`, { pc, sd: start, ed: end }),
    // カラー別販売（FKU枚数構成用・品番&カラー）
    q(`SELECT color_name, SUM(sales_quantity) qty FROM ${T('sales_daily')}
       WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND source_file='orders'
         AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) GROUP BY color_name`, { pc, sd: start, ed: end }),
    // 最新スナップショット（現在庫=予約0, お気に入り）確定№1/№11
    q(`WITH pm AS (SELECT UPPER(TRIM(sku_code)) sk, ANY_VALUE(sale_type) stype
                   FROM ${T('product_master')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) GROUP BY sk),
            latest AS (SELECT MAX(snapshot_date) d FROM ${T('stock_analysis')}
                       WHERE product_code=@pc AND snapshot_date<=DATE(@asof))
       SELECT UPPER(TRIM(sa.sku_code)) sk,
         SUM(CASE WHEN pm.stype LIKE '%予約%' THEN 0 ELSE sa.available_qty END) cur,
         SUM(sa.favorites) fav
       FROM ${T('stock_analysis')} sa LEFT JOIN pm ON pm.sk=UPPER(TRIM(sa.sku_code))
       WHERE sa.product_code=@pc AND sa.snapshot_date=(SELECT d FROM latest) GROUP BY sk`, { pc, asof }),
    // 日次SKU販売（30日窓）→ 7日/30日 集計・中央値。qn=予約を除く通常販売（欠品補正の7日平均用）
    q(`SELECT UPPER(TRIM(sku_code)) sk, CAST(sale_date AS STRING) d, SUM(sales_quantity) q,
         SUM(IF(sale_type LIKE '%予約%', 0, sales_quantity)) qn
       FROM ${T('sales_daily')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND source_file='orders'
         AND sale_date BETWEEN DATE(@dl) AND DATE(@asof) GROUP BY sk,d`, { pc, dl: dl30, asof }),
    // 日次SKU在庫（30日窓）→ 中央値ルール
    q(`SELECT UPPER(TRIM(sku_code)) sk, CAST(snapshot_date AS STRING) d, SUM(available_qty) s
       FROM ${T('stock_analysis')} WHERE product_code=@pc
         AND snapshot_date BETWEEN DATE(@dl) AND DATE(@asof) GROUP BY sk,d`, { pc, dl: dl30, asof }),
    // 最終入荷日（除外3条件・確定№12）SKU別
    q(`SELECT UPPER(TRIM(sku_code)) sk, MAX(arrival_date) d FROM ${T('inventory_snapshot')}
       WHERE product_code=@pc AND delivery_note_no IS NOT NULL AND delivery_note_no!=''
         AND NOT STARTS_WITH(delivery_note_no,'_') AND NOT REGEXP_CONTAINS(delivery_note_no,'-SAI-')
       GROUP BY sk`, { pc }),
    // 前回発注日・前回原価（MMS発注書一覧, 作成日以前の最新）SKU別
    q(`WITH r AS (SELECT UPPER(TRIM(sku_code)) sk, order_date od, unit_price up,
                    ROW_NUMBER() OVER (PARTITION BY UPPER(TRIM(sku_code)) ORDER BY order_date DESC) rn
                  FROM ${T('mms_orders')} WHERE product_code=@pc AND order_date<=DATE(@asof))
       SELECT sk, CAST(od AS STRING) od, up FROM r WHERE rn=1`, { pc, asof }),
    // 最新加重平均原価（MMS評価額一覧 最新評価額）SKU別
    q(`WITH r AS (SELECT UPPER(TRIM(sku_code)) sk, valuation_price vp,
                    ROW_NUMBER() OVER (PARTITION BY UPPER(TRIM(sku_code)) ORDER BY source_date DESC) rn
                  FROM ${T('cost_master')} WHERE product_code=@pc)
       SELECT sk, vp FROM r WHERE rn=1`, { pc }),
    // sitateru 確定卸値（品番単位）— 前回原価のフォールバック用（MMS発注単価が0/無い時）。最も網羅的(約8割)。
    q(`SELECT ANY_VALUE(confirmed_wholesale_price) cw FROM ${T('sitateru_item_master')}
       WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND confirmed_wholesale_price>0`, { pc }),
    // 予約未処理数（最新 reservation_date・SKUで合計）SKU別
    q(`WITH latest AS (SELECT MAX(reservation_date) d FROM ${T('reservations')} WHERE product_code=@pc)
       SELECT UPPER(TRIM(sku_code)) sk, SUM(quantity) q FROM ${T('reservations')}
       WHERE product_code=@pc AND reservation_date=(SELECT d FROM latest) GROUP BY sk`, { pc }),
    // 入荷残（最新 source_date）SKU別 → フリー在庫
    // 顧客No.5: 着荷 > asof+N日 の入荷予定は将来発注扱いで除外（日付なし・期日超過は含める）
    // incoming_stock.sku_code は「品番＋SKU」連結（例 BLEsh1667F10181pf）。商品マスタは「F10181pf」。
    // 先頭の品番接頭辞を除去してSKUに揃えてから集計（揃えないと入荷残がフリー在庫に乗らない不具合）。
    q(`WITH latest AS (SELECT MAX(source_date) d FROM ${T('incoming_stock')} WHERE product_code=@pc)
       SELECT UPPER(TRIM(
                CASE WHEN STARTS_WITH(UPPER(TRIM(sku_code)), UPPER(TRIM(product_code)))
                     THEN SUBSTR(TRIM(sku_code), LENGTH(TRIM(product_code)) + 1)
                     ELSE sku_code END)) sk,
              SUM(incoming_qty) q FROM ${T('incoming_stock')}
       WHERE product_code=@pc AND source_date=(SELECT d FROM latest)
         AND (earliest_arrival_date IS NULL
              OR SAFE_CAST(REPLACE(earliest_arrival_date,'/','-') AS DATE)
                 <= DATE_ADD(DATE(@asof), INTERVAL ${cutoffDays} DAY))
       GROUP BY sk`, { pc, asof }),
    // 入荷残（SKU別×着荷日）。顧客指摘: 従来は品番合計を全SKUに同数表示していた→SKU別に修正。
    //   sku_code は「品番+SKU」連結なので接頭辞を除去。フリー在庫と整合するよう N日カットオフを適用。
    q(`SELECT UPPER(TRIM(
                CASE WHEN STARTS_WITH(UPPER(TRIM(sku_code)), UPPER(TRIM(product_code)))
                     THEN SUBSTR(TRIM(sku_code), LENGTH(TRIM(product_code)) + 1)
                     ELSE sku_code END)) sk,
              SAFE_CAST(REPLACE(earliest_arrival_date,'/','-') AS DATE) d, SUM(incoming_qty) q
       FROM ${T('incoming_stock')} WHERE product_code=@pc AND earliest_arrival_date IS NOT NULL
         AND source_date=(SELECT MAX(source_date) FROM ${T('incoming_stock')} WHERE product_code=@pc)
       GROUP BY sk, d
       HAVING d IS NOT NULL AND d <= DATE_ADD(DATE(@asof), INTERVAL ${cutoffDays} DAY)
       ORDER BY sk, d`, { pc, asof }),
    // ヘッダ用 品番属性・レビュー・合計粗利率/値引率
    fetchHeader(pc, start, end, asof),
    // 商品画像（カラー別）R02: color_master のカラーID → o.imgz.jp URL
    q(`WITH pm AS (SELECT DISTINCT color_name, item_code FROM ${T('product_master')}
                   WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))
                     AND color_name IS NOT NULL AND item_code IS NOT NULL)
       SELECT pm.color_name cn, ANY_VALUE(pm.item_code) ic, ANY_VALUE(cm.color_id) cid
       FROM pm LEFT JOIN ${T('color_master')} cm ON TRIM(cm.color_name)=TRIM(pm.color_name)
       GROUP BY pm.color_name`, { pc }),
    // PF原価（品番単位・粗利率の原価優先元）— 顧客No.7。per-SKU原価＝PF優先→MMS の算出用
    q(`SELECT ANY_VALUE(cost_price) val FROM ${T('pf_fee_master')}
       WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))
         AND snapshot_date=(SELECT MAX(snapshot_date) FROM ${T('pf_fee_master')}) AND cost_price>0`, { pc }),
    // 季節係数（この品番の gender×商品タイプ子の52週）— 欠品補正の「知りたい週÷実績週」用
    q(`WITH a AS (SELECT ANY_VALUE(gender) g, ANY_VALUE(child_item_type) ct
                  FROM ${T('product_master')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)))
       SELECT sc.week_number wk, sc.coefficient c FROM ${T('seasonal_coefficients')} sc, a
       WHERE sc.gender=a.g AND sc.child_item_type=a.ct`, { pc }),
    // 経過係数（このブランドのリリース経過日カーブ）— 7日実績が無い新商品のフォールバック用
    q(`WITH a AS (SELECT parent_category brand FROM ${T('sales_daily')}
                  WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND parent_category IS NOT NULL
                    AND parent_category NOT LIKE '%限定%' ORDER BY sale_date DESC LIMIT 1)
       SELECT ec.days_since_release d, ec.coefficient c FROM ${T('elapsed_coefficients')} ec, a
       WHERE ec.brand=a.brand`, { pc }),
    // 初回受注日（リリース日）SKU別 — リリース経過日数の算出用
    q(`SELECT UPPER(TRIM(sku_code)) sk, CAST(MIN(sale_date) AS STRING) d
       FROM ${T('sales_daily')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND source_file='orders'
       GROUP BY sk`, { pc }),
    // ZOZOBOのカラー並び順: カラー系の順（系の最小color_id順）＋ 同系内はカラーコード(color_id)昇順。
    q(`WITH catord AS (SELECT color_category, MIN(SAFE_CAST(color_id AS INT64)) cat_min
                       FROM ${T('color_master')} GROUP BY color_category),
            colr AS (SELECT TRIM(color_name) cn, ANY_VALUE(color_category) cat, MIN(SAFE_CAST(color_id AS INT64)) cid
                     FROM ${T('color_master')} GROUP BY cn)
       SELECT colr.cn, ROW_NUMBER() OVER (ORDER BY catord.cat_min, colr.cid) rank
       FROM colr JOIN catord ON catord.color_category=colr.cat`, {}),
  ]);
  const pfCost = pfRows[0]?.val == null ? null : num(pfRows[0].val);
  // 前回原価フォールバック用: sitateru確定卸値（品番単位）。
  const sitWholesale = sitRows[0]?.cw == null ? null : num(sitRows[0].cw);
  // カラー名→ZOZOBO並び順位（未登録色は末尾）
  const colorRank: Record<string, number> = {};
  for (const r of colorOrderRows) colorRank[String(r.cn)] = Number(r.rank);
  const crank = (c: string | null | undefined): number => colorRank[(c ?? '').trim()] ?? 999999;

  // ── 欠品補正の係数マップ ──
  const seasonalByWeek: Record<number, number> = {};
  for (const r of seasonalRows) seasonalByWeek[Number(r.wk)] = num(r.c);
  const elapsedByDay: Record<number, number> = {};
  for (const r of elapsedRows) elapsedByDay[Number(r.d)] = num(r.c);
  const firstSaleMap: Record<string, string | null> = {};
  for (const r of firstSaleRows) firstSaleMap[r.sk] = dval(r.d);
  const isoWeek = (iso: string): number => {  // ISO週番号（1..53）
    const dt = new Date(iso + 'T00:00:00Z');
    const day = (dt.getUTCDay() + 6) % 7;
    dt.setUTCDate(dt.getUTCDate() - day + 3);
    const firstTh = new Date(Date.UTC(dt.getUTCFullYear(), 0, 4));
    const fday = (firstTh.getUTCDay() + 6) % 7;
    firstTh.setUTCDate(firstTh.getUTCDate() - fday + 3);
    return 1 + Math.round((dt.getTime() - firstTh.getTime()) / 604800000);
  };
  // 実績週=asofの週、知りたい週=発注がカバーする先 COVERAGE_WEEKS 週の平均。比率=知りたい/実績。
  const wkClamp = (w: number) => ((w - 1) % 52) + 1;
  const refWeek = wkClamp(isoWeek(asof));
  const seasonalRef = seasonalByWeek[refWeek] || null;
  let seasonalTgt: number | null = null;
  {
    const ws: number[] = [];
    for (let i = 1; i <= COVERAGE_WEEKS; i++) { const c = seasonalByWeek[wkClamp(refWeek + i)]; if (c) ws.push(c); }
    if (ws.length) seasonalTgt = ws.reduce((a, b) => a + b, 0) / ws.length;
  }
  // 季節比率（知りたい週÷実績週）。両週の係数が揃わない時は補正なし=1.0。
  const seasonalRatio = (seasonalRef && seasonalTgt) ? seasonalTgt / seasonalRef : 1.0;

  // 商品画像（カラー別）
  const images: Plan1Image[] = imgRows
    .filter((r) => r.ic && r.cid)
    .map((r) => ({
      color: String(r.cn),
      url: `https://o.imgz.jp/${String(r.ic).slice(-3)}/${r.ic}/${r.ic}b_${r.cid}_d.jpg`,
    }))
    .sort((a, b) => crank(a.color) - crank(b.color) || a.color.localeCompare(b.color, 'ja'));  // 画像も左からZOZOBO順

  // ── マップ化 ──
  const m = <V>(rows: any[], val: (r: any) => V) => {
    const o: Record<string, V> = {}; for (const r of rows) o[r.sk] = val(r); return o;
  };
  const psMap = m(periodSales, (r) => ({ qty: num(r.qty), rev: num(r.rev), lst: num(r.lst), cn: r.cn, sz: r.sz }));
  const stMap = m(stockRows, (r) => ({ cur: num(r.cur), fav: num(r.fav) }));
  const arrMap = m(arrRows, (r) => dval(r.d));
  const ordMap = m(lastOrd, (r) => ({ od: dval(r.od), up: r.up == null ? null : num(r.up) }));
  const costMap = m(costRows, (r) => (r.vp == null ? null : num(r.vp)));
  const resvMap = m(resvRows, (r) => num(r.q));
  const incMap = m(incRemain, (r) => num(r.q));

  // 日次（SKU×日）→ 辞書。dskNorm=予約を除く通常販売（欠品補正の7日平均用）
  const dsk: Record<string, Record<string, number>> = {};
  const dskNorm: Record<string, Record<string, number>> = {};
  for (const r of dailySku) { (dsk[r.sk] ??= {})[r.d] = num(r.q); (dskNorm[r.sk] ??= {})[r.d] = num(r.qn); }
  const dst: Record<string, Record<string, number>> = {};
  for (const r of dailyStk) (dst[r.sk] ??= {})[r.d] = num(r.s);

  // カラー別合計・品番合計（FKU構成）
  const colorTotal: Record<string, number> = {};
  for (const r of colorSales) colorTotal[r.color_name ?? ''] = num(r.qty);
  const productTotalQty = Object.values(colorTotal).reduce((a, b) => a + b, 0);

  // 入荷山（共通）
  // 入荷残をSKU別に整理（着荷日昇順）。各SKUは自分の入荷分だけを持つ。
  const arrBySku: Record<string, { d: string | null; q: number }[]> = {};
  for (const r of arrivals) (arrBySku[r.sk] ??= []).push({ d: dval(r.d), q: num(r.q) });

  const daysS = Array.from({ length: WIN_SHORT }, (_, i) => addDays(asof, -i));
  const daysL = Array.from({ length: WIN_LONG }, (_, i) => addDays(asof, -i));

  const skus: Plan1Sku[] = skuMaster.map((sm: any) => {
    const sk = sm.sk as string;
    const ps = psMap[sk];
    const st = stMap[sk] ?? { cur: 0, fav: 0 };
    const cur = st.cur;
    const salesQty = ps?.qty ?? 0;
    const color = sm.color_name ?? ps?.cn ?? null;
    // 顧客#1: 集計対象外SKUを引いた合計を再計算するための per-SKU 期間値（原価はPF優先→MMS）
    const unitCost = pfCost ?? costMap[sk] ?? null;
    const periodRev = ps?.rev ?? 0;
    const periodLst = ps?.lst ?? 0;
    const periodCost = unitCost == null ? 0 : salesQty * unitCost;

    // FKU枚数構成（品番&カラー）= カラー合計 ÷ 品番合計
    const fku = productTotalQty ? r2((colorTotal[color ?? ''] ?? 0) / productTotalQty) : null;

    // 直近7日
    const s7Qty = daysS.reduce((a, d) => a + (dsk[sk]?.[d] ?? 0), 0);
    const s7Avg = r2(s7Qty / elapsed);
    const s7Days = s7Avg ? r1(cur / s7Avg) : null;
    const s7Sellout = s7Days == null ? null : addDays(asof, Math.round(s7Days));

    // 直近30日（中央値: 受注>0→値, 在庫>0&受注0→0, それ以外除外）
    const l30Qty = daysL.reduce((a, d) => a + (dsk[sk]?.[d] ?? 0), 0);
    const valsL: number[] = [];
    for (const d of daysL) {
      const qd = dsk[sk]?.[d] ?? 0;
      if (qd > 0) { valsL.push(qd); continue; }
      const s = dst[sk]?.[d]; if (s && s > 0) valsL.push(0);
    }
    const l30Med = valsL.length ? r2(median(valsL)) : null;
    const l30Days = l30Med ? r1(cur / l30Med) : null;
    const l30Sellout = l30Days == null ? null : addDays(asof, Math.round(l30Days));

    // フリー在庫（確定№3）= 現在庫(予約0) + 入荷残 - 予約未処理
    const reserved = resvMap[sk] ?? 0;
    const incoming = incMap[sk] ?? 0;
    const free = cur + incoming - reserved;
    const velo30 = l30Qty / WIN_LONG;
    const freeDays = velo30 ? r1(free / velo30) : null;

    // ── 欠品補正された日販（顧客・欠品補正仕様）──
    //  実数: 「予約になる前の通常販売」7日平均（在庫があった日のみ＝欠品日を除外）× 季節係数(知りたい週÷実績週)
    //  シミュ: 7日実績が無ければ ブランド経過係数で定常日販を推定 × 季節係数
    const norm7Days = daysS.filter((d) => (dst[sk]?.[d] ?? 0) > 0);          // 在庫があった日のみ
    const norm7Sum = norm7Days.reduce((a, d) => a + (dskNorm[sk]?.[d] ?? 0), 0);
    const l30NormQty = daysL.reduce((a, d) => a + (dskNorm[sk]?.[d] ?? 0), 0); // 30日の通常販売累計
    let correctedVelo: number;
    let veloBasis: 'actual' | 'simulated';
    if (norm7Days.length > 0 && l30NormQty > 0) {
      // 実数ベース: 欠品日を除いた通常販売の日販 × 季節比率
      correctedVelo = (norm7Sum / norm7Days.length) * seasonalRatio;
      veloBasis = 'actual';
    } else {
      // シミュレーション: 経過係数で定常日販を推定（累計 ÷ 経過日までの係数和）× 季節比率
      const fs = firstSaleMap[sk];
      const dSince = fs ? Math.max(1, daysBetween(fs, asof) + 1) : null;
      let steady = velo30; // フォールバック（経過係数が無い場合）
      if (dSince) {
        let sumCoef = 0;
        for (let k = 1; k <= Math.min(dSince, WIN_LONG); k++) sumCoef += elapsedByDay[k] ?? 0;
        if (sumCoef > 0) steady = l30NormQty / sumCoef;
      }
      correctedVelo = steady * seasonalRatio;
      veloBasis = 'simulated';
    }

    // 推奨発注数 = MAX(0, CEIL(8週×7日×補正日販 − フリー在庫))。補正日販は欠品/季節を考慮。
    const recommended = Math.max(0, Math.ceil(COVERAGE_WEEKS * 7 * correctedVelo - free));

    return {
      color_name: color, size: sm.size ?? ps?.sz ?? null, sku_code: sk === '' ? null : sk,
      retail_price: sm.retail == null ? null : num(sm.retail),
      sale_type: sm.sale_type ?? null,
      favorites: st.fav, sales_qty: salesQty,
      period_rev: periodRev, period_cost: periodCost, period_lst: periodLst, fku_share: fku,
      last_order_date: ordMap[sk]?.od ?? null,
      // 前回原価: MMS発注単価(>0)優先 → sitateru確定卸値 → MMS評価額(最新加重平均) でフォールバック（顧客2026）。
      last_cost: (ordMap[sk]?.up && ordMap[sk]!.up! > 0) ? ordMap[sk]!.up : (sitWholesale ?? costMap[sk] ?? null),
      latest_avg_cost: costMap[sk] ?? null, last_arrival_date: arrMap[sk] ?? null,
      current_stock: cur, recommended_qty: recommended, recommended_provisional: true,
      corrected_velo: r2(correctedVelo), velo_basis: veloBasis, confirmed_qty: null,
      s7_qty: s7Qty, s7_daily_avg: s7Avg, s7_stock_days: s7Days, s7_sellout: s7Sellout,
      l30_qty: l30Qty, l30_daily_median: l30Med, l30_stock_days: l30Days, l30_sellout: l30Sellout,
      free_stock: free, free_stock_days: freeDays, reserved_pending: reserved,
      arr1_date: arrBySku[sk]?.[0]?.d ?? null, arr1_qty: arrBySku[sk]?.[0]?.q ?? null,
      arr2_date: arrBySku[sk]?.[1]?.d ?? null, arr2_qty: arrBySku[sk]?.[1]?.q ?? null,
      arr3_date: arrBySku[sk]?.[2]?.d ?? null, arr3_qty: arrBySku[sk]?.[2]?.q ?? null,
    };
  });

  // カラーは ZOZOBO 順（カラー系順＋カラーコード昇順）でまとめ、各カラー内はサイズ昇順（小→大）。
  // client 2026: 「カラーの順番はZOZOBOと同じに、サイズは小さいサイズから昇順」。
  skus.sort((a, b) =>
    crank(a.color_name) - crank(b.color_name)
    || (a.color_name ?? '').localeCompare(b.color_name ?? '', 'ja')
    || sizeRank(a.size) - sizeRank(b.size)
    || (a.size ?? '').localeCompare(b.size ?? '', 'ja'));

  return {
    images,
    header: { created_at: today, data_asof: asof, start, end, product_code: pc, ...header },
    skus,
  };
}

// 案1 列定義（顧客スプシ「案1」シートの書式に一致）。テーブル幅＝32列。
export const PLAN1_TABLE_COLS = 32;
// グループ見出しの開始列（各ブロックの先頭）と表示名
export const PLAN1_GROUPS: { col: number; label: string }[] = [
  { col: 0, label: '▼指定期間合計' },
  { col: 15, label: '▼直近7日' },
  { col: 19, label: '▼直近30日' },
  { col: 23, label: 'フリー在庫・予約' },
  { col: 26, label: '入荷残' },
];
export const PLAN1_GROUP_MARK = '▼指定期間合計'; // テーブル先頭行の検出用

// 案1 → 2次元配列（顧客スプシ案1シートと同じ書式：ヘッダ縦並び→画像→グループ見出し→列見出し→データ）。
//   ※ =IMAGE / %表示のため、書き込みは USER_ENTERED で行うこと。
// 集計対象外カラー名のサフィックス（書式関数が赤＋取消線＋赤枠の判定に使う）。
export const PLAN1_EXCLUDED_MARK = '（集計対象外）';

export function plan1ToMatrix(p: Plan1, excludedColors?: Set<string>): (string | number)[][] {
  const h = p.header;
  const v = (x: unknown): string | number => (x == null ? '' : (x as string | number));
  const pctv = (x: number | null | undefined) => (x == null ? '' : `${x}%`);
  const fkuv = (x: number | null | undefined) => (x == null ? '' : `${Math.round(x * 100)}%`);
  // ── ① ヘッダ（label/value 縦並び：左ブロック）──
  const head: (string | number)[][] = [
    ['発注管理表 期間集計'],
    ['作成日', v(h.created_at)],
    ['データ基準日', v(h.data_asof)],
    ['集計開始日', v(h.start)],
    ['集計終了日', v(h.end)],
    ['品番', v(h.product_code)],
    ['商品名', v(h.product_name)],
    ['ショップ', v(h.shop)],
    ['ブランド', v(h.brand)],
    ['商品タイプ親', v(h.item_type_parent)],
    ['商品タイプ子', v(h.item_type_child)],
    ['累計レビュー件数', v(h.review_count)],
    ['累計レビュー点数', v(h.review_avg)],
    ['合計粗利率', pctv(h.total_margin_pct)],
    ['合計値引率', pctv(h.total_discount_pct)],
    ['合計販売額', v(h.total_revenue)],
    ['合計枚数', h.total_qty],
  ];
  const m: (string | number)[][] = [...head];

  // ── ② 商品画像（カラー別）：ヘッダ（作成日/品番/商品名…）の「下」に独立した行で配置 ──
  //   顧客要望(2026): 画像を日付・品番・商品名と同じ行に置くと、画像の高さでそれらの行まで
  //   高くなってしまう。ダッシュボードのように「画像だけの行」にして、ヘッダ行の高さに影響させない。
  //   集計対象外カラーは別セクション「集計対象外（参考）」に分け、名前に印を付ける（書式で赤＋取消線＋赤枠）。
  //   インライン表示は =IMAGE が唯一の手段（初回「アクセスを許可」が必要・Google仕様）。
  const PER_ROW = 5;
  const pushImageBands = (imgs: Plan1Image[], mark: boolean) => {
    for (let band = 0; band * PER_ROW < imgs.length; band++) {
      const imgRow: (string | number)[] = [];
      const nameRow: (string | number)[] = [];
      for (let k = 0; k < PER_ROW; k++) {
        const im = imgs[band * PER_ROW + k];
        imgRow[k] = im ? `=IMAGE("${im.url}")` : '';
        nameRow[k] = im ? (mark ? `${im.color}${PLAN1_EXCLUDED_MARK}` : im.color) : '';
      }
      m.push(imgRow);                            // 画像だけの行（=IMAGE）
      m.push(nameRow);                           // カラー名の行（画像の下）
    }
  };
  const activeImgs = excludedColors ? p.images.filter((im) => !excludedColors.has(im.color)) : p.images;
  const excludedImgs = excludedColors ? p.images.filter((im) => excludedColors.has(im.color)) : [];
  if (activeImgs.length) {
    m.push([]);
    m.push(['商品画像（カラー別）']);
    pushImageBands(activeImgs, false);
  }
  if (excludedImgs.length) {
    m.push([]);
    m.push(['商品画像（集計対象外・参考）']);
    pushImageBands(excludedImgs, true);
  }

  // ── ③ 明細テーブル（グループ見出し → 列見出し → データ）──
  m.push([]);
  const grp: (string | number)[] = new Array(PLAN1_TABLE_COLS).fill('');
  for (const g of PLAN1_GROUPS) grp[g.col] = g.label;
  m.push(grp);
  m.push(['カラー', 'サイズ', 'SKU品番', '上代', '販売タイプ', 'お気に入り', '販売数', 'FKU枚数構成',
    '前回発注日', '前回原価', '最新加重平均原価', '最終入荷日', '現在庫数', '推奨発注数', '確定発注数',
    '販売数', '日販平均', '現在庫日数', '現在庫完売想定日', '販売数', '日販中央値', '現在庫日数', '現在庫完売想定日',
    'フリー在庫数', 'フリー在庫日数', '予約未処理数', '入荷日1', '入荷数', '入荷日2', '入荷数', '入荷日3', '入荷数']);
  for (const s of p.skus) {
    m.push([
      v(s.color_name), v(s.size), v(s.sku_code), v(s.retail_price), v(s.sale_type), v(s.favorites), s.sales_qty,
      fkuv(s.fku_share), v(s.last_order_date), v(s.last_cost), v(s.latest_avg_cost), v(s.last_arrival_date),
      s.current_stock, v(s.recommended_qty), '', s.s7_qty, v(s.s7_daily_avg), v(s.s7_stock_days), v(s.s7_sellout),
      s.l30_qty, v(s.l30_daily_median), v(s.l30_stock_days), v(s.l30_sellout),
      s.free_stock, v(s.free_stock_days), s.reserved_pending,
      v(s.arr1_date), v(s.arr1_qty), v(s.arr2_date), v(s.arr2_qty), v(s.arr3_date), v(s.arr3_qty),
    ]);
  }
  return m;
}

// ヘッダ（品番属性・レビュー・合計粗利率/値引率・合計上代/枚数）
async function fetchHeader(pc: string, start: string, end: string, asof: string) {
  const [mRow, rv, tot, cost] = await Promise.all([
    q(`SELECT ANY_VALUE(product_name) nm, ANY_VALUE(shop_name) shop, ANY_VALUE(parent_category) brand,
         ANY_VALUE(parent_item_type) pit, ANY_VALUE(child_item_type) cit
       FROM ${T('product_master')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))`, { pc }),
    q(`SELECT COUNT(*) c, ROUND(AVG(rating),2) a FROM ${T('product_reviews')}
       WHERE product_code=@pc AND review_date<=DATE(@asof)`, { pc, asof }),
    q(`SELECT SUM(sales_quantity) qty, SUM(sales_amount) rev, SUM(proper_price*sales_quantity) lst
       FROM ${T('sales_daily')} WHERE product_code=@pc AND source_file='orders'
         AND sale_date BETWEEN DATE(@sd) AND DATE(@ed)`, { pc, sd: start, ed: end }),
    // 原価（顧客No.7 2026-06-24 古城）: PF手数料表の原価(下代・品番単位)を優先し、
    //   無い場合(PF原価=0/未登録)のみ MMS原価(cost_master・SKU単位)を参照する。
    //   ＝マート(06_simple_mart_build)・予約管理表と同一の COALESCE(PF, MMS) ロジック。粗利率算出用。
    q(`WITH s AS (SELECT UPPER(TRIM(sku_code)) sk, color_name, size, SUM(sales_quantity) qty, SUM(sales_amount) rev
                  FROM ${T('sales_daily')} WHERE product_code=@pc AND source_file='orders'
                    AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) GROUP BY sk,color_name,size),
            pfc AS (SELECT ANY_VALUE(cost_price) val FROM ${T('pf_fee_master')}
                    WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))
                      AND snapshot_date=(SELECT MAX(snapshot_date) FROM ${T('pf_fee_master')}) AND cost_price>0),
            c AS (SELECT UPPER(TRIM(sku_code)) sk, ANY_VALUE(cost_price) vp FROM ${T('cost_master')}
                  WHERE product_code=@pc AND valid_to IS NULL GROUP BY sk)
       SELECT SUM(s.rev) rev,
              SUM(s.qty*COALESCE((SELECT val FROM pfc), c.vp, 0)) cost,
              COUNTIF((SELECT val FROM pfc) IS NULL AND c.vp IS NULL AND s.qty>0) miss
       FROM s LEFT JOIN c ON c.sk=s.sk`, { pc, sd: start, ed: end }),
  ]);
  const m = mRow[0] ?? {};
  const t = tot[0] ?? {};
  const trv = num(t.rev), tls = num(t.lst), tq = num(t.qty);
  const c = cost[0] ?? {};
  const totalCost = num(c.cost);
  const margin = trv ? r1((trv - totalCost) / trv * 100) : null;
  const discount = tls ? r1((1 - trv / tls) * 100) : null;
  return {
    product_name: m.nm ?? null, shop: m.shop ?? null, brand: m.brand ?? null,
    item_type_parent: m.pit ?? null, item_type_child: m.cit ?? null,
    review_count: rv[0]?.c != null ? num(rv[0].c) : null,
    review_avg: rv[0]?.a != null ? r2(num(rv[0].a)) : null,
    total_margin_pct: margin, total_discount_pct: discount,
    total_list_amount: tls || null, total_revenue: trv || null, total_qty: tq,
  };
}
