'use client';

import { useState, useEffect, useCallback } from 'react';
import { LoadingProgress } from '../LoadingProgress';

// 発注管理表「期間集計」(旧:案1・SKU別明細ビュー)。/api/order-plan1 のレスポンス型。
interface Plan1Sku {
  color_name: string | null; size: string | null; sku_code: string | null;
  retail_price: number | null; sale_type: string | null; favorites: number | null;
  sales_qty: number; period_rev: number; period_cost: number; period_lst: number; fku_share: number | null;
  last_order_date: string | null; last_cost: number | null; latest_avg_cost: number | null;
  last_arrival_date: string | null; current_stock: number;
  recommended_qty: number | null; recommended_provisional: boolean; confirmed_qty: null;
  s7_qty: number; s7_daily_avg: number | null; s7_stock_days: number | null; s7_sellout: string | null;
  l30_qty: number; l30_daily_median: number | null; l30_stock_days: number | null; l30_sellout: string | null;
  free_stock: number; free_stock_days: number | null; reserved_pending: number;
  arr1_date: string | null; arr1_qty: number | null;
  arr2_date: string | null; arr2_qty: number | null;
  arr3_date: string | null; arr3_qty: number | null;
}
interface Plan1Image { color: string; url: string; }
interface Plan1 {
  images: Plan1Image[];
  header: {
    created_at: string; start: string; end: string; product_code: string;
    product_name: string | null; shop: string | null; brand: string | null;
    item_type_parent: string | null; item_type_child: string | null;
    review_count: number | null; review_avg: number | null;
    total_margin_pct: number | null; total_discount_pct: number | null;
    total_list_amount: number | null; total_qty: number;
  };
  skus: Plan1Sku[];
}

const n = (v: number | null | undefined, suffix = '') =>
  v == null ? '—' : v.toLocaleString('ja-JP') + suffix;
const d = (v: string | null) => (v ? String(v).slice(0, 10) : '—');

