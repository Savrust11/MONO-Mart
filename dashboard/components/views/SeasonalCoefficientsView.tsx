'use client';

import { useState, useEffect } from 'react';
import { CircularProgress } from '@/components/CircularProgress';

interface Cat { gender: string; child_item_type: string; weeks: (number | null)[]; total: number; }

// 1.00=平均週(白) / >1=繁忙期(赤) / <1=閑散期(青)
function cellColor(c: number | null): string {
  if (c == null) return '#ffffff';
  if (c >= 1) { const t = Math.min(1, (c - 1) / 1.5); return `rgba(220,38,38,${0.10 + t * 0.6})`; }
  const t = Math.min(1, (1 - c) / 0.8); return `rgba(37,99,235,${0.10 + t * 0.55})`;
}

export function SeasonalCoefficientsView() {
  const [cats, setCats] = useState<Cat[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(true);   // 進捗を100%まで見せてから本体表示
  const [error, setError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<string | null>(null);
  const [gender, setGender] = useState<'ALL' | 'MEN' | 'WOMEN'>('ALL');
  const [kw, setKw] = useState('');

  useEffect(() => {
    fetch('/api/seasonal-coefficients').then((r) => r.json()).then((j) => {
      if (j.error) setError(j.error);
      else { setCats(j.categories || []); setUpdated(j.updated_at ?? null); }
    }).catch((e) => setError(String(e))).finally(() => setLoading(false));
  }, []);

  if (busy) return <CircularProgress active={loading} label="季節係数を読み込み中" onDone={() => setBusy(false)} />;
  if (error) return <div className="m-4 bg-rose-50 border border-rose-200 rounded p-3 text-xs text-rose-700">{error}</div>;

  const weeks = Array.from({ length: 52 }, (_, i) => i + 1);
  const rows = cats.filter((c) => (gender === 'ALL' || c.gender === gender) && (!kw || c.child_item_type.includes(kw)));

  return (
    <div className="p-4 space-y-3">
      <div>
        <h2 className="text-base font-semibold text-gray-800">52週 季節係数（男女別 × 商品タイプ子別）</h2>
        <p className="text-[11px] text-gray-500 mt-1">
          シミュレーションの季節調整に使う基礎値です。<b>ファーストセラー（ZOZO BackOffice・直近52週）の販売数</b>から算出（{updated ? updated.slice(0, 10) : '—'} 更新）。
          各週のトップ50（メンズ50・レディース50）に入った商品タイプ子だけ色が付き、圏外の週は<span className="text-gray-400">1.00（平均週扱い）</span>で表示します。
        </p>
      </div>
      <div className="flex items-center gap-2 text-[12px]">
        <span className="text-gray-500">性別:</span>
        {(['ALL', 'MEN', 'WOMEN'] as const).map((g) => (
          <button key={g} onClick={() => setGender(g)}
            className={`px-2 py-1 rounded border ${gender === g ? 'bg-teal-600 text-white border-teal-600' : 'border-gray-300 hover:bg-gray-50'}`}>
            {g === 'ALL' ? '全部' : g}
          </button>
        ))}
        <input value={kw} onChange={(e) => setKw(e.target.value)} placeholder="商品タイプで絞り込み"
          className="ml-2 px-2 py-1 border border-gray-300 rounded text-[12px] w-48" />
        <span className="ml-auto text-gray-400">{rows.length} 分類</span>
      </div>
      {/* 凡例（顧客が空欄=1.00の意味を画面上で理解できるように）*/}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500">
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3.5 h-3.5 rounded-sm" style={{ background: 'rgba(220,38,38,0.55)' }} />繁忙（&gt;1）</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3.5 h-3.5 rounded-sm" style={{ background: 'rgba(37,99,235,0.45)' }} />閑散（&lt;1）</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3.5 h-3.5 rounded-sm border border-gray-200 bg-white" /><span className="text-gray-300 font-medium">1.00</span>＝平均週（その週はトップ50圏外＝季節調整なし）</span>
      </div>
      <div className="bg-white border border-gray-200 rounded overflow-x-auto">
        <table className="text-[10px] border-collapse">
          <thead>
            <tr className="bg-gray-100 text-gray-600">
              <th className="px-2 py-1 border border-gray-200 text-left sticky left-0 bg-gray-100 z-10 min-w-[190px]">性別 / 商品タイプ子</th>
              {weeks.map((w) => <th key={w} className="px-1 py-1 border border-gray-200 min-w-[34px] text-center font-normal">W{w}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={53} className="px-3 py-3 text-gray-400">該当する分類がありません。</td></tr>
            )}
            {rows.map((c, i) => (
              <tr key={i} className="hover:bg-gray-50/60">
                <td className="px-2 py-1 border border-gray-100 sticky left-0 bg-white z-10 whitespace-nowrap">
                  <span className={`inline-block w-12 font-semibold ${c.gender === 'MEN' ? 'text-blue-700' : 'text-pink-700'}`}>{c.gender}</span>
                  {c.child_item_type}
                </td>
                {weeks.map((w) => {
                  const v = c.weeks[w];
                  if (v == null) return (
                    <td key={w} className="px-1 py-1 border border-gray-100 text-center tabular-nums text-gray-300"
                      title="この週はトップ50圏外（平均週=1.00として扱います）">1.00</td>
                  );
                  return (
                    <td key={w} className="px-1 py-1 border border-gray-100 text-center tabular-nums"
                      style={{ backgroundColor: cellColor(v) }}>{v.toFixed(2)}</td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
