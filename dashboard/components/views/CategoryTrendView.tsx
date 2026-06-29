'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ReferenceLine,
} from 'recharts';

type Week = { wk: number; amt2025: number; qty2025: number; amt2026: number; qty2026: number };
type Opt = { parent: string; children: string[] };
type Resp = { options: Opt[]; parent: string; child: string; weeks: Week[]; error?: string };

const yen = (n: number) => `¥${Math.round(n).toLocaleString('ja-JP')}`;
const oku = (n: number) => (n >= 1e8 ? `${(n / 1e8).toFixed(2)}億` : n >= 1e4 ? `${Math.round(n / 1e4).toLocaleString('ja-JP')}万` : `${Math.round(n)}`);

// 顧客要望2026: 商品タイプ親/子・週を選び、52週トレンドをグラフで直感的に見る。
//   ①ピーク週/推移を見て発注・販促のタイミングを定める ②基準週比%で発注数の参考にする。
export function CategoryTrendView() {
  const [options, setOptions] = useState<Opt[]>([]);
  const [parent, setParent] = useState('');
  const [child, setChild] = useState('');           // '' = すべて
  const [metric, setMetric] = useState<'amt' | 'qty'>('amt');  // 売上 or 点数
  const [baseWk, setBaseWk] = useState<number>(1);  // 基準週
  const [weeks, setWeeks] = useState<Week[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 初回: 選択肢取得＋既定の親で表示
  useEffect(() => {
    fetch('/api/category-trend').then((r) => r.json()).then((j: Resp) => {
      setOptions(j.options || []);
      if (j.options?.length) setParent(j.options[0].parent);
    }).catch((e) => setError(String(e)));
  }, []);

  // 親/子 変更で週次トレンド取得
  useEffect(() => {
    if (!parent) return;
    setLoading(true); setError(null);
    const qs = `parent=${encodeURIComponent(parent)}${child ? `&child=${encodeURIComponent(child)}` : ''}`;
    fetch(`/api/category-trend?${qs}`).then((r) => r.json()).then((j: Resp) => {
      if (j.error) { setError(j.error); setWeeks([]); }
      else setWeeks(j.weeks || []);
    }).catch((e) => { setError(String(e)); setWeeks([]); }).finally(() => setLoading(false));
  }, [parent, child]);

  const children = useMemo(() => options.find((o) => o.parent === parent)?.children ?? [], [options, parent]);

  // 親を変えたら子をリセット
  const onParent = (p: string) => { setParent(p); setChild(''); };

  const v25 = (w: Week) => (metric === 'amt' ? w.amt2025 : w.qty2025);
  const v26 = (w: Week) => (metric === 'amt' ? w.amt2026 : w.qty2026);
  const unit = metric === 'amt' ? '売上' : '点数';

  // グラフ用データ
  const chartData = weeks.map((w) => ({ wk: w.wk, '2025年': v25(w), '2026年': v26(w) }));

  // 基準週の2026値（基準週比%の分母）
  const baseVal = useMemo(() => {
    const b = weeks.find((w) => w.wk === baseWk);
    return b ? v26(b) : 0;
  }, [weeks, baseWk, metric]);

  return (
    <div className="px-6 py-4">
      <div className="mb-3">
        <h1 className="text-base font-bold text-gray-900">カテゴリ別 52週トレンド</h1>
        <p className="text-xs text-gray-500">商品タイプ親/子・週を選び、ピーク週や推移をグラフで確認（2025 vs 2026・BigQuery最新）</p>
      </div>

      {/* セレクタ */}
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <label className="text-xs text-gray-600">商品タイプ親
          <select value={parent} onChange={(e) => onParent(e.target.value)}
            className="block mt-0.5 px-2 py-1.5 text-sm border border-gray-300 rounded min-w-[160px]">
            {options.map((o) => <option key={o.parent} value={o.parent}>{o.parent}</option>)}
          </select>
        </label>
        <label className="text-xs text-gray-600">商品タイプ子
          <select value={child} onChange={(e) => setChild(e.target.value)}
            className="block mt-0.5 px-2 py-1.5 text-sm border border-gray-300 rounded min-w-[160px]">
            <option value="">（すべて）</option>
            {children.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="text-xs text-gray-600">指標
          <select value={metric} onChange={(e) => setMetric(e.target.value as 'amt' | 'qty')}
            className="block mt-0.5 px-2 py-1.5 text-sm border border-gray-300 rounded">
            <option value="amt">売上金額</option>
            <option value="qty">販売点数</option>
          </select>
        </label>
        <label className="text-xs text-gray-600">基準週
          <select value={baseWk} onChange={(e) => setBaseWk(Number(e.target.value))}
            className="block mt-0.5 px-2 py-1.5 text-sm border border-gray-300 rounded">
            {weeks.map((w) => <option key={w.wk} value={w.wk}>第{w.wk}週</option>)}
          </select>
        </label>
      </div>

      {loading && <div className="text-sm text-gray-400 py-10 text-center">集計中…</div>}
      {error && <div className="text-sm text-rose-600 py-4">エラー: {error}</div>}

      {!loading && !error && weeks.length > 0 && (
        <>
          {/* グラフ（①ピーク週/推移） */}
          <div className="bg-white border border-gray-200 rounded p-4 mb-4">
            <div className="text-xs font-bold text-gray-700 mb-2">
              {parent}{child ? ` > ${child}` : '（すべての子）'} の週次{unit}推移
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="wk" tick={{ fontSize: 11 }} label={{ value: '週', position: 'insideBottomRight', fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => oku(Number(v))} width={60} />
                <Tooltip formatter={(v: number) => (metric === 'amt' ? yen(v) : `${v.toLocaleString('ja-JP')}点`)} labelFormatter={(l) => `第${l}週`} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <ReferenceLine x={baseWk} stroke="#f59e0b" strokeDasharray="4 4" label={{ value: '基準週', fontSize: 10, fill: '#f59e0b' }} />
                <Line type="monotone" dataKey="2025年" stroke="#94a3b8" strokeWidth={1.5} dot={false} />
                <Line type="monotone" dataKey="2026年" stroke="#6366f1" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* 表（②基準週比% ＋ 実数） */}
          <div className="bg-white border border-gray-200 rounded overflow-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 text-gray-600 sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left">週</th>
                  <th className="px-3 py-2 text-right">2025年 {unit}</th>
                  <th className="px-3 py-2 text-right">2026年 {unit}</th>
                  <th className="px-3 py-2 text-right">前年比</th>
                  <th className="px-3 py-2 text-right">基準週比(2026)</th>
                </tr>
              </thead>
              <tbody>
                {weeks.map((w) => {
                  const a = v25(w), b = v26(w);
                  const yoy = a > 0 ? b / a : null;
                  const pct = baseVal > 0 ? (b / baseVal) * 100 : null;
                  const isBase = w.wk === baseWk;
                  return (
                    <tr key={w.wk} className={`border-t border-gray-100 ${isBase ? 'bg-amber-50' : 'hover:bg-gray-50'}`}>
                      <td className="px-3 py-1.5">第{w.wk}週{isBase && ' ★基準'}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{metric === 'amt' ? yen(a) : a.toLocaleString('ja-JP')}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{metric === 'amt' ? yen(b) : b.toLocaleString('ja-JP')}</td>
                      <td className={`px-3 py-1.5 text-right tabular-nums ${yoy != null && yoy < 1 ? 'text-rose-600' : 'text-emerald-700'}`}>
                        {yoy == null ? '—' : `${Math.round(yoy * 1000) / 10}%`}
                      </td>
                      <td className={`px-3 py-1.5 text-right tabular-nums font-medium ${pct != null && pct < 100 ? 'text-rose-600' : 'text-gray-900'}`}>
                        {pct == null ? '—' : `${Math.round(pct * 10) / 10}%`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
