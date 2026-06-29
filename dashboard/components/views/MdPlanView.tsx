'use client';

import { useEffect, useState } from 'react';
import { TrendingDown, ArrowUpRight } from 'lucide-react';

// ブランド＝ショップ名（sales_daily.shop_name で集計）。
const BRANDS = ['MONO-MART', 'EMMA CLOTHES', 'Chaco closet', 'ADRER', 'anown', 'Anchor Smith', 'BONLECILL'];
const TABS = ['エグゼクティブサマリー', '売れ筋ランキング'];

type Cat = { name: string; sales: number; qty: number; types: number; discount_pct: number | null; score: number; label: string };
type Rank = { product_code: string; product_name: string | null; category: string | null; sales: number; qty: number };
type MdData = {
  brand: string; asof: string | null; period_days: number;
  kpi: { sales: number; types: number; qty: number; discount_pct: number | null };
  categories: Cat[]; ranking: Rank[];
};

const yen = (n: number) => `¥${Math.round(n).toLocaleString('ja-JP')}`;
const oku = (n: number) => (n >= 1e8 ? `¥${(n / 1e8).toFixed(1)}億` : n >= 1e4 ? `¥${Math.round(n / 1e4).toLocaleString('ja-JP')}万` : yen(n));

export function MdPlanView() {
  const [brand, setBrand] = useState(BRANDS[0]);
  const [tab, setTab] = useState(TABS[0]);
  const [data, setData] = useState<MdData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true); setError(null);
    fetch(`/api/md-plan?brand=${encodeURIComponent(brand)}`)
      .then((r) => r.json())
      .then((j) => { if (j.error) { setError(j.error); setData(null); } else setData(j as MdData); })
      .catch((e) => { setError('通信エラー: ' + String(e)); setData(null); })
      .finally(() => setLoading(false));
  }, [brand]);

  const cats = data?.categories ?? [];
  const reinforce = cats.filter((c) => c.label === '強化推奨').slice(0, 5);
  const review = cats.filter((c) => c.label === '見直し').slice(0, 5);
  const maxBar = 100;

  return (
    <div className="px-6 py-4">
      <div className="mb-3">
        <h1 className="text-base font-bold text-gray-900">MD計画・提案</h1>
        <p className="text-xs text-gray-500">
          BigQuery最新データで集計（直近{data?.period_days ?? 90}日）
          {data?.asof && ` / データ基準日: ${data.asof}`}
        </p>
      </div>

      {/* Brand pills */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {BRANDS.map((b) => (
          <button key={b} onClick={() => setBrand(b)}
            className={`px-4 py-2 text-xs font-bold rounded ${brand === b ? 'bg-gray-800 text-white' : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'}`}>
            {b}
          </button>
        ))}
      </div>

      {/* Sub-tabs */}
      <div className="border-b border-gray-200 mb-4">
        <div className="flex items-center gap-6">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`pb-2 text-xs font-medium border-b-2 transition-colors ${tab === t ? 'border-cyan-500 text-cyan-700' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="text-sm text-gray-400 py-10 text-center">集計中…</div>}
      {error && <div className="text-sm text-rose-600 py-4">エラー: {error}</div>}
      {!loading && !error && data && (data.kpi.sales === 0 && cats.length === 0
        ? <div className="text-sm text-gray-400 py-10 text-center">「{brand}」の直近{data.period_days}日に受注実績がありません。</div>
        : (
        <>
          {/* KPI cards (実データ) */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            {[
              { label: '売上金額', value: oku(data.kpi.sales), sub: `(直近${data.period_days}日合計)` },
              { label: '型数', value: data.kpi.types.toLocaleString('ja-JP'), sub: '(ユニーク品番)' },
              { label: '値引率', value: data.kpi.discount_pct == null ? '—' : `${data.kpi.discount_pct}%`, sub: '' },
              { label: '販売数', value: `${data.kpi.qty.toLocaleString('ja-JP')}点`, sub: '' },
            ].map((c) => (
              <div key={c.label} className="bg-white border border-gray-200 rounded p-4">
                <div className="text-[11px] text-gray-500">{c.label}</div>
                <div className="text-xl font-bold text-gray-900 mt-1">{c.value}</div>
                {c.sub && <div className="text-[11px] text-gray-400 mt-0.5">{c.sub}</div>}
              </div>
            ))}
          </div>

          {tab === 'エグゼクティブサマリー' && (
            <>
              {/* 2-col panels (実データ) */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-4">
                <div className="bg-white border border-gray-200 rounded p-4">
                  <h3 className="text-xs font-bold text-emerald-600 flex items-center gap-1 mb-2">
                    <ArrowUpRight className="w-3 h-3" /> 強化推奨カテゴリ（売上上位）
                  </h3>
                  <ul className="space-y-1.5">
                    {reinforce.length === 0 && <li className="text-xs text-gray-400">該当なし</li>}
                    {reinforce.map((c) => (
                      <li key={c.name} className="flex items-center justify-between text-xs">
                        <span className="text-gray-700">{c.name}</span>
                        <span className="text-gray-500">スコア <span className="font-bold text-gray-900">{c.score}</span> / {oku(c.sales)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="bg-white border border-gray-200 rounded p-4">
                  <h3 className="text-xs font-bold text-rose-600 flex items-center gap-1 mb-2">
                    <TrendingDown className="w-3 h-3" /> 見直し対象（値引率が高い）
                  </h3>
                  <ul className="space-y-1.5">
                    {review.length === 0 && <li className="text-xs text-gray-400">該当なし</li>}
                    {review.map((c) => (
                      <li key={c.name} className="flex items-center justify-between text-xs">
                        <span className="text-gray-700">{c.name}</span>
                        <span className="font-bold text-rose-600">値引率 {c.discount_pct}%</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Score bars (実データ) */}
              <div className="bg-white border border-gray-200 rounded p-4">
                <h3 className="text-xs font-bold text-gray-700 mb-3">MDスコア上位カテゴリ（売上ベース）</h3>
                <div className="space-y-2">
                  {cats.slice(0, 10).map((s) => {
                    const widthPct = (s.score / maxBar) * 100;
                    const color = s.label === '強化推奨' ? (s.score > 60 ? 'bg-emerald-500' : 'bg-amber-400') : s.label === '見直し' ? 'bg-rose-400' : 'bg-gray-300';
                    const badge = s.label === '強化推奨' ? 'bg-emerald-100 text-emerald-700' : s.label === '見直し' ? 'bg-rose-100 text-rose-700' : 'bg-gray-100 text-gray-600';
                    return (
                      <div key={s.name} className="flex items-center gap-3 text-xs">
                        <div className="w-32 text-gray-700 truncate">{s.name}</div>
                        <div className="flex-1 h-5 bg-gray-100 rounded relative overflow-hidden">
                          <div className={`absolute left-0 top-0 bottom-0 ${color} flex items-center justify-end pr-2`} style={{ width: `${Math.max(widthPct, 6)}%` }}>
                            <span className="text-[10px] text-white font-bold">{s.score}</span>
                          </div>
                        </div>
                        <span className={`px-2 py-0.5 text-[10px] font-bold rounded ${badge}`}>{s.label}</span>
                        <span className="w-12 text-right text-gray-500">{s.types}型</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}

          {tab === '売れ筋ランキング' && (
            <div className="bg-white border border-gray-200 rounded overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="px-3 py-2 text-left w-10">#</th>
                    <th className="px-3 py-2 text-left">品番</th>
                    <th className="px-3 py-2 text-left">商品名</th>
                    <th className="px-3 py-2 text-left">カテゴリ</th>
                    <th className="px-3 py-2 text-right">売上金額</th>
                    <th className="px-3 py-2 text-right">販売数</th>
                  </tr>
                </thead>
                <tbody>
                  {data.ranking.length === 0 && <tr><td colSpan={6} className="px-3 py-4 text-gray-400">データなし</td></tr>}
                  {data.ranking.map((r, i) => (
                    <tr key={r.product_code} className="border-t border-gray-100 hover:bg-gray-50">
                      <td className="px-3 py-1.5 text-gray-500">{i + 1}</td>
                      <td className="px-3 py-1.5 font-mono text-gray-800">{r.product_code}</td>
                      <td className="px-3 py-1.5 text-gray-700 truncate max-w-[280px]">{r.product_name ?? '—'}</td>
                      <td className="px-3 py-1.5 text-gray-600">{r.category ?? '—'}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{yen(r.sales)}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{r.qty.toLocaleString('ja-JP')}点</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ))}
    </div>
  );
}
