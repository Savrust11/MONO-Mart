/**
 * 発注管理表（項目詳細）— 品番 × 指定期間 の「実数」集計。
 * 仕様シート「発注管理表項目詳細」(R02-R82) の計算式どおり（独自計算なし）。
 * 計算ロジックは pipeline/scrapers/order_report.py と同一（compute_values / build_rows）を TS 移植。
 *
 * 確定事項（社内で決めること）反映:
 *  現在庫=S列販売可能数・予約0(№1) / フリー在庫=現在庫(予約0)+入荷残-予約未処理(№3)
 *  最終入荷日=納品書NO 空白/先頭_/-SAI- を除外(№12) / お気に入り=在庫分析daily(№11)
 *  販売開始日=期間内初回受注日(№2)
 * 在庫日数の分母は 30日中央値 に統一（仕様の中央値/平均の矛盾は要客確認）。
 * データ未取得の項目は value=null（画面で「（データ未取得）」表示）。
 */
import { BigQuery } from '@google-cloud/bigquery';

const PROJECT = process.env.GCP_PROJECT_ID!;
const DS = process.env.BQ_DATASET_ANALYTICS ?? 'analytics_layer';
const LOCATION = process.env.BQ_LOCATION ?? 'asia-northeast1';

let _bq: BigQuery | null = null;
function bq(): BigQuery {
  if (!_bq) _bq = new BigQuery({ projectId: PROJECT });
  return _bq;
}
async function q(query: string, params: Record<string, unknown>): Promise<any[]> {
  const [rows] = await bq().query({ query, params, location: LOCATION });
  return rows as any[];
}
const num = (x: unknown): number => Number((x as any)?.value ?? x ?? 0) || 0;
const T = (name: string) => `\`${PROJECT}.${DS}.${name}\``;

export type ReportRow = { kind: 'title' | 'sec' | 'item' | 'blank'; label: string; value: string | number | null; note: string };

const NA = '（データ未取得）';
const WIN_SHORT = 7;
const WIN_LONG = 30;
const STOCK_DAYS_BASIS: 'median' | 'average' = 'median';

function dstr(d: Date): string { return d.toISOString().slice(0, 10); }
function addDays(iso: string, n: number): string {
  const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return dstr(d);
}
function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 86400000);
}
function median(xs: number[]): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b); const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
const r1 = (x: number) => Math.round(x * 10) / 10;
const r2 = (x: number) => Math.round(x * 100) / 100;

