'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { CircularProgress } from '../CircularProgress';

// 遅延付きツールチップ。マウスを乗せて少し経つと、整形した内容をふわっと表示する。
function HoverTip({ children, title, rows, accent }:
  { children: React.ReactNode; title: string; rows: [string, string][]; accent: 'indigo' | 'amber' }) {
  const [show, setShow] = useState(false);     // 表示するか
  const [render, setRender] = useState(false); // DOMに載せるか（フェード後に外す）
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const move = (e: React.MouseEvent) => setPos({ x: e.clientX, y: e.clientY });
  const enter = (e: React.MouseEvent) => {
    move(e);
    timer.current = setTimeout(() => { setRender(true); requestAnimationFrame(() => setShow(true)); }, 450);
  };
  const leave = () => {
    if (timer.current) clearTimeout(timer.current);
    setShow(false); setTimeout(() => setRender(false), 150);
  };
  const head = accent === 'amber' ? 'text-amber-700' : 'text-indigo-700';
  const bar = accent === 'amber' ? 'bg-amber-400' : 'bg-indigo-400';
  // 負マージン+パディングでセルのpx-1 py-1まで覆い、背景全体をホバー対象にする
  return (
    <span onMouseEnter={enter} onMouseMove={move} onMouseLeave={leave}
      className="cursor-help block w-full h-full -mx-1 -my-1 px-1 py-1">
      {children}
      {render && (
        <div
          style={{ position: 'fixed', left: pos.x + 14, top: pos.y + 16, zIndex: 60 }}
          className={`pointer-events-none transition-opacity duration-150 ${show ? 'opacity-100' : 'opacity-0'}`}
        >
          <div className="bg-white text-gray-800 text-[12px] rounded-lg shadow-xl border border-gray-200 overflow-hidden w-64">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-100">
              <span className={`inline-block w-1.5 h-4 rounded-sm ${bar}`} />
              <span className={`font-bold ${head}`}>{title}</span>
            </div>
            <div className="px-3 py-2 space-y-1.5">
              {rows.map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <span className="text-gray-400 w-16 shrink-0">{k}</span>
                  <span className="font-medium text-gray-700 leading-snug">{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </span>
  );
}

// 発注管理表「期間集計」(旧:案1・SKU別明細ビュー)。/api/order-plan1 のレスポンス型。
interface Plan1Sku {
  color_name: string | null; size: string | null; sku_code: string | null;
  retail_price: number | null; sale_type: string | null; favorites: number | null;
  sales_qty: number; period_rev: number; period_cost: number; period_lst: number; fku_share: number | null;
  last_order_date: string | null; last_cost: number | null; latest_avg_cost: number | null;
  last_arrival_date: string | null; current_stock: number;
  recommended_qty: number | null; recommended_provisional: boolean; confirmed_qty: null;
  corrected_velo: number; velo_basis: 'actual' | 'simulated';
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
    created_at: string; data_asof: string; start: string; end: string; product_code: string;
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

export function Plan1View({ code, start, end, totalQty = 0, cutoffN = 180,
  excluded, onToggleExclude, onResetExclude }:
  { code: string; start: string; end: string; totalQty?: number; cutoffN?: number;
    excluded: Set<string>; onToggleExclude: (sk: string) => void; onResetExclude: () => void }) {
  const [data, setData] = useState<Plan1 | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(true); // 進捗（完了アニメ含む）。初期true＝即表示
  const [error, setError] = useState<string | null>(null);
  // 集計不要は親(ProductDashboardView)で保持＝期間集計/推移集計で共有・タブ切替でも維持。
  const [outMsg, setOutMsg] = useState<string | null>(null);
  const [outUrl, setOutUrl] = useState<string | null>(null);
  // #1 確定発注数: 手入力欄（SKU品番ごと）。既定は空欄、未入力時は推奨発注数をプレースホルダ表示。
  const [confirmed, setConfirmed] = useState<Record<string, string>>({});

  const toSheet = useCallback(async () => {
    setOutMsg('スプシ出力中…'); setOutUrl(null);
    try {
      const ex = [...excluded].join(',');
      // 統合出力: 1ファイルに「期間集計＋推移集計」の2タブを作成（顧客要望）。
      const res = await fetch(`/api/order-plan/to-sheet?product_code=${encodeURIComponent(code)}&start=${start}&end=${end}${ex ? `&exclude=${encodeURIComponent(ex)}` : ''}`, { method: 'POST' });
      const j = await res.json();
      if (res.ok) { setOutMsg(`✓ 新規スプレッドシート「${j.filename}」を作成しました（${j.rows}行）`); setOutUrl(j.url || null); }
      else setOutMsg(`エラー: ${j.error || '失敗'}`);
    } catch (e) { setOutMsg('通信エラー: ' + String(e)); }
  }, [code, start, end, excluded]);

  const run = useCallback(async () => {
    setBusy(true); setLoading(true); setError(null);
    try {
      const res = await fetch(
        `/api/order-plan1?product_code=${encodeURIComponent(code)}&start=${start}&end=${end}&n=${cutoffN}`);
      const j = await res.json();
      if (!res.ok) { setError(j.error || '取得に失敗しました'); setData(null); }
      else { setData(j as Plan1); }
    } catch (e) { setError('通信エラー: ' + String(e)); setData(null); }
    finally { setLoading(false); }
  }, [code, start, end]);

  useEffect(() => { run(); }, [run]);

  if (busy) return <CircularProgress active={loading} label="期間集計を集計中" onDone={() => setBusy(false)} />;
  if (error) return <div className="m-4 bg-rose-50 border border-rose-200 rounded p-3 text-xs text-rose-700">{error}</div>;
  if (!data) return null;

  const h = data.header;
  const isExcluded = (s: Plan1Sku) => excluded.has(s.sku_code ?? '');
  // 顧客#5/#6: 「集計不要」は行を消さず最下行へ移動・グレー表示し、いつでも✔を外して復活可能にする。
  //   集計（配分・入荷列）は除外SKUを含めない（=activeRows）。
  const rows = [...data.skus].sort((a, b) => Number(isExcluded(a)) - Number(isExcluded(b)));
  const activeRows = data.skus.filter((s) => !isExcluded(s));
  const toggle = (sk: string) => onToggleExclude(sk);

  // 顧客#1: 品番合計から「集計対象外SKU」を除外。除外ゼロ時はサーバ値（厳密一致）、除外時のみ再計算。
  const round1 = (x: number) => Math.round(x * 10) / 10;
  const sumRev = activeRows.reduce((a, s) => a + (s.period_rev || 0), 0);  // 合計販売額（実売上）
  const hdr = excluded.size === 0
    ? { qty: h.total_qty, lst: h.total_list_amount, margin: h.total_margin_pct, discount: h.total_discount_pct, rev: sumRev }
    : (() => {
        const rev = sumRev;
        const cost = activeRows.reduce((a, s) => a + (s.period_cost || 0), 0);
        const lst = activeRows.reduce((a, s) => a + (s.period_lst || 0), 0);
        const qty = activeRows.reduce((a, s) => a + (s.sales_qty || 0), 0);
        return {
          qty,
          lst: lst || null,
          margin: rev > 0 ? round1((rev - cost) / rev * 100) : null,
          discount: lst > 0 ? round1((1 - rev / lst) * 100) : null,
          rev,
        };
      })();
  const totalLabel = excluded.size > 0 ? `（集計対象 ${activeRows.length}/${data.skus.length} SKU）` : '';

  // 総数指定→SKU配分（顧客回答 2026: 「不足ベース」と「構成比ベース」を両方表示）。
  //  ・不足ベース   = 各SKUの不足(推奨発注数=需要−残在庫)の比率で総数を配分。
  //                   →定番カラー等は売れていても在庫が充足なら配分が小さくなる（顧客指摘どおり）。
  //  ・構成比ベース = 直近30日販売数の構成比で総数を配分（純粋な人気度）。
  //  端数は最大剰余法で総数に厳密一致させる。
  const distribute = (weights: number[]): number[] => {
    const sumW = weights.reduce((a, b) => a + b, 0);
    const raw = weights.map((wi) => (sumW > 0 ? totalQty * (wi / sumW) : totalQty / weights.length));
    const floor = raw.map(Math.floor);
    let residual = totalQty - floor.reduce((a, b) => a + b, 0);
    raw.map((r, i) => ({ i, f: r - Math.floor(r) })).sort((a, b) => b.f - a.f)
      .forEach(({ i }) => { if (residual-- > 0) floor[i] += 1; });
    return floor;
  };
  const sum = (arr: number[]) => arr.reduce((a, b) => a + b, 0);
  const allocShort: Record<string, number> = {};   // 不足ベース
  const allocSales: Record<string, number> = {};   // 構成比ベース
  // オフシーズン判定: 直近販売がほぼ無く、全SKUの推奨発注数が0（＝不足が出ず均等割りに落ちる）。
  //   顧客指摘(BLEjk605): シーズン外で全色500均等になり在庫差が出ない。
  //   → オフシーズンは「指定した実績期間」を基準にし、在庫も考慮する別ロジックに切替える。
  let offSeason = false;
  if (totalQty > 0 && activeRows.length) {
    const recW = activeRows.map((s) => Math.max(s.recommended_qty || 0, 0));
    // ── 不足ベースの重み ──
    let shortWeights = recW;
    if (sum(recW) === 0) {
      offSeason = true;
      // オフシーズン: 指定期間の実績 − フリー在庫 ＝「期間不足」（在庫が潤沢な色ほど小さく）
      const periodShort = activeRows.map((s) => Math.max((s.sales_qty || 0) - (s.free_stock || 0), 0));
      shortWeights = sum(periodShort) > 0
        ? periodShort
        : activeRows.map((s) => Math.max(s.sales_qty || 0, 0)); // それも全0なら指定期間の販売構成比
    }
    // ── 構成比ベースの重み（オフシーズンは直近30日が0なので指定期間実績を使う）──
    const l30W = activeRows.map((s) => Math.max(s.l30_qty || 0, 0));
    const salesWeights = sum(l30W) > 0 ? l30W : activeRows.map((s) => Math.max(s.sales_qty || 0, 0));

    const shortW = distribute(shortWeights);
    const salesW = distribute(salesWeights);
    activeRows.forEach((s, i) => {
      allocShort[s.sku_code ?? ''] = shortW[i];
      allocSales[s.sku_code ?? ''] = salesW[i];
    });
  }

  // #3 入荷山を「日付ごと」に整列（左詰めをやめる）。全SKUの入荷予定日を集めて列に並べ、
  //    各SKUの入荷数量を該当する日付列の下に配置する。
  const arrivalDates: string[] = (() => {
    const set = new Set<string>();
    for (const s of activeRows) for (const dt of [s.arr1_date, s.arr2_date, s.arr3_date]) if (dt) set.add(dt);
    return Array.from(set).sort();
  })();
  // テーブル総列数（除外行の colSpan 用）。先頭4列（集計不要/カラー/サイズ/SKU品番）以外をまとめる。
  const COLS = 16 + (totalQty > 0 ? 2 : 0) + 4 + 4 + 3 + 1 + Math.max(1, arrivalDates.length);  // +1=入荷残合計列
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
  const arrTotalOf = (s: Plan1Sku): number => (s.arr1_qty ?? 0) + (s.arr2_qty ?? 0) + (s.arr3_qty ?? 0);

  return (
    <div className="p-4 space-y-4">
      {/* ヘッダ（品番サマリ） */}
      <div className="bg-white border border-gray-200 rounded p-3 grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-1 text-[13px]">
        <Field label="品番" value={h.product_code} mono />
        <Field label="ショップ" value={h.shop ?? '—'} />
        <Field label="ブランド" value={h.brand ?? '—'} />
        <Field label="作成日" value={d(h.created_at)} />
        <Field label="データ基準日" value={d(h.data_asof)} />
        <Field label="商品名" value={h.product_name ?? '—'} span />
        <Field label="商品タイプ" value={`${h.item_type_parent ?? '—'} / ${h.item_type_child ?? '—'}`} />
        <Field label="集計期間" value={`${d(h.start)} 〜 ${d(h.end)}`} />
        <Field label="累計レビュー" value={`${n(h.review_count)}件 / ${h.review_avg ?? '—'}点`} />
        <Field label={`合計粗利率${totalLabel}`} value={hdr.margin == null ? '—' : `${hdr.margin.toFixed(1)}%`}
          warn={hdr.margin != null && hdr.margin < 0} badge="原価割れ" />
        <Field label={`合計値引率${totalLabel}`} value={hdr.discount == null ? '—' : `${hdr.discount.toFixed(1)}%`} />
        <Field label={`合計販売額${totalLabel}`} value={n(hdr.rev, '円')} />
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
                    {/* 顧客要望: 色は見えるように（グレースケール/塗りつぶしをやめ）、除外印は「斜線1本」だけ */}
                    <div className="relative h-24 w-24">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={im.url} alt={im.color}
                        className="h-24 w-24 object-cover rounded border border-gray-300" />
                      <div className="absolute inset-0 rounded pointer-events-none"
                        style={{ background: 'linear-gradient(to top right, transparent calc(50% - 1.5px), rgba(220,38,38,0.85) calc(50% - 1.5px), rgba(220,38,38,0.85) calc(50% + 1.5px), transparent calc(50% + 1.5px))' }} />
                    </div>
                    <figcaption className="text-[10px] text-gray-500 mt-1 w-24 truncate">{im.color}</figcaption>
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

      {/* 集計対象外（集計不要✔）の件数と一括復活。最下部のグレー行を探さなくても1クリックで戻せる。*/}
      {excluded.size > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded px-3 py-2 text-[12px]">
          <span className="text-amber-800">
            <b>{excluded.size}件</b>のSKUを「集計対象外」にしています（表の最下部にグレーで表示・推移集計の品番合計からも除外）。
          </span>
          <button onClick={onResetExclude}
            className="ml-auto px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded text-[12px] font-medium">
            すべて集計に戻す
          </button>
        </div>
      )}

      {/* 推奨発注数の色分け凡例（顧客・欠品補正: 実数とシミュレーションを判別）*/}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500">
        <span className="font-medium text-gray-600">推奨発注数の色:</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3.5 h-3.5 rounded-sm bg-indigo-50 border border-indigo-200" />実数ベース（欠品日を除いた7日平均×季節係数）</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3.5 h-3.5 rounded-sm bg-amber-50 border border-amber-200" />シミュレーション（▲＝7日実績なし→経過係数で推定）</span>
      </div>

      {/* SKU別明細（横スクロール） */}
      <div className="bg-white border border-gray-200 rounded overflow-x-auto">
        <table className="text-[12px] whitespace-nowrap border-collapse">
          <thead>
            <tr className="text-gray-600 text-[11px]">
              <th colSpan={16 + (totalQty > 0 ? 2 : 0)} className="px-2 py-1 border border-gray-200 bg-gray-50 text-left">▼指定期間合計</th>
              <th colSpan={4} className="px-2 py-1 border border-gray-200 bg-sky-100 text-center">▼直近7日</th>
              <th colSpan={4} className="px-2 py-1 border border-gray-200 bg-teal-100 text-center">▼直近30日</th>
              <th colSpan={3} className="px-2 py-1 border border-gray-200 bg-violet-100 text-center">フリー在庫・予約</th>
              <th colSpan={1 + Math.max(1, arrivalDates.length)} className="px-2 py-1 border border-gray-200 bg-amber-100 text-center">入荷残（合計・日付別）</th>
            </tr>
            <tr className="bg-gray-100 text-gray-600">
              <Th>集計不要</Th><Th>カラー</Th><Th>サイズ</Th><Th>SKU品番</Th><Th>上代</Th><Th>販売タイプ</Th>
              <Th>お気に入り</Th><Th>販売数</Th><Th>FKU構成</Th><Th>前回発注日</Th><Th>前回原価</Th>
              <Th>最新加重平均原価</Th><Th>最終入荷日</Th><Th>現在庫数</Th>
              <Th cls="bg-indigo-50">推奨発注数</Th><Th cls="bg-indigo-50">確定発注数</Th>
              {totalQty > 0 && <Th cls="bg-indigo-100" title={offSeason
                ? 'オフシーズン: 直近実績が無いため、指定した実績期間の販売−フリー在庫（在庫考慮）で配分'
                : '総数を各SKUの不足(需要−残在庫)の比率で配分。在庫が充足な色は小さくなる'}>
                配分数（不足ベース）{offSeason && <span className="ml-0.5 text-[9px] text-amber-700">▲季</span>}</Th>}
              {totalQty > 0 && <Th cls="bg-purple-100" title={offSeason
                ? 'オフシーズン: 直近30日が無いため、指定した実績期間の販売構成比で配分'
                : '総数を直近30日の販売構成比で配分（人気度ベース）'}>配分数（構成比）</Th>}
              <Th cls="bg-sky-50">7日販売数</Th><Th cls="bg-sky-50">日販平均</Th><Th cls="bg-sky-50">在庫日数</Th><Th cls="bg-sky-50">完売想定日</Th>
              <Th cls="bg-teal-50">30日販売数</Th><Th cls="bg-teal-50">日販中央値</Th><Th cls="bg-teal-50">在庫日数</Th><Th cls="bg-teal-50">完売想定日</Th>
              <Th cls="bg-violet-50">フリー在庫数</Th><Th cls="bg-violet-50">フリー在庫日数</Th><Th cls="bg-violet-50">予約未処理</Th>
              <Th cls="bg-amber-100 font-bold">入荷残合計</Th>
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
                <Td num cls={`font-semibold ${s.velo_basis === 'simulated' ? 'bg-amber-50 text-amber-700' : 'bg-indigo-50 text-indigo-800'}`}>
                  <HoverTip
                    accent={s.velo_basis === 'simulated' ? 'amber' : 'indigo'}
                    title={s.velo_basis === 'simulated' ? 'シミュレーション値' : '実数ベース'}
                    rows={s.velo_basis === 'simulated'
                      ? [['区分', 'シミュレーション ▲'], ['補正日販', `${s.corrected_velo} 枚/日`], ['算出', '7日実績なし → ブランド経過係数で定常日販を推定 × 季節係数']]
                      : [['区分', '実数ベース'], ['補正日販', `${s.corrected_velo} 枚/日`], ['算出', '欠品日を除いた通常販売の7日平均 × 季節係数（知りたい週÷実績週）']]}
                  >
                    {n(s.recommended_qty)}{s.velo_basis === 'simulated' && <span className="ml-0.5 text-[9px]">▲</span>}
                  </HoverTip>
                </Td>
                <Td cls="bg-indigo-50">
                  <input type="number" min={0}
                    value={confirmed[s.sku_code ?? ''] ?? ''}
                    placeholder={s.recommended_qty != null ? String(s.recommended_qty) : ''}
                    onChange={(e) => setConfirmed((p) => ({ ...p, [s.sku_code ?? '']: e.target.value }))}
                    className="w-16 px-1 py-0.5 border border-gray-300 rounded text-right text-[12px]" />
                </Td>
                {totalQty > 0 && <Td num cls="bg-indigo-100 font-semibold">{n(allocShort[s.sku_code ?? ''] ?? 0)}</Td>}
                {totalQty > 0 && <Td num cls="bg-purple-100 font-semibold">{n(allocSales[s.sku_code ?? ''] ?? 0)}</Td>}
                <Td num cls="bg-sky-50">{n(s.s7_qty)}</Td><Td num cls="bg-sky-50">{s.s7_daily_avg == null ? '—' : s.s7_daily_avg.toFixed(1)}</Td>
                <Td num cls="bg-sky-50">{s.s7_stock_days == null ? '—' : `${Math.round(s.s7_stock_days)}日`}</Td><Td cls="bg-sky-50">{d(s.s7_sellout)}</Td>
                <Td num cls="bg-teal-50">{n(s.l30_qty)}</Td><Td num cls="bg-teal-50">{s.l30_daily_median ?? '—'}</Td>
                <Td num cls="bg-teal-50">{s.l30_stock_days == null ? '—' : `${Math.round(s.l30_stock_days)}日`}</Td><Td cls="bg-teal-50">{d(s.l30_sellout)}</Td>
                <Td num cls="bg-violet-50">{n(s.free_stock)}</Td>
                <Td num cls="bg-violet-50">{s.free_stock_days == null ? '—' : `${s.free_stock_days}日`}</Td>
                <Td num cls="bg-violet-50">{n(s.reserved_pending)}</Td>
                {(() => { const t = arrTotalOf(s); return (
                  <Td num cls={`font-bold ${t > 0 ? 'bg-amber-100 text-amber-800' : 'bg-amber-50 text-gray-300'}`}>{t > 0 ? n(t) : '—'}</Td>
                ); })()}
                {arrivalDates.length === 0
                  ? <Td num cls="bg-amber-50 text-gray-300">—</Td>
                  : arrivalDates.map((dt) => {
                      const q = arrQtyOf(s, dt);
                      // 入荷がある日は色付け（琥珀）、無い日は薄いグレーの「—」で見やすく
                      return <Td key={dt} num cls={q > 0 ? 'bg-amber-100 text-amber-800 font-semibold' : 'bg-amber-50/40 text-gray-300'}>{q > 0 ? n(q) : '—'}</Td>;
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

function Field({ label, value, mono, span, warn, badge }:
  { label: string; value: string; mono?: boolean; span?: boolean; warn?: boolean; badge?: string }) {
  return (
    <div className={span ? 'col-span-2' : ''}>
      <span className="text-[11px] text-gray-400">{label}</span>
      <div className={`font-medium ${warn ? 'text-rose-600 font-bold' : 'text-gray-800'} ${mono ? 'font-mono' : ''}`}>
        {value}
        {warn && badge && (
          <span className="ml-1.5 px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 text-[10px] font-bold align-middle">{badge}</span>
        )}
      </div>
    </div>
  );
}
function Th({ children, cls = '', title }: { children: React.ReactNode; cls?: string; title?: string }) {
  return <th title={title} className={`px-2 py-1.5 font-semibold border border-gray-200 text-center ${cls}`}>{children}</th>;
}
function Td({ children, num, center, mono, cls = '' }:
  { children: React.ReactNode; num?: boolean; center?: boolean; mono?: boolean; cls?: string }) {
  return (
    <td className={`px-2 py-1 border border-gray-100 ${num ? 'text-right tabular-nums' : ''} ${center ? 'text-center' : ''} ${mono ? 'font-mono' : ''} ${cls}`}>
      {children}
    </td>
  );
}
