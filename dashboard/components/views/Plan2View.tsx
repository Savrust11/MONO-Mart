'use client';

import { useState, useEffect, useCallback } from 'react';
import { CircularProgress } from '../CircularProgress';

type MetricFormat = 'int' | 'yen' | 'pct';
interface Plan2Metric { key: string; label: string; format: MetricFormat; yearly: (number | null)[]; monthly: (number | null)[]; daily: (number | null)[]; }
interface Plan2SkuRow { color_name: string | null; size: string | null; sku_code: string | null; yearly: number[]; daily: number[]; monthly: number[]; }
interface Plan2 {
  product_code: string; start: string; end: string;
  years: string[]; months: string[]; days: string[];
  metrics: Plan2Metric[]; skuPivot: Plan2SkuRow[]; note: string;
}

function fmt(v: number | null, f: MetricFormat): string {
  if (v == null) return '—';
  if (f === 'pct') return `${v}%`;
  return v.toLocaleString('ja-JP');
}

// ピボットの「葉」列。年(計)/月(計)/日 のいずれか。idx は yearly/monthly/daily への添字。
type Leaf = { type: 'year' | 'month' | 'day'; y: string; m?: string; d?: string; idx: number };

export function Plan2View({ code, start, end, excluded }:
  { code: string; start: string; end: string; excluded: Set<string> }) {
  const exParam = [...excluded].join(',');  // Plan1で集計不要にしたSKU→品番合計から除外
  const [data, setData] = useState<Plan2 | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(true);  // 初期true＝照会時に即進捗表示
  const [error, setError] = useState<string | null>(null);
  const [outMsg, setOutMsg] = useState<string | null>(null);
  const [outUrl, setOutUrl] = useState<string | null>(null);
  const [expandedYears, setExpandedYears] = useState<Set<string>>(new Set());
  const [expandedMonths, setExpandedMonths] = useState<Set<string>>(new Set());

  const toSheet = useCallback(async () => {
    setOutMsg('スプシ出力中…'); setOutUrl(null);
    try {
      // 統合出力: 1ファイルに「期間集計＋推移集計」の2タブを作成（顧客要望）。
      const res = await fetch(`/api/order-plan/to-sheet?product_code=${encodeURIComponent(code)}&start=${start}&end=${end}${exParam ? `&exclude=${encodeURIComponent(exParam)}` : ''}`, { method: 'POST' });
      const j = await res.json();
      if (res.ok) { setOutMsg(`✓ 新規スプレッドシート「${j.filename}」を作成しました（${j.rows}行）`); setOutUrl(j.url || null); }
      else setOutMsg(`エラー: ${j.error || '失敗'}`);
    } catch (e) { setOutMsg('通信エラー: ' + String(e)); }
  }, [code, start, end, exParam]);

  const run = useCallback(async () => {
    setBusy(true); setLoading(true); setError(null);
    try {
      const res = await fetch(`/api/order-plan2?product_code=${encodeURIComponent(code)}&start=${start}&end=${end}${exParam ? `&exclude=${encodeURIComponent(exParam)}` : ''}`);
      const j = await res.json();
      if (!res.ok) { setError(j.error || '取得に失敗しました'); setData(null); }
      else setData(j as Plan2);
    } catch (e) { setError('通信エラー: ' + String(e)); setData(null); }
    finally { setLoading(false); }
  }, [code, start, end, exParam]);  // 集計不要が変わったら再集計（品番合計を除外で再計算）
  useEffect(() => { run(); }, [run]);

  // 既定: 最新の年だけ展開（直近の月が見える状態）。読み込みのたびに初期化。
  useEffect(() => {
    if (data?.years?.length) setExpandedYears(new Set([data.years[data.years.length - 1]]));
    setExpandedMonths(new Set());
  }, [data?.product_code, data?.years]);

  if (busy) return <CircularProgress active={loading} label="推移集計を集計中" onDone={() => setBusy(false)} />;
  if (error) return <div className="m-4 bg-rose-50 border border-rose-200 rounded p-3 text-xs text-rose-700">{error}</div>;
  if (!data) return null;

  // ── ピボット列ツリー構築 ───────────────────────────────────────────────
  const monthsByYear: Record<string, string[]> = {};
  for (const m of data.months) (monthsByYear[m.slice(0, 4)] ??= []).push(m);
  const daysByMonth: Record<string, string[]> = {};
  for (const d of data.days) (daysByMonth[d.slice(0, 7)] ??= []).push(d);
  const monthIndex = new Map(data.months.map((m, i) => [m, i]));
  const dayIndex = new Map(data.days.map((d, i) => [d, i]));

  const leaves: Leaf[] = [];
  data.years.forEach((y, yi) => {
    if (!expandedYears.has(y)) { leaves.push({ type: 'year', y, idx: yi }); return; }
    for (const m of monthsByYear[y] ?? []) {
      if (!expandedMonths.has(m)) { leaves.push({ type: 'month', y, m, idx: monthIndex.get(m) ?? 0 }); continue; }
      for (const d of daysByMonth[m] ?? []) leaves.push({ type: 'day', y, m, d, idx: dayIndex.get(d) ?? 0 });
    }
  });

  const toggleYear = (y: string) => setExpandedYears((p) => { const n = new Set(p); n.has(y) ? n.delete(y) : n.add(y); return n; });
  const toggleMonth = (m: string) => setExpandedMonths((p) => { const n = new Set(p); n.has(m) ? n.delete(m) : n.add(m); return n; });

  const mVal = (m: Plan2Metric, lf: Leaf) => lf.type === 'year' ? m.yearly[lf.idx] : lf.type === 'month' ? m.monthly[lf.idx] : m.daily[lf.idx];
  const sVal = (s: Plan2SkuRow, lf: Leaf) => lf.type === 'year' ? s.yearly[lf.idx] : lf.type === 'month' ? s.monthly[lf.idx] : s.daily[lf.idx];

  // 年グループ（ヘッダ1行目）: 連続する同一 year の葉をまとめる
  const yearGroups: { y: string; span: number }[] = [];
  for (const lf of leaves) {
    const last = yearGroups[yearGroups.length - 1];
    if (last && last.y === lf.y) last.span++; else yearGroups.push({ y: lf.y, span: 1 });
  }
  // 月グループ（ヘッダ2行目）: 年が畳まれていれば空1セル、展開なら月ごとにまとめる
  const monthGroups: { y: string; m?: string; span: number; collapsedYear: boolean }[] = [];
  for (const lf of leaves) {
    if (lf.type === 'year') { monthGroups.push({ y: lf.y, span: 1, collapsedYear: true }); continue; }
    const last = monthGroups[monthGroups.length - 1];
    if (last && !last.collapsedYear && last.m === lf.m) last.span++;
    else monthGroups.push({ y: lf.y, m: lf.m, span: 1, collapsedYear: false });
  }

  const colCount = leaves.length;
  const Tri = ({ open }: { open: boolean }) => <span className="inline-block w-3 text-[9px] text-gray-500">{open ? '▼' : '▶'}</span>;

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-[11px] text-gray-500">年/月/日 ピボット（年・月の見出しをクリックで +/− 展開）</span>
        {data.note && <span className="text-[11px] text-amber-700">{data.note}</span>}
        <div className="ml-auto flex items-center gap-2">
          <button onClick={() => setExpandedYears(new Set(data.years))}
            className="px-2 py-1 text-[11px] border border-gray-300 rounded hover:bg-gray-50">全月展開</button>
          <button onClick={() => { setExpandedYears(new Set()); setExpandedMonths(new Set()); }}
            className="px-2 py-1 text-[11px] border border-gray-300 rounded hover:bg-gray-50">全折り畳み</button>
          <button onClick={toSheet}
            className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded text-[12px]">スプシ出力</button>
          {outMsg && <span className="text-[11px] text-gray-700">{outMsg}</span>}
          {outUrl && (
            <a href={outUrl} target="_blank" rel="noopener noreferrer"
              className="text-[11px] text-teal-700 underline hover:text-teal-800 font-medium">📊 スプレッドシートを開く</a>
          )}
        </div>
      </div>

      {/* 顧客#12: 品番合計（指標）とSKU別を「1つの表」に統合し、列を完全連動・同一スクロールに */}
      <div className="bg-white border border-gray-200 rounded overflow-x-auto">
        <table className="text-[12px] whitespace-nowrap border-collapse table-fixed">
          <colgroup>
            <col className="w-[92px]" /><col className="w-[56px]" /><col className="w-[110px]" />
            {leaves.map((_, i) => <col key={i} className="w-[84px]" />)}
          </colgroup>
          <thead>
            {/* 年 */}
            <tr className="bg-gray-100 text-gray-700">
              <th colSpan={3} rowSpan={2} className="px-2 py-1.5 border border-gray-200 text-left sticky left-0 bg-gray-100 z-20">品番合計 / SKU</th>
              {yearGroups.map((g) => (
                <th key={g.y} colSpan={g.span} onClick={() => toggleYear(g.y)}
                  className="px-2 py-1 border border-gray-200 text-center cursor-pointer select-none hover:bg-gray-200 font-semibold">
                  <Tri open={expandedYears.has(g.y)} />{g.y}年
                </th>
              ))}
            </tr>
            {/* 月 */}
            <tr className="bg-gray-50 text-gray-600">
              {monthGroups.map((g, gi) => g.collapsedYear ? (
                <th key={`y${gi}`} className="px-2 py-1 border border-gray-200 text-center text-gray-300">—</th>
              ) : (
                <th key={`m${g.m}`} colSpan={g.span} onClick={() => toggleMonth(g.m!)}
                  className="px-2 py-1 border border-gray-200 text-center cursor-pointer select-none hover:bg-gray-100">
                  <Tri open={expandedMonths.has(g.m!)} />{g.m!.slice(5)}月
                </th>
              ))}
            </tr>
            {/* 葉（カラー/サイズ/SKU品番 ＋ 年計/月計/日） */}
            <tr className="bg-white text-gray-500">
              <th className="px-2 py-1 border border-gray-200 text-left sticky left-0 bg-white z-20">カラー</th>
              <th className="px-2 py-1 border border-gray-200 text-left sticky left-[92px] bg-white z-20">サイズ</th>
              <th className="px-2 py-1 border border-gray-200 text-left sticky left-[148px] bg-white z-20">SKU品番</th>
              {leaves.map((lf, i) => (
                <th key={i} className="px-2 py-1 border border-gray-200 text-right font-normal text-[11px]">
                  {lf.type === 'year' ? '年計' : lf.type === 'month' ? '月計' : `${lf.d!.slice(8)}日`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* ── 品番合計（指標）── */}
            <tr className="bg-indigo-50 text-indigo-800">
              <td colSpan={3 + colCount} className="px-2 py-1 border border-gray-100 font-semibold">■ 品番合計（指標）</td>
            </tr>
            {data.metrics.map((m) => (
              <tr key={m.key} className="border-b border-gray-50 hover:bg-gray-50">
                <td colSpan={3} className="px-2 py-1 border border-gray-100 font-medium text-gray-700 sticky left-0 bg-white z-10">{m.label}</td>
                {leaves.map((lf, i) => (
                  <td key={i} className="px-2 py-1 border border-gray-100 text-right tabular-nums">{fmt(mVal(m, lf), m.format)}</td>
                ))}
              </tr>
            ))}
            {/* ── SKU別 販売数 ── */}
            <tr className="bg-teal-50 text-teal-800">
              <td colSpan={3 + colCount} className="px-2 py-1 border border-gray-100 font-semibold">■ SKU別 販売数</td>
            </tr>
            {data.skuPivot.length === 0 && (
              <tr><td colSpan={3 + colCount} className="px-3 py-3 text-gray-400">販売実績のあるSKUがありません。</td></tr>
            )}
            {data.skuPivot.map((s, ri) => {
              const ex = excluded.has(s.sku_code ?? '');  // 集計不要SKU（Plan1で✔）→グレー＋品番合計から除外済み
              return (
              <tr key={s.sku_code ?? ri} className={`border-b border-gray-50 ${ex ? 'bg-gray-100 text-gray-400 line-through' : 'hover:bg-gray-50'}`}>
                <td className={`px-2 py-1 border border-gray-100 sticky left-0 z-10 truncate ${ex ? 'bg-gray-100' : 'bg-white'}`}>{s.color_name ?? '—'}</td>
                <td className={`px-2 py-1 border border-gray-100 sticky left-[92px] z-10 truncate ${ex ? 'bg-gray-100' : 'bg-white'}`}>{s.size ?? '—'}</td>
                <td className={`px-2 py-1 border border-gray-100 font-mono sticky left-[148px] z-10 truncate ${ex ? 'bg-gray-100' : 'bg-white'}`}>{s.sku_code ?? '—'}{ex && ' ⊘'}</td>
                {leaves.map((lf, i) => {
                  const v = sVal(s, lf);
                  return <td key={i} className={`px-2 py-1 border border-gray-100 text-right tabular-nums ${!ex && v === 0 ? 'text-gray-300' : ''}`}>{v.toLocaleString('ja-JP')}</td>;
                })}
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