export function Plan1View({ code, start, end, totalQty = 0 }:
  { code: string; start: string; end: string; totalQty?: number }) {
  const [data, setData] = useState<Plan1 | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false); // 進捗バー表示（完了アニメ含む）
  const [error, setError] = useState<string | null>(null);
  // 仕様: SKUに「集計不要」チェックがある。既定は全集計、チェックで除外。
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [outMsg, setOutMsg] = useState<string | null>(null);
  const [outUrl, setOutUrl] = useState<string | null>(null);
  // #1 確定発注数: 手入力欄（SKU品番ごと）。既定は空欄、未入力時は推奨発注数をプレースホルダ表示。
  const [confirmed, setConfirmed] = useState<Record<string, string>>({});

  const toSheet = useCallback(async () => {
    setOutMsg('スプシ出力中…'); setOutUrl(null);
    try {
      const res = await fetch(`/api/order-plan1/to-sheet?product_code=${encodeURIComponent(code)}&start=${start}&end=${end}`, { method: 'POST' });
      const j = await res.json();
      if (res.ok) { setOutMsg(`✓ 新規スプレッドシート「${j.filename}」を作成しました（${j.rows}行）`); setOutUrl(j.url || null); }
      else setOutMsg(`エラー: ${j.error || '失敗'}`);
    } catch (e) { setOutMsg('通信エラー: ' + String(e)); }
  }, [code, start, end]);

  const run = useCallback(async () => {
    setBusy(true); setLoading(true); setError(null);
    try {
      const res = await fetch(
        `/api/order-plan1?product_code=${encodeURIComponent(code)}&start=${start}&end=${end}`);
      const j = await res.json();
      if (!res.ok) { setError(j.error || '取得に失敗しました'); setData(null); }
      else { setData(j as Plan1); setExcluded(new Set()); }
    } catch (e) { setError('通信エラー: ' + String(e)); setData(null); }
    finally { setLoading(false); }
  }, [code, start, end]);

  useEffect(() => { run(); }, [run]);

  if (busy) return <LoadingProgress active={loading} label="期間集計を集計中" onDone={() => setBusy(false)} />;
  if (error) return <div className="m-4 bg-rose-50 border border-rose-200 rounded p-3 text-xs text-rose-700">{error}</div>;
  if (!data) return null;

  const h = data.header;
  const isExcluded = (s: Plan1Sku) => excluded.has(s.sku_code ?? '');
  // 顧客#5/#6: 「集計不要」は行を消さず最下行へ移動・グレー表示し、いつでも✔を外して復活可能にする。
  //   集計（配分・入荷列）は除外SKUを含めない（=activeRows）。
  const rows = [...data.skus].sort((a, b) => Number(isExcluded(a)) - Number(isExcluded(b)));
  const activeRows = data.skus.filter((s) => !isExcluded(s));
  const toggle = (sk: string) =>
    setExcluded((p) => { const x = new Set(p); x.has(sk) ? x.delete(sk) : x.add(sk); return x; });

  // 顧客#1: 品番合計から「集計対象外SKU」を除外。除外ゼロ時はサーバ値（厳密一致）、除外時のみ再計算。
  const round1 = (x: number) => Math.round(x * 10) / 10;
  const hdr = excluded.size === 0
    ? { qty: h.total_qty, lst: h.total_list_amount, margin: h.total_margin_pct, discount: h.total_discount_pct }
    : (() => {
        const rev = activeRows.reduce((a, s) => a + (s.period_rev || 0), 0);
        const cost = activeRows.reduce((a, s) => a + (s.period_cost || 0), 0);
        const lst = activeRows.reduce((a, s) => a + (s.period_lst || 0), 0);
        const qty = activeRows.reduce((a, s) => a + (s.sales_qty || 0), 0);
        return {
          qty,
          lst: lst || null,
          margin: rev > 0 ? round1((rev - cost) / rev * 100) : null,
          discount: lst > 0 ? round1((1 - rev / lst) * 100) : null,
        };
      })();
  const totalLabel = excluded.size > 0 ? `（集計対象 ${activeRows.length}/${data.skus.length} SKU）` : '';

  // 総数指定→SKU配分（⚠暫定: 30日販売数構成比＋最大剰余法。配分基準はスプシ未定義のため要確認）
  const alloc: Record<string, number> = {};
  if (totalQty > 0 && activeRows.length) {
    const w = activeRows.map((s) => Math.max(s.l30_qty || 0, 0));
    const sumW = w.reduce((a, b) => a + b, 0);
    const raw = activeRows.map((_, i) => (sumW > 0 ? totalQty * (w[i] / sumW) : totalQty / activeRows.length));
    const floor = raw.map(Math.floor);
    let residual = totalQty - floor.reduce((a, b) => a + b, 0);
    raw.map((r, i) => ({ i, f: r - Math.floor(r) })).sort((a, b) => b.f - a.f)
      .forEach(({ i }) => { if (residual-- > 0) floor[i] += 1; });
    activeRows.forEach((s, i) => { alloc[s.sku_code ?? ''] = floor[i]; });
  }

  // #3 入荷山を「日付ごと」に整列（左詰めをやめる）。全SKUの入荷予定日を集めて列に並べ、
  //    各SKUの入荷数量を該当する日付列の下に配置する。
  const arrivalDates: string[] = (() => {
    const set = new Set<string>();
    for (const s of activeRows) for (const dt of [s.arr1_date, s.arr2_date, s.arr3_date]) if (dt) set.add(dt);
    return Array.from(set).sort();
  })();
  // テーブル総列数（除外行の colSpan 用）。先頭4列（集計不要/カラー/サイズ/SKU品番）以外をまとめる。
  const COLS = 16 + (totalQty > 0 ? 1 : 0) + 4 + 4 + 3 + Math.max(1, arrivalDates.length);
  // 顧客#6: 全SKUが「集計不要」のカラーは、画像を2段目（集計対象外・斜線/グレー）へ移す。
  const excludedColors = new Set(
    Array.from(new Set(data.skus.map((s) => s.color_name).filter((c): c is string => !!c)))
      .filter((c) => { const g = data.skus.filter((s) => s.color_name === c); return g.length > 0 && g.every(isExcluded); })
  );
  const activeImages = data.images.filter((im) => !excludedColors.has(im.color));
  const excludedImages = data.images.filter((im) => excludedColors.has(im.color));
  const arrQtyOf = (s: Plan1Sku, dt: string): number => {
    let q = 0;
    if (s.arr1_date === dt) q += s.arr1_qty ?? 0;
    if (s.arr2_date === dt) q += s.arr2_qty ?? 0;
    if (s.arr3_date === dt) q += s.arr3_qty ?? 0;
    return q;
  };

  return (
    <div className="p-4 space-y-4">
      {/* ヘッダ（品番サマリ） */}
      <div className="bg-white border border-gray-200 rounded p-3 grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-1 text-[13px]">
        <Field label="品番" value={h.product_code} mono />
        <Field label="ショップ" value={h.shop ?? '—'} />
        <Field label="ブランド" value={h.brand ?? '—'} />
        <Field label="作成日" value={d(h.created_at)} />
        <Field label="商品名" value={h.product_name ?? '—'} span />
        <Field label="商品タイプ" value={`${h.item_type_parent ?? '—'} / ${h.item_type_child ?? '—'}`} />
        <Field label="集計期間" value={`${d(h.start)} 〜 ${d(h.end)}`} />
        <Field label="累計レビュー" value={`${n(h.review_count)}件 / ${h.review_avg ?? '—'}点`} />
        <Field label={`合計粗利率${totalLabel}`} value={hdr.margin == null ? '—' : `${hdr.margin}%`} />
        <Field label={`合計値引率${totalLabel}`} value={hdr.discount == null ? '—' : `${hdr.discount}%`} />
        <Field label={`合計上代額${totalLabel}`} value={n(hdr.lst, '円')} />
        <Field label={`合計販売数${totalLabel}`} value={n(hdr.qty, '点')} />
      </div>

      {/* 商品画像（カラー別）R02 */}
      {data.images.length > 0 && (
        <div className="bg-white border border-gray-200 rounded p-3">
          <div className="text-[11px] text-gray-500 mb-2">商品画像（カラー別）</div>
          <div className="flex flex-wrap gap-3">
            {activeImages.map((im) => (
              <figure key={im.color} className="text-center">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={im.url} alt={im.color}
                  className="h-24 w-24 object-cover rounded border border-gray-200"
                  onError={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = '0.25'; }} />
                <figcaption className="text-[10px] text-gray-600 mt-1 w-24 truncate">{im.color}</figcaption>
              </figure>
            ))}
          </div>
          {/* 顧客#6: 集計対象外カラーの画像は2段目へ移動。斜線＋グレースケールで除外を明示 */}
          {excludedImages.length > 0 && (
            <div className="mt-3 pt-2 border-t border-dashed border-gray-300">
              <div className="text-[10px] text-gray-400 mb-2">集計対象外（チェックで除外中）</div>
              <div className="flex flex-wrap gap-3">
                {excludedImages.map((im) => (
                  <figure key={im.color} className="text-center">
                    <div className="relative h-24 w-24">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={im.url} alt={im.color}
                        className="h-24 w-24 object-cover rounded border border-gray-200 grayscale opacity-40" />
                      <div className="absolute inset-0 rounded pointer-events-none"
                        style={{ backgroundImage: 'repeating-linear-gradient(45deg, rgba(0,0,0,0.25) 0 5px, transparent 5px 10px)' }} />
                    </div>
                    <figcaption className="text-[10px] text-gray-400 mt-1 w-24 truncate line-through">{im.color}</figcaption>
                  </figure>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 出力＝スプシ確定（№13）。CSVは確定外のため非表示・APIは残置 */}
      <div className="flex items-center gap-2">
        <button onClick={toSheet}
          className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded text-[12px]">
          スプシ出力
        </button>
        {outMsg && <span className="text-[11px] text-gray-700">{outMsg}</span>}
        {outUrl && (
          <a href={outUrl} target="_blank" rel="noopener noreferrer"
            className="text-[11px] text-teal-700 underline hover:text-teal-800 font-medium">
            📊 スプレッドシートを開く
          </a>
        )}
      </div>

      {/* SKU別明細（横スクロール） */}
      <div className="bg-white border border-gray-200 rounded overflow-x-auto">
        <table className="text-[12px] whitespace-nowrap border-collapse">
          <thead>
            <tr className="text-gray-600 text-[11px]">
              <th colSpan={16 + (totalQty > 0 ? 1 : 0)} className="px-2 py-1 border border-gray-200 bg-gray-50 text-left">▼指定期間合計</th>
              <th colSpan={4} className="px-2 py-1 border border-gray-200 bg-sky-100 text-center">▼直近7日</th>
              <th colSpan={4} className="px-2 py-1 border border-gray-200 bg-teal-100 text-center">▼直近30日</th>
              <th colSpan={3} className="px-2 py-1 border border-gray-200 bg-violet-100 text-center">フリー在庫・予約</th>
              <th colSpan={Math.max(1, arrivalDates.length)} className="px-2 py-1 border border-gray-200 bg-amber-100 text-center">入荷残（日付別）</th>
            </tr>
            <tr className="bg-gray-100 text-gray-600">
              <Th>集計不要</Th><Th>カラー</Th><Th>サイズ</Th><Th>SKU品番</Th><Th>上代</Th><Th>販売タイプ</Th>
              <Th>お気に入り</Th><Th>販売数</Th><Th>FKU構成</Th><Th>前回発注日</Th><Th>前回原価</Th>
              <Th>最新加重平均原価</Th><Th>最終入荷日</Th><Th>現在庫数</Th>
              <Th cls="bg-indigo-50">推奨発注数</Th><Th cls="bg-indigo-50">確定発注数</Th>
              {totalQty > 0 && <Th cls="bg-indigo-100">配分数（暫定）</Th>}
              <Th cls="bg-sky-50">7日販売数</Th><Th cls="bg-sky-50">日販平均</Th><Th cls="bg-sky-50">在庫日数</Th><Th cls="bg-sky-50">完売想定日</Th>
              <Th cls="bg-teal-50">30日販売数</Th><Th cls="bg-teal-50">日販中央値</Th><Th cls="bg-teal-50">在庫日数</Th><Th cls="bg-teal-50">完売想定日</Th>
              <Th cls="bg-violet-50">フリー在庫数</Th><Th cls="bg-violet-50">フリー在庫日数</Th><Th cls="bg-violet-50">予約未処理</Th>
              {arrivalDates.length === 0
                ? <Th cls="bg-amber-50">入荷予定</Th>
                : arrivalDates.map((dt) => <Th key={dt} cls="bg-amber-50">{d(dt)}</Th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => {
              // 顧客#5/#6: 集計不要の行は消さず、グレー＋斜線で「集計対象外」を最下行に残す（✔を外せば復活）
              if (isExcluded(s)) return (
                <tr key={s.sku_code ?? i} className="bg-gray-100 text-gray-400 border-b border-gray-100">
                  <Td center>
                    <input type="checkbox" checked title="チェックを外すと集計に復活します"
                      onChange={() => toggle(s.sku_code ?? '')} />
                  </Td>
                  <Td>{s.color_name ?? '—'}</Td><Td>{s.size ?? '—'}</Td><Td mono>{s.sku_code ?? '—'}</Td>
                  <td colSpan={COLS - 4}
                    className="px-2 py-1 border border-gray-100 italic text-gray-400 text-[11px]"
                    style={{ backgroundImage: 'repeating-linear-gradient(45deg, rgba(0,0,0,0.06) 0 6px, transparent 6px 12px)' }}>
                    集計対象外（チェックを外すと復活します）
                  </td>
                </tr>
              );
              return (
              <tr key={s.sku_code ?? i} className="border-b border-gray-50 hover:bg-gray-50">
                <Td center>
                  <input type="checkbox" checked={false}
                    onChange={() => toggle(s.sku_code ?? '')} />
                </Td>
                <Td>{s.color_name ?? '—'}</Td><Td>{s.size ?? '—'}</Td>
                <Td mono>{s.sku_code ?? '—'}</Td><Td num>{n(s.retail_price)}</Td><Td>{s.sale_type ?? '—'}</Td>
                <Td num>{n(s.favorites)}</Td><Td num>{n(s.sales_qty)}</Td>
                <Td num>{s.fku_share == null ? '—' : `${Math.round(s.fku_share * 100)}%`}</Td>
                <Td>{d(s.last_order_date)}</Td><Td num>{n(s.last_cost)}</Td><Td num>{n(s.latest_avg_cost)}</Td>
                <Td>{d(s.last_arrival_date)}</Td><Td num>{n(s.current_stock)}</Td>
                <Td num cls="bg-indigo-50 font-semibold">{n(s.recommended_qty)}</Td>
                <Td cls="bg-indigo-50">
                  <input type="number" min={0}
                    value={confirmed[s.sku_code ?? ''] ?? ''}
                    placeholder={s.recommended_qty != null ? String(s.recommended_qty) : ''}
                    onChange={(e) => setConfirmed((p) => ({ ...p, [s.sku_code ?? '']: e.target.value }))}
                    className="w-16 px-1 py-0.5 border border-gray-300 rounded text-right text-[12px]" />
                </Td>
                {totalQty > 0 && <Td num cls="bg-indigo-100 font-semibold">{n(alloc[s.sku_code ?? ''] ?? 0)}</Td>}
                <Td num cls="bg-sky-50">{n(s.s7_qty)}</Td><Td num cls="bg-sky-50">{s.s7_daily_avg ?? '—'}</Td>
                <Td num cls="bg-sky-50">{s.s7_stock_days == null ? '—' : `${s.s7_stock_days}日`}</Td><Td cls="bg-sky-50">{d(s.s7_sellout)}</Td>
                <Td num cls="bg-teal-50">{n(s.l30_qty)}</Td><Td num cls="bg-teal-50">{s.l30_daily_median ?? '—'}</Td>
                <Td num cls="bg-teal-50">{s.l30_stock_days == null ? '—' : `${s.l30_stock_days}日`}</Td><Td cls="bg-teal-50">{d(s.l30_sellout)}</Td>
                <Td num cls="bg-violet-50">{n(s.free_stock)}</Td>
                <Td num cls="bg-violet-50">{s.free_stock_days == null ? '—' : `${s.free_stock_days}日`}</Td>
                <Td num cls="bg-violet-50">{n(s.reserved_pending)}</Td>
                {arrivalDates.length === 0
                  ? <Td num cls="bg-amber-50">—</Td>
                  : arrivalDates.map((dt) => {
                      const q = arrQtyOf(s, dt);
                      return <Td key={dt} num cls="bg-amber-50">{q > 0 ? n(q) : '—'}</Td>;
                    })}
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="text-[11px] text-gray-500">
        集計対象 {activeRows.length} / 全 {data.skus.length} SKU{excluded.size > 0 && `（${excluded.size}件を集計対象外として最下行にグレー表示中・✔を外すと復活）`}
      </div>
    </div>
  );
}

function Field({ label, value, mono, span }: { label: string; value: string; mono?: boolean; span?: boolean }) {
  return (
    <div className={span ? 'col-span-2' : ''}>
      <span className="text-[11px] text-gray-400">{label}</span>
      <div className={`font-medium text-gray-800 ${mono ? 'font-mono' : ''}`}>{value}</div>
    </div>
  );
}
function Th({ children, cls = '' }: { children: React.ReactNode; cls?: string }) {
  return <th className={`px-2 py-1.5 font-semibold border border-gray-200 text-center ${cls}`}>{children}</th>;
}
function Td({ children, num, center, mono, cls = '' }:
  { children: React.ReactNode; num?: boolean; center?: boolean; mono?: boolean; cls?: string }) {
  return (
    <td className={`px-2 py-1 border border-gray-100 ${num ? 'text-right tabular-nums' : ''} ${center ? 'text-center' : ''} ${mono ? 'font-mono' : ''} ${cls}`}>
      {children}
    </td>
  );
}