export async function fetchPeriodReport(pc: string, start: string, end: string): Promise<ReportRow[]> {
  // 作成日（自動）= データ最新日を超えない当日
  const today = dstr(new Date());
  const asofRow = (await q(
    `SELECT LEAST(@t, CAST(MAX(sale_date) AS STRING)) d FROM ${T('sales_daily')} WHERE source_file='orders'`,
    { t: today },
  ))[0];
  const asof: string = asofRow?.d ?? today;
  const dL = addDays(asof, -(WIN_LONG - 1));

  // ── 受注期間集計（SKU単位）＋原価（PF品番→MMS SKU）R14/R15/R25/R71/R73 ──
  const sku = await q(
    `WITH s AS (
       SELECT sku_code, color_name, size, sale_type,
         SUM(sales_quantity) qty, SUM(sales_amount) rev, SUM(proper_price*sales_quantity) lst
       FROM ${T('sales_daily')}
       WHERE product_code=@pc AND source_file='orders'
         AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) AND sales_quantity>0
       GROUP BY sku_code, color_name, size, sale_type),
     pfc AS (
       SELECT ANY_VALUE(cost_price) val FROM ${T('pf_fee_master')}
       WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))
         AND snapshot_date=(SELECT MAX(snapshot_date) FROM ${T('pf_fee_master')}) AND cost_price>0),
     mms AS (
       SELECT j_col, j_sz, ARRAY_AGG(cost_price ORDER BY source_date DESC LIMIT 1)[OFFSET(0)] cp
       FROM (SELECT UPPER(TRIM(color_name)) j_col, UPPER(TRIM(size)) j_sz, cost_price, source_date
             FROM ${T('cost_master')}
             WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND color_name IS NOT NULL
               AND size IS NOT NULL AND valid_to IS NULL)
       GROUP BY j_col, j_sz)
     SELECT s.color_name, s.sale_type, s.qty, s.rev, s.lst,
       COALESCE((SELECT val FROM pfc), mms.cp) AS cost
     FROM s LEFT JOIN mms ON mms.j_col=UPPER(TRIM(s.color_name)) AND mms.j_sz=UPPER(TRIM(s.size))`,
    { pc, sd: start, ed: end },
  );
  let tq = 0, trv = 0, tls = 0, tcs = 0, yq = 0;
  const fku: Record<string, number> = {};
  for (const r of sku) {
    const qty = num(r.qty); tq += qty; trv += num(r.rev); tls += num(r.lst);
    if (r.cost != null) tcs += num(r.cost) * qty;
    if (r.sale_type && String(r.sale_type).includes('予約')) yq += qty;
    fku[r.color_name] = (fku[r.color_name] ?? 0) + qty;
  }
  const avgPrice = tq ? r1(trv / tq) : null;
  const discount = tls ? r1((1 - trv / tls) * 100) : null;
  const margin = trv ? r1((trv - tcs) / trv * 100) : null;
  const avgCost = tq && tcs ? r1(tcs / tq) : null;
  const yoyakuRate = tq ? r1(yq / tq * 100) : null;

  // ── マスタ属性 R07-R11,R20 ──
  const m = (await q(
    `SELECT ANY_VALUE(product_name) nm, ANY_VALUE(shop_name) shop, ANY_VALUE(parent_category) brand,
       ANY_VALUE(parent_item_type) pit, ANY_VALUE(child_item_type) cit, ANY_VALUE(proper_price) jodai
     FROM ${T('product_master')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))`, { pc },
  ))[0] ?? {};

  // ── 販売開始日＝期間内初回受注日（確定№2）──
  const sd0 = (await q(
    `SELECT MIN(sale_date) d FROM ${T('sales_daily')} WHERE product_code=@pc AND source_file='orders'
       AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) AND sales_quantity>0`, { pc, sd: start, ed: end },
  ))[0];
  const saleStart: string | null = sd0?.d ? (sd0.d.value ?? sd0.d) : null;

  // ── 在庫分析daily（現在）: 現在庫=S列・予約0（確定№1）/ お気に入り（確定№11）──
  const st = (await q(
    `WITH pm AS (SELECT UPPER(TRIM(product_code)) pc, UPPER(TRIM(sku_code)) sk, ANY_VALUE(sale_type) stype
                 FROM ${T('product_master')} GROUP BY pc, sk)
     SELECT SUM(CASE WHEN pm.stype LIKE '%予約%' THEN 0 ELSE sa.available_qty END) cur, SUM(sa.favorites) fav
     FROM ${T('stock_analysis')} sa
     LEFT JOIN pm ON pm.pc=UPPER(TRIM(sa.product_code)) AND pm.sk=UPPER(TRIM(sa.sku_code))
     WHERE sa.product_code=@pc
       AND sa.snapshot_date=(SELECT MAX(snapshot_date) FROM ${T('stock_analysis')} WHERE snapshot_date<=DATE(@asof))`,
    { pc, asof },
  ))[0] ?? {};
  const curStock = num(st.cur);
  const favorites = num(st.fav);

  // ── 最終入荷日（除外3条件・確定№12）R31 ──
  const arr = (await q(
    `SELECT MAX(arrival_date) d FROM ${T('inventory_snapshot')}
     WHERE product_code=@pc AND delivery_note_no IS NOT NULL AND delivery_note_no!=''
       AND NOT STARTS_WITH(delivery_note_no,'_') AND NOT REGEXP_CONTAINS(delivery_note_no,'-SAI-')`, { pc },
  ))[0];
  const lastArrival: string | null = arr?.d ? (arr.d.value ?? arr.d) : null;

  // ── 予約未処理数 R50 ──
  const rv = (await q(
    `SELECT SUM(quantity) q FROM ${T('reservations')} WHERE product_code=@pc
       AND reservation_date=(SELECT MAX(reservation_date) FROM ${T('reservations')} WHERE product_code=@pc)`, { pc },
  ))[0];
  const reservedPending = num(rv?.q);

  // ── 入荷残 + 入荷山1/2/3 R52-59 ──
  const inc = (await q(
    `SELECT SUM(incoming_qty) q FROM ${T('incoming_stock')} WHERE product_code=@pc
       AND source_date=(SELECT MAX(source_date) FROM ${T('incoming_stock')} WHERE product_code=@pc)`, { pc },
  ))[0];
  const incomingRemain = num(inc?.q);
  const arrivals = await q(
    `SELECT SAFE_CAST(REPLACE(earliest_arrival_date,'/','-') AS DATE) d, SUM(incoming_qty) q
     FROM ${T('incoming_stock')}
     WHERE product_code=@pc AND earliest_arrival_date IS NOT NULL
       AND source_date=(SELECT MAX(source_date) FROM ${T('incoming_stock')} WHERE product_code=@pc)
     GROUP BY d HAVING d IS NOT NULL AND d>=DATE(@asof) ORDER BY d LIMIT 3`, { pc, asof },
  );

  // ── 累計レビュー件数/点数 R12-13 ──
  const rr = (await q(
    `SELECT COUNT(*) c, ROUND(AVG(rating),2) a FROM ${T('product_reviews')}
     WHERE product_code=@pc AND review_date<=DATE(@asof)`, { pc, asof },
  ))[0] ?? {};
  const reviewCnt = num(rr.c);
  const reviewAvg = rr.a != null ? r2(num(rr.a)) : null;

  // ── 日次系列 → 日販平均(短期)・中央値(長期, 在庫ルール込み) R38/R43 ──
  const dsRows = await q(
    `SELECT CAST(sale_date AS STRING) d, SUM(sales_quantity) q FROM ${T('sales_daily')}
     WHERE product_code=@pc AND source_file='orders' AND sale_date BETWEEN DATE(@dl) AND DATE(@asof) GROUP BY d`,
    { pc, dl: dL, asof },
  );
  const stRows = await q(
    `SELECT CAST(snapshot_date AS STRING) d, SUM(available_qty) s FROM ${T('stock_analysis')}
     WHERE product_code=@pc AND snapshot_date BETWEEN DATE(@dl) AND DATE(@asof) GROUP BY d`,
    { pc, dl: dL, asof },
  );
  const dsl: Record<string, number> = {}; for (const r of dsRows) dsl[r.d] = num(r.q);
  const dst: Record<string, number> = {}; for (const r of stRows) dst[r.d] = num(r.s);
  const dval = (ds: string): number | null => {  // R43: 受注>0→値, 在庫>0&受注0→0, それ以外→除外
    const qd = dsl[ds] ?? 0; if (qd > 0) return qd;
    const s = dst[ds]; return s && s > 0 ? 0 : null;
  };
  const daysS = Array.from({ length: WIN_SHORT }, (_, i) => addDays(asof, -i));
  const daysL = Array.from({ length: WIN_LONG }, (_, i) => addDays(asof, -i));
  const sumS = daysS.reduce((a, d) => a + (dsl[d] ?? 0), 0);
  let elapsed = WIN_SHORT;
  if (saleStart) elapsed = Math.min(WIN_SHORT, daysBetween(saleStart, asof) + 1);
  elapsed = Math.max(1, elapsed);
  const veloS = r2(sumS / elapsed);                                  // R38
  const valsL = daysL.map(dval).filter((v): v is number => v !== null);
  const med = valsL.length ? r2(median(valsL)) : 0;                  // R43
  const salesS = sumS;
  const salesL = daysL.reduce((a, d) => a + (dsl[d] ?? 0), 0);

  const basis = STOCK_DAYS_BASIS === 'median' ? med : veloS;
  const sdays = (stock: number, rate: number): number | null => (rate ? r1(stock / rate) : null);
  const soldout = (d: number | null): string | null => (d == null ? null : addDays(asof, Math.round(d)));
  const sdS = sdays(curStock, veloS);
  const sdL = sdays(curStock, med);
  const freeStock = curStock + incomingRemain - reservedPending;     // 確定№3
  const freeDays = sdays(freeStock, basis);

  // ── 販売タイプ（現在の在庫/予約）R21 ──
  const stype = (await q(
    `SELECT CASE WHEN COUNTIF(sale_type LIKE '%予約%')=COUNT(*) THEN '予約'
                 WHEN COUNTIF(sale_type LIKE '%予約%')>0 THEN '在庫/予約 混在'
                 ELSE '在庫' END st
     FROM ${T('product_master')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND sale_type IS NOT NULL`,
    { pc }))[0];
  const saleType: string | null = stype?.st ?? null;

  // ── 推奨発注数 R34（Phase1合意式: MAX(0, CEIL(8週×7日×30日平均日販 − フリー在庫)))──
  const velo30 = salesL / WIN_LONG;
  const recommended = Math.max(0, Math.ceil(8 * 7 * velo30 - freeStock));

  // ── ブランド 限定回避 R09: sales_daily の最新「非【限定】」親カテゴリを引き継ぐ ──
  const brandRow = (await q(
    `SELECT parent_category b FROM ${T('sales_daily')}
     WHERE product_code=@pc AND parent_category IS NOT NULL AND parent_category NOT LIKE '%限定%'
     ORDER BY sale_date DESC LIMIT 1`, { pc }))[0];
  const brand: string | null = brandRow?.b ?? (m.brand ?? null);

  // ── ② 内訳: UU / CVR / お気に率（商品別実績(新)＝sales_dailyの該当列）R65-67 ──
  const uuRow = (await q(
    `SELECT SUM(unique_visitors) u, SUM(favorites) f FROM ${T('sales_daily')}
     WHERE product_code=@pc AND sale_date BETWEEN DATE(@sd) AND DATE(@ed)`, { pc, sd: start, ed: end },
  ))[0];
  const UU = uuRow?.u != null ? num(uuRow.u) : null;
  const favSum = num(uuRow?.f);
  const cvr = UU ? r1(tq / UU * 100) : null;       // R66: 品番合計受注点数(注文数)÷品番合計UU
  const favRate = UU ? r1(favSum / UU * 100) : null; // R67: 品番合計お気に入り÷品番合計UU

  // ── 前回原価＝sitateru 実原価の最新（作成日以前）R28 ──
  const prevCost = (await q(
    `SELECT actual_cost ac FROM ${T('sitateru_item_master')}
     WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND actual_cost IS NOT NULL AND actual_cost>0
       AND snapshot_date<=DATE(@asof) ORDER BY snapshot_date DESC LIMIT 1`, { pc, asof },
  ))[0];
  const prevCostV = prevCost?.ac != null ? num(prevCost.ac) : null;

  // ── 前回発注日・前回原価＝MMS発注書一覧の最新発注（作成日以前）R27/R28 ──
  const prevOrder = (await q(
    `SELECT CAST(order_date AS STRING) d, unit_price up FROM ${T('mms_orders')}
     WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND order_date<=DATE(@asof) AND order_date IS NOT NULL
     ORDER BY order_date DESC LIMIT 1`, { pc, asof }))[0];
  const prevOrderDate: string | null = prevOrder?.d ?? null;
  const prevOrderCost = prevOrder?.up != null ? num(prevOrder.up) : null;

  // ── 入荷数量（期間中に入荷した数）R74 ──
  const inq = (await q(
    `SELECT SUM(incoming_qty) q FROM ${T('incoming_stock')}
     WHERE product_code=@pc
       AND SAFE_CAST(REPLACE(earliest_arrival_date,'/','-') AS DATE) BETWEEN DATE(@sd) AND DATE(@ed)`,
    { pc, sd: start, ed: end },
  ))[0];
  // R74: incoming_stock は取込済み（全体で約27万行）。該当なし(NULL)は取得失敗ではなく
  //       「この品番は期間内に入荷なし＝0」を意味するため、NA ではなく 0 を表示する（顧客確認済み）。
  const incomingQty = num(inq?.q);

  // ── CP対象枚数比：ショップがクーポン実施日 且つ この品番がクーポン除外にない日の注文数÷合計 R68 ──
  const cpRow = (await q(
    `WITH shop AS (SELECT ANY_VALUE(shop_name) s FROM ${T('product_master')} WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))),
     cdays AS (SELECT DISTINCT CAST(exclusion_date AS STRING) d FROM ${T('coupon_exclusion')}
               WHERE brand_name=(SELECT s FROM shop)),
     excl AS (SELECT DISTINCT CAST(exclusion_date AS STRING) d FROM ${T('coupon_exclusion')}
              WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc))),
     s AS (SELECT CAST(sale_date AS STRING) d, SUM(sales_quantity) q FROM ${T('sales_daily')}
           WHERE product_code=@pc AND source_file='orders' AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) GROUP BY d)
     SELECT SUM(q) total,
       SUM(IF(d IN (SELECT d FROM cdays) AND d NOT IN (SELECT d FROM excl), q, 0)) cp
     FROM s`, { pc, sd: start, ed: end },
  ))[0];
  const cpRate = cpRow && num(cpRow.total) ? r1(num(cpRow.cp) / num(cpRow.total) * 100) : null;

  // ── 画像URL：color_master の カラーID を使う（R02）──
  //   https://o.imgz.jp/{商品コード末尾3}/{商品コード}/{商品コード}b_{カラーID}_d.jpg
  const imgRows = await q(
    `WITH pm AS (SELECT DISTINCT color_name, item_code FROM ${T('product_master')}
                 WHERE UPPER(TRIM(product_code))=UPPER(TRIM(@pc)) AND color_name IS NOT NULL AND item_code IS NOT NULL)
     SELECT pm.color_name cn, ANY_VALUE(pm.item_code) ic, ANY_VALUE(cm.color_id) cid
     FROM pm LEFT JOIN ${T('color_master')} cm ON TRIM(cm.color_name)=TRIM(pm.color_name)
     GROUP BY pm.color_name`, { pc });
  const images = imgRows.filter((r) => r.ic && r.cid).map((r) => ({
    color: String(r.cn),
    url: `https://o.imgz.jp/${String(r.ic).slice(-3)}/${r.ic}/${r.ic}b_${r.cid}_d.jpg`,
  }));
  const imageUrl = images.length ? images[0].url : null;  // 代表画像（先頭カラー）

  // ── ②内訳 在庫（当時）= 期間終了時点の在庫 R75 ──
  const stockEnd = (await q(
    `WITH pm AS (SELECT UPPER(TRIM(product_code)) pc, UPPER(TRIM(sku_code)) sk, ANY_VALUE(sale_type) stype
                 FROM ${T('product_master')} GROUP BY pc, sk)
     SELECT SUM(CASE WHEN pm.stype LIKE '%予約%' THEN 0 ELSE sa.available_qty END) cur
     FROM ${T('stock_analysis')} sa
     LEFT JOIN pm ON pm.pc=UPPER(TRIM(sa.product_code)) AND pm.sk=UPPER(TRIM(sa.sku_code))
     WHERE sa.product_code=@pc
       AND sa.snapshot_date=(SELECT MAX(snapshot_date) FROM ${T('stock_analysis')}
                             WHERE product_code=@pc AND snapshot_date<=DATE(@ed))`,
    { pc, ed: end }))[0];
  const stockAtPeriod = stockEnd?.cur != null ? num(stockEnd.cur) : null;

  // ── SKU別明細（カラー名/サイズ名/SKU品番＝ブランド品番&CS品番）R17-19 ──
  const skuDetail = await q(
    `SELECT color_name, size, ANY_VALUE(sku_code) sk, SUM(sales_quantity) qty
     FROM ${T('sales_daily')} WHERE product_code=@pc AND source_file='orders'
       AND sale_date BETWEEN DATE(@sd) AND DATE(@ed) AND sales_quantity>0
     GROUP BY color_name, size ORDER BY color_name, size`, { pc, sd: start, ed: end });

  const piv = (fmt: string) => q(
    `SELECT ${fmt} k, SUM(sales_quantity) q FROM ${T('sales_daily')}
     WHERE product_code=@pc AND source_file='orders' AND sale_date BETWEEN DATE(@sd) AND DATE(@ed)
     GROUP BY k ORDER BY k`, { pc, sd: start, ed: end });
  const pivY = await piv('EXTRACT(YEAR FROM sale_date)');
  const pivM = await piv("FORMAT_DATE('%Y/%m', sale_date)");
  const pivD = await piv("FORMAT_DATE('%Y/%m/%d', sale_date)");

  // ── レイアウト（仕様の項目順）→ rows ──
  const rows: ReportRow[] = [];
  const sec = (label: string) => rows.push({ kind: 'sec', label, value: '', note: '' });
  const it = (label: string, value: string | number | null, note = '') => rows.push({ kind: 'item', label, value, note });
  const blank = () => rows.push({ kind: 'blank', label: '', value: '', note: '' });

  rows.push({ kind: 'title', label: '発注管理表（項目詳細） — 品番×期間の実数', value: '', note: '' });
  sec('基本情報');
  it('品番', pc); it('商品名', m.nm ?? null); it('ショップ', m.shop ?? null);
  it('集計開始日', start, '入力値'); it('集計終了日', end, '入力値'); it('作成日', asof, '自動（データ最新日）');
  blank(); sec('① 集計');
  it('ブランド（親カテゴリ）', brand, '年2回【限定】回避＝直近の非限定値を引継ぎ（R09）');
  it('商品タイプ親', m.pit ?? null); it('商品タイプ子', m.cit ?? null);
  it('上代（税抜）', m.jodai != null ? num(m.jodai) : null);
  it('販売開始日', saleStart, '期間内初回受注日（確定№2）');
  it('累計レビュー件数', reviewCnt); it('累計レビュー点数', reviewAvg);
  it('合計販売数', tq); it('平均売価（税抜）', avgPrice);
  it('合計値引率(%)', discount); it('合計粗利率(%)', margin, 'PF→MMS（R14/R69）');
  it('最新加重平均原価', avgCost);
  it('お気に入り', favorites, '在庫分析daily（確定№11）');
  it('販売タイプ', saleType, '現在の在庫/予約（R21）');
  it('現在庫数', curStock, 'S列販売可能数・予約0（確定№1）');
  it('最終入荷日', lastArrival, '納品書NO 空白/先頭_/-SAI- 除外（確定№12）');
  it('予約未処理数', reservedPending);
  it('フリー在庫数', freeStock, '現在庫(予約0)+入荷残-予約未処理（確定№3）');
  it('フリー在庫日数', freeDays, `分母=${STOCK_DAYS_BASIS}（要客確認の矛盾点）`);
  it('前回発注日', prevOrderDate, 'MMS発注書一覧の最新発注日（R27）');
  it('前回原価', prevOrderCost ?? prevCostV, 'MMS発注単価→無ければsitateru実原価（R28）');
  it('画像', imageUrl, 'color_master のカラーID で生成（R02）');
  it('推奨発注数', recommended, '8週×30日平均日販−フリー在庫（R34）');
  it('確定発注数', '', '手入力欄');
  blank();
  it(`▼直近${WIN_SHORT}日 販売数`, salesS);
  it(`▼直近${WIN_SHORT}日 日販平均`, veloS, '販売数÷7（7日未満は経過日数）');
  it(`▼直近${WIN_SHORT}日 現在庫日数`, sdS);
  it(`▼直近${WIN_SHORT}日 完売想定日`, soldout(sdS));
  it(`▼直近${WIN_LONG}日 販売数`, salesL);
  it(`▼直近${WIN_LONG}日 日販中央値`, med, '在庫あり受注0=0/在庫無し受注0=除外');
  it(`▼直近${WIN_LONG}日 現在庫日数`, sdL);
  it(`▼直近${WIN_LONG}日 完売想定日`, soldout(sdL));
  blank(); sec('入荷山（予約管理表）');
  for (let i = 0; i < 3; i++) {
    const a = arrivals[i];
    it(`入荷日${i + 1}`, a?.d ? (a.d.value ?? a.d) : ''); it(`　入荷数${i + 1}`, a ? num(a.q) : '');
  }
  sec('FKU枚数構成（品番&カラー）');
  for (const [c, n] of Object.entries(fku).sort((a, b) => b[1] - a[1])) {
    it(`　${c}`, tq ? `${r1(n / tq * 100)}%` : '0%', `${n}枚`);
  }
  blank(); sec('② 内訳');
  it('合計販売数', tq); it('平均売価（税抜）', avgPrice);
  it('粗利率(%)', margin); it('値引率(%)', discount);
  it('予約販売数割合(%)', yoyakuRate);
  it('UU', UU, '商品別実績(新)・受注CSVと1日ずれ（R65）');
  it('CVR(%)', cvr, '受注点数(注文数)÷UU（R66）');
  it('お気に率(%)', favRate, 'お気に入り÷UU（R67）');
  it('CP対象枚数比(%)', cpRate, 'クーポン実施日×非除外の注文数÷合計（R68）');
  it('入荷数量（期間）', incomingQty, '期間中に入荷した数（0=入荷なし）・予約管理表（R74）');
  it('在庫（当時）', stockAtPeriod, '期間終了時点の在庫（R75）');
  blank(); sec('SKU別（カラー名/サイズ名/SKU品番）R17-19');
  for (const r of skuDetail) {
    it(`　${r.color_name ?? ''} / ${r.size ?? ''}`, `${pc}${r.sk ?? ''}`, `販売数 ${num(r.qty)}`);
  }
  blank(); sec('時系列（注文数）年');
  for (const r of pivY) it(`　${r.k}`, num(r.q));
  sec('時系列（注文数）月');
  for (const r of pivM) it(`　${r.k}`, num(r.q));
  sec('時系列（注文数）日');
  for (const r of pivD) it(`　${r.k}`, num(r.q));

  return rows.map((r) => ({ ...r, value: r.value == null ? NA : r.value }));
}
