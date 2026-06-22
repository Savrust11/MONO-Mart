'use client';

import { useState } from 'react';
import { TrendingUp, TrendingDown, ArrowUpRight, AlertCircle } from 'lucide-react';

const BRANDS = ['MONO-MART', 'EMMA CLOTHES', 'CLEL', 'ADRER', 'WYM LIDNM'];

const TABS = ['エグゼクティブサマリー', 'MD提案一覧', '外部環境分析', '内部環境分析', '市場分析', '売れ筋ランキング'];

const KPI_CARDS = [
  { label: '売上金額', value: '¥10.6億', sub: '(3ヶ月合計)' },
  { label: '型数',     value: '440',     sub: '(ユニーク品番)' },
  { label: '粗利率',   value: '30.7%',   sub: '' },
  { label: 'プロパー比率', value: '2.8%', sub: '' },
];

const RECOMMEND_CATEGORIES = [
  { name: 'パンツ',          score: '61.3' },
  { name: 'トップス',         score: '59.6' },
  { name: 'ジャケット/アウター', score: '51.5' },
];

const NEW_ENTRY_CANDIDATES = [
  { name: '財布/小物',         demand: '需要 24,969件' },
  { name: '水着/着物・浴衣',   demand: '需要 3,015件' },
];

const REVIEW_TARGETS = [
  { name: 'ファッション雑貨', delta: '-12.4%' },
  { name: '帽子',            delta: '+32.9%' },
  { name: 'スカート',        delta: '-5.6%' },
];

const SCORE_BARS = [
  { name: 'パンツ',           score: 61.3, label: '強化推奨', count: '48型' },
  { name: 'トップス',          score: 59.6, label: '強化推奨', count: '274型' },
  { name: 'ジャケット/アウター', score: 51.5, label: '強化推奨', count: '64型' },
  { name: 'バッグ',            score: 49.7, label: '維持',    count: '15型' },
  { name: 'シューズ',          score: 47.5, label: '維持',    count: '13型' },
  { name: 'アクセサリー',       score: 41.2, label: '維持',    count: '1型' },
  { name: 'レッグウェア',       score: 32.4, label: '維持',    count: '3型' },
  { name: 'ワンピース/ドレス',   score: 31.0, label: '維持',    count: '3型' },
];

export function MdPlanView() {
  const [brand, setBrand] = useState(BRANDS[0]);
  const [tab, setTab] = useState(TABS[0]);

  return (
    <div className="px-6 py-4">
      {/* Title */}
      <div className="mb-3">
        <h1 className="text-base font-bold text-gray-900">MD計画</h1>
        <p className="text-xs text-gray-500">
          分析期間: 2026年1月〜3月 / 更新日: 2026-04-03 / SS月: 202603
        </p>
      </div>

      {/* Brand pills */}
      <div className="flex items-center gap-2 mb-3">
        {BRANDS.map((b) => (
          <button
            key={b}
            onClick={() => setBrand(b)}
            className={`px-4 py-2 text-xs font-bold rounded ${
              brand === b
                ? 'bg-gray-800 text-white'
                : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
            }`}
          >
            {b}
          </button>
        ))}
      </div>

      {/* Sub-tabs */}
      <div className="border-b border-gray-200 mb-4">
        <div className="flex items-center gap-6">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`pb-2 text-xs font-medium border-b-2 transition-colors ${
                tab === t
                  ? 'border-cyan-500 text-cyan-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {KPI_CARDS.map((c) => (
          <div key={c.label} className="bg-white border border-gray-200 rounded p-4">
            <div className="text-[11px] text-gray-500">{c.label}</div>
            <div className="text-xl font-bold text-gray-900 mt-1">{c.value}</div>
            {c.sub && <div className="text-[11px] text-gray-400 mt-0.5">{c.sub}</div>}
          </div>
        ))}
      </div>

      {/* 3-col panels */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mb-4">
        <div className="bg-white border border-gray-200 rounded p-4">
          <h3 className="text-xs font-bold text-emerald-600 flex items-center gap-1 mb-2">
            <ArrowUpRight className="w-3 h-3" /> 強化推奨カテゴリ
          </h3>
          <ul className="space-y-1.5">
            {RECOMMEND_CATEGORIES.map((c) => (
              <li key={c.name} className="flex items-center justify-between text-xs">
                <span className="text-gray-700">{c.name}</span>
                <span className="text-gray-500">スコア <span className="font-bold text-gray-900">{c.score}</span></span>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-white border border-gray-200 rounded p-4">
          <h3 className="text-xs font-bold text-cyan-600 flex items-center gap-1 mb-2">
            <span className="text-cyan-500">⊕</span> 新規参入候補
          </h3>
          <ul className="space-y-1.5">
            {NEW_ENTRY_CANDIDATES.map((c) => (
              <li key={c.name} className="flex items-center justify-between text-xs">
                <span className="text-gray-700">{c.name}</span>
                <span className="text-gray-500">{c.demand}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-white border border-gray-200 rounded p-4">
          <h3 className="text-xs font-bold text-rose-600 flex items-center gap-1 mb-2">
            <TrendingDown className="w-3 h-3" /> 見直し対象
          </h3>
          <ul className="space-y-1.5">
            {REVIEW_TARGETS.map((c) => (
              <li key={c.name} className="flex items-center justify-between text-xs">
                <span className="text-gray-700">{c.name}</span>
                <span className={`font-bold ${c.delta.startsWith('-') ? 'text-rose-600' : 'text-emerald-600'}`}>
                  粗利率 {c.delta}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Score bars */}
      <div className="bg-white border border-gray-200 rounded p-4">
        <h3 className="text-xs font-bold text-gray-700 mb-3">MDスコア上位カテゴリ</h3>
        <div className="space-y-2">
          {SCORE_BARS.map((s) => {
            const widthPct = (s.score / 80) * 100; // scale max to 80
            const color = s.label === '強化推奨'
              ? (s.score > 60 ? 'bg-emerald-500' : 'bg-amber-400')
              : 'bg-gray-300';
            const badge = s.label === '強化推奨'
              ? 'bg-emerald-100 text-emerald-700'
              : 'bg-gray-100 text-gray-600';
            return (
              <div key={s.name} className="flex items-center gap-3 text-xs">
                <div className="w-32 text-gray-700 truncate">{s.name}</div>
                <div className="flex-1 h-5 bg-gray-100 rounded relative overflow-hidden">
                  <div
                    className={`absolute left-0 top-0 bottom-0 ${color} flex items-center justify-end pr-2`}
                    style={{ width: `${widthPct}%` }}
                  >
                    <span className="text-[10px] text-white font-bold">{s.score}</span>
                  </div>
                </div>
                <span className={`px-2 py-0.5 text-[10px] font-bold rounded ${badge}`}>{s.label}</span>
                <span className="w-12 text-right text-gray-500">{s.count}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
