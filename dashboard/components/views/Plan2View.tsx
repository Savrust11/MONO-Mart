'use client';

import { useState, useEffect, useCallback } from 'react';
import { LoadingProgress } from '../LoadingProgress';

type MetricFormat = 'int' | 'yen' | 'pct';
interface Plan2Metric { key: string; label: string; format: MetricFormat; monthly: (number | null)[]; daily: (number | null)[]; }
interface Plan2SkuRow { color_name: string | null; size: string | null; sku_code: string | null; daily: number[]; monthly: number[]; }
interface Plan2 {
  product_code: string; start: string; end: string;
  months: string[]; days: string[];
  metrics: Plan2Metric[]; skuPivot: Plan2SkuRow[]; note: string;
}

function fmt(v: number | null, f: MetricFormat): string {
  if (v == null) return '—';
  if (f === 'pct') return `${v}%`;
  if (f === 'yen') return v.toLocaleString('ja-JP');
  return v.toLocaleString('ja-JP');
}
const md = (d: string) => d.slice(5); // 'MM-DD'

export function Plan2View({ code, start, end }: { code: string; start: string; end: string }) {
  const [data, setData] = useState<Plan2 | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false); // 進捗バー表示（完了アニメ含む）
  const [error, setError] = useState<string | null>(null);
  const [grain, setGrain] = useState<'monthly' | 'daily'>('monthly');
  const [outMsg, setOutMsg] = useState<string | null>(null);
  const [outUrl, setOutUrl] = useState<string | null>(null);

  const toSheet = useCallback(async () => {
    setOutMsg('スプシ出力中…'); setOutUrl(null);
    try {
      const res = await fetch(`/api/order-plan2/to-sheet?product_code=${encodeURIComponent(code)}&start=${start}&end=${end}`, { method: 'POST' });
      const j = await res.json();
      if (res.ok) { setOutMsg(`✓ スプレッドシート「案2」タブに出力しました（${j.rows}行）`); setOutUrl(j.url || null); }
      else setOutMsg(`エラー: ${j.error || '失敗'}`);
    } catch (e) { setOutMsg('通信エラー: ' + String(e)); }
  }, [code, start, end]);

  const run = useCallback(async () => {
    setBusy(true); setLoading(true); setError(null);
    try {
      const res = await fetch(`/api/order-plan2?product_code=${encodeURIComponent(code)}&start=${start}&end=${end}`);
      const j = await res.json();
      if (!res.ok) { setError(j.error || '取得に失敗しました'); setData(null); }
      else setData(j as Plan2);
    } catch (e) { setError('通信エラー: ' + String(e)); setData(null); }
    finally { setLoading(false); }
  }, [code, start, end]);
  useEffect(() => { run(); }, [run]);

  if (busy) return <LoadingProgress active={loading} label="案2（時系列）を集計中" onDone={() => setBusy(false)} />;
  if (error) return <div className="m-4 bg-rose-50 border border-rose-200 rounded p-3 text-xs text-rose-700">{error}</div>;
  if (!data) return null;

  const cols = grain === 'monthly' ? data.months : data.days;
  const colLabel = (c: string) => (grain === 'monthly' ? c : md(c));
  const valAt = (m: Plan2Metric, i: number) => (grain === 'monthly' ? m.monthly[i] : m.daily[i]);

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-3">
        <div className="inline-flex rounded border border-gray-300 overflow-hidden text-[12px]">
          {(['monthly', 'daily'] as const).map((g) => (
            <button key={g} onClick={() => setGrain(g)}
              className={`px-3 py-1 ${grain === g ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}>
              {g === 'monthly' ? '月次' : '日次'}
            </button>
          ))}
        </div>
        <span className="text-[11px] text-gray-500">期間 {data.start} 〜 {data.end}（{cols.length}列）</span>
        {data.note && <span className="text-[11px] text-amber-700">{data.note}</span>}
        {/* 出力＝スプシ確定（№13）。CSVは確定外のため非表示・APIは残置 */}
        <div className="ml-auto flex items-center gap-2">
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
      </div>

      {/* 指標 × 時系列 */}
      <div className="bg-white border border-gray-200 rounded overflow-x-auto">
        <table className="text-[12px] whitespace-nowrap border-collapse">
          <thead>
            <tr className="bg-gray-100 text-gray-600">
              <th className="px-2 py-1.5 border border-gray-200 text-left sticky left-0 bg-gray-100 z-10">指標</th>
              {cols.map((c) => <th key={c} className="px-2 py-1.5 border border-gray-200 text-right">{colLabel(c)}</th>)}
            </tr>
          </thead>
          <tbody>
            {data.metrics.map((m) => (
              <tr key={m.key} className="border-b border-gray-50 hover:bg-gray-50">
                <td className="px-2 py-1 border border-gray-100 font-medium text-gray-700 sticky left-0 bg-white z-10">{m.label}</td>
                {cols.map((_, i) => (
                  <td key={i} className="px-2 py-1 border border-gray-100 text-right tabular-nums">{fmt(valAt(m, i), m.format)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* SKU × 時系列 販売数ピボット（月次/日次は上のトグルに連動） */}
      <div>
        <div className="text-[12px] font-semibold text-gray-700 mb-1">
          SKU別 販売数（{grain === 'monthly' ? '月次' : '日次'}）
        </div>
        <div className="bg-white border border-gray-200 rounded overflow-x-auto">
          <table className="text-[12px] whitespace-nowrap border-collapse">
            <thead>
              <tr className="bg-gray-100 text-gray-600">
                <th className="px-2 py-1.5 border border-gray-200 text-left sticky left-0 bg-gray-100 z-10">カラー</th>
                <th className="px-2 py-1.5 border border-gray-200 text-left">サイズ</th>
                <th className="px-2 py-1.5 border border-gray-200 text-left">SKU品番</th>
                {cols.map((c) => <th key={c} className="px-2 py-1.5 border border-gray-200 text-right">{colLabel(c)}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.skuPivot.length === 0 && (
                <tr><td colSpan={3 + cols.length} className="px-3 py-3 text-gray-400">販売実績のあるSKUがありません。</td></tr>
              )}
              {data.skuPivot.map((s, ri) => {
                const series = grain === 'monthly' ? s.monthly : s.daily;
                return (
                  <tr key={s.sku_code ?? ri} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="px-2 py-1 border border-gray-100 sticky left-0 bg-white z-10">{s.color_name ?? '—'}</td>
                    <td className="px-2 py-1 border border-gray-100">{s.size ?? '—'}</td>
                    <td className="px-2 py-1 border border-gray-100 font-mono">{s.sku_code ?? '—'}</td>
                    {series.map((v, i) => (
                      <td key={i} className={`px-2 py-1 border border-gray-100 text-right tabular-nums ${v === 0 ? 'text-gray-300' : ''}`}>{v.toLocaleString('ja-JP')}</td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
