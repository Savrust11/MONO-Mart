'use client';

/**
 * SimulationPanel
 *
 * Shows a 3-scenario order simulation for a selected SKU.
 * Appears as a modal overlay when the user clicks "シミュレーション" on any row.
 *
 * Renders:
 *   - SKU header (product / color / size / urgency)
 *   - Current snapshot metrics
 *   - 3 scenario cards (conservative / balanced / aggressive)
 *   - 12-week stock projection chart (pure CSS bar chart, no lib dependency)
 *   - Optional custom order quantity input
 */

import { useState, useEffect, useCallback } from 'react';
import { X, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { formatNumber } from '@/lib/utils';

// ── Types (mirrored from API) ─────────────────────────────────────────────────

interface Scenario {
  label:           string;
  order_qty:       number;
  target_days:     number;
  stockout_week:   number | null;
  total_cost:      number;
  total_revenue:   number;
  gross_profit:    number;
  margin_pct:      number | null;
  description:     string;
}

interface WeeklyProjection {
  week:                number;
  stock_without_order: number;
  stock_conservative:  number;
  stock_balanced:      number;
  stock_aggressive:    number;
}

interface SimulationResult {
  sku_code:     string;
  product_code: string;
  product_name: string;
  color_name:   string;
  size:         string;
  current: {
    free_inventory:        number;
    daily_velocity_30d:    number;
    trend_coefficient:     number;
    stock_days_7d:         number | null;
    order_urgency:         string;
    cost_price:            number;
    retail_price:          number;
    gross_margin_pct:      number | null;
    recommended_order_qty: number;
  };
  scenarios: {
    conservative: Scenario;
    balanced:     Scenario;
    aggressive:   Scenario;
  };
  weekly_projections: WeeklyProjection[];
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  skuCode:  string;
  date:     string;
  onClose:  () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const URGENCY_LABEL: Record<string, { text: string; cls: string }> = {
  CRITICAL:  { text: '欠品',     cls: 'bg-red-100 text-red-700' },
  WARNING:   { text: '警告',     cls: 'bg-amber-100 text-amber-700' },
  OK:        { text: 'OK',       cls: 'bg-green-100 text-green-700' },
  OVERSTOCK: { text: '過剰在庫', cls: 'bg-blue-100 text-blue-700' },
};

function fmt(n: number | null | undefined, decimals = 0): string {
  if (n == null) return '-';
  return n.toLocaleString('ja-JP', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtYen(n: number): string {
  return `¥${n.toLocaleString('ja-JP')}`;
}

function fmtPct(n: number | null): string {
  if (n == null) return '-';
  return `${(n * 100).toFixed(1)}%`;
}

// ── Scenario card ─────────────────────────────────────────────────────────────

function ScenarioCard({
  scenario,
  isRecommended,
  accentColor,
}: {
  scenario:       Scenario;
  isRecommended?: boolean;
  accentColor:    string;
}) {
  const borderCls = isRecommended ? `border-2 ${accentColor}` : 'border border-gray-200';
  return (
    <div className={`rounded-xl bg-white p-4 ${borderCls} flex flex-col gap-2`}>
      {isRecommended && (
        <div className={`text-xs font-bold px-2 py-0.5 rounded-full self-start ${accentColor.replace('border-', 'bg-').replace('500', '100')} text-${accentColor.split('-')[1]}-700`}>
          推奨
        </div>
      )}
      <div className="text-sm font-bold text-gray-900">{scenario.label}</div>
      <div className="text-xs text-gray-500 leading-snug">{scenario.description}</div>

      <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <span className="text-gray-400">発注数</span>
        <span className="font-bold text-gray-900 text-right">{formatNumber(scenario.order_qty)} 枚</span>

        <span className="text-gray-400">在庫カバー</span>
        <span className="font-semibold text-right text-gray-700">
          {scenario.target_days > 0 ? `${scenario.target_days} 日` : '-'}
        </span>

        <span className="text-gray-400">欠品予測</span>
        <span className={`font-semibold text-right ${scenario.stockout_week ? 'text-red-600' : 'text-green-600'}`}>
          {scenario.stockout_week ? `第${scenario.stockout_week}週` : '12週内なし'}
        </span>

        <span className="text-gray-400">発注コスト</span>
        <span className="font-semibold text-right text-gray-700">{fmtYen(scenario.total_cost)}</span>

        <span className="text-gray-400">予想粗利</span>
        <span className={`font-bold text-right ${scenario.gross_profit >= 0 ? 'text-green-700' : 'text-red-600'}`}>
          {fmtYen(scenario.gross_profit)}
        </span>

        <span className="text-gray-400">粗利率</span>
        <span className="font-semibold text-right text-gray-700">{fmtPct(scenario.margin_pct)}</span>
      </div>
    </div>
  );
}

// ── Mini stock chart (pure CSS, no chart library) ─────────────────────────────

function StockChart({ projections }: { projections: WeeklyProjection[] }) {
  const allValues = projections.flatMap(p => [
    p.stock_without_order,
    p.stock_aggressive,
  ]);
  const maxVal = Math.max(...allValues, 1);
  const minVal = Math.min(...allValues, 0);
  const range  = maxVal - minVal || 1;

  const toY = (v: number) =>
    Math.round(((maxVal - v) / range) * 100);  // 0% = top, 100% = bottom

  const LINES: Array<{ key: keyof WeeklyProjection; color: string; label: string; dashed?: boolean }> = [
    { key: 'stock_without_order', color: '#9CA3AF', label: '発注なし', dashed: true },
    { key: 'stock_conservative',  color: '#F59E0B', label: '安全発注' },
    { key: 'stock_balanced',      color: '#6366F1', label: '推奨発注' },
    { key: 'stock_aggressive',    color: '#10B981', label: '積極発注' },
  ];

  // SVG polyline
  const pts = (key: keyof WeeklyProjection) =>
    projections.map((p, i) => {
      const x = (i / (projections.length - 1)) * 100;
      const y = toY(p[key] as number);
      return `${x},${y}`;
    }).join(' ');

  return (
    <div>
      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-2">
        {LINES.map(l => (
          <span key={l.key} className="flex items-center gap-1 text-xs text-gray-600">
            <span
              className="inline-block w-6 h-0.5 rounded"
              style={{ backgroundColor: l.color, borderTop: l.dashed ? `2px dashed ${l.color}` : undefined }}
            />
            {l.label}
          </span>
        ))}
      </div>

      {/* Zero line indicator */}
      <div className="text-xs text-gray-400 mb-1">在庫数推移（12週間）</div>

      <div className="relative">
        <svg
          viewBox="0 0 100 80"
          preserveAspectRatio="none"
          className="w-full h-40 border border-gray-100 rounded bg-gray-50"
        >
          {/* Zero line */}
          {minVal < 0 && (
            <line
              x1="0" y1={toY(0)}
              x2="100" y2={toY(0)}
              stroke="#EF4444" strokeWidth="0.4" strokeDasharray="2,1"
            />
          )}

          {LINES.map(l => (
            <polyline
              key={l.key}
              points={pts(l.key)}
              fill="none"
              stroke={l.color}
              strokeWidth="1.5"
              strokeDasharray={l.dashed ? '3,2' : undefined}
              vectorEffect="non-scaling-stroke"
            />
          ))}

          {/* Week labels */}
          {[1, 4, 8, 12].map(w => (
            <text
              key={w}
              x={(w - 1) / 11 * 100}
              y="78"
              fontSize="4"
              fill="#9CA3AF"
              textAnchor="middle"
            >
              W{w}
            </text>
          ))}
        </svg>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function SimulationPanel({ skuCode, date, onClose }: Props) {
  const [data,        setData]        = useState<SimulationResult | null>(null);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState<string | null>(null);
  const [customQty,   setCustomQty]   = useState<string>('');
  const [customData,  setCustomData]  = useState<SimulationResult | null>(null);
  const [customLoading, setCustomLoading] = useState(false);

  // Initial fetch
  useEffect(() => {
    setLoading(true);
    fetch('/api/simulate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ sku_code: skuCode, date }),
    })
      .then(r => r.json())
      .then(d => {
        if (d.error) throw new Error(d.error);
        setData(d);
        setCustomQty(String(d.current.recommended_order_qty));
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [skuCode, date]);

  // Custom quantity simulation
  const runCustomSim = useCallback(async () => {
    const qty = parseInt(customQty, 10);
    if (isNaN(qty) || qty < 0) return;
    setCustomLoading(true);
    try {
      const r = await fetch('/api/simulate', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ sku_code: skuCode, date, order_qty: qty }),
      });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      setCustomData(d);
    } catch (e) {
      alert('シミュレーション失敗: ' + (e as Error).message);
    } finally {
      setCustomLoading(false);
    }
  }, [skuCode, date, customQty]);

  const display = customData ?? data;

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 backdrop-blur-sm pt-10 pb-6 px-4 overflow-y-auto"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Panel */}
      <div className="relative bg-gray-50 rounded-2xl shadow-2xl w-full max-w-3xl flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-white rounded-t-2xl border-b border-gray-200">
          <div>
            <h2 className="text-base font-bold text-gray-900">発注シミュレーション</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              {loading ? '読込中...' : display
                ? `${display.product_code} / ${display.color_name} / ${display.size}`
                : skuCode}
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
          >
            <X size={16} />
            閉じる
          </button>
        </div>

        {/* Body */}
        <div className="p-6 flex flex-col gap-5">

          {loading && (
            <div className="py-16 text-center text-sm text-gray-400">
              シミュレーション計算中...
            </div>
          )}

          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              エラー: {error}
            </div>
          )}

          {display && !loading && (
            <>
              {/* Current snapshot */}
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">
                  現在のSKU状況
                </div>
                <div className="grid grid-cols-4 gap-3 text-xs">
                  {[
                    ['フリー在庫',   fmt(display.current.free_inventory)    + ' 枚'],
                    ['日販 (30d)',   fmt(display.current.daily_velocity_30d, 1) + ' 枚/日'],
                    ['トレンド係数', fmt(display.current.trend_coefficient, 2)],
                    ['在庫日数',     display.current.stock_days_7d != null
                                      ? `${fmt(display.current.stock_days_7d, 1)} 日`
                                      : '-'],
                    ['原価',         fmtYen(display.current.cost_price)],
                    ['売価',         fmtYen(display.current.retail_price)],
                    ['粗利率',       fmtPct(display.current.gross_margin_pct)],
                    ['推奨発注数',   fmt(display.current.recommended_order_qty) + ' 枚'],
                  ].map(([label, value]) => (
                    <div key={label} className="flex flex-col gap-0.5">
                      <span className="text-gray-400">{label}</span>
                      <span className="font-semibold text-gray-900">{value}</span>
                    </div>
                  ))}
                </div>
                {/* Urgency badge */}
                {(() => {
                  const urg = URGENCY_LABEL[display.current.order_urgency] ??
                    { text: display.current.order_urgency, cls: 'bg-gray-100 text-gray-700' };
                  return (
                    <span className={`mt-3 inline-block px-2 py-0.5 rounded-full text-xs font-bold ${urg.cls}`}>
                      {urg.text}
                    </span>
                  );
                })()}
              </div>

              {/* Scenario cards */}
              <div className="grid grid-cols-3 gap-3">
                <ScenarioCard
                  scenario={display.scenarios.conservative}
                  accentColor="border-amber-400"
                />
                <ScenarioCard
                  scenario={display.scenarios.balanced}
                  isRecommended
                  accentColor="border-indigo-500"
                />
                <ScenarioCard
                  scenario={display.scenarios.aggressive}
                  accentColor="border-emerald-500"
                />
              </div>

              {/* 12-week chart */}
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">
                  在庫推移グラフ（12週間予測）
                </div>
                <StockChart projections={display.weekly_projections} />
                <p className="text-xs text-gray-400 mt-2">
                  ※ 赤破線 = 在庫ゼロライン。線が下を下回ると欠品状態。
                </p>
              </div>

              {/* Custom quantity input */}
              <div className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-3">
                  カスタム発注数でシミュレーション
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="number"
                    min="0"
                    value={customQty}
                    onChange={e => setCustomQty(e.target.value)}
                    className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-36 font-mono"
                    placeholder="発注数を入力"
                    onKeyDown={e => { if (e.key === 'Enter') runCustomSim(); }}
                  />
                  <button
                    onClick={runCustomSim}
                    disabled={customLoading}
                    className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 font-semibold"
                  >
                    {customLoading ? '計算中...' : '再計算'}
                  </button>
                  {customData && (
                    <button
                      onClick={() => setCustomData(null)}
                      className="text-xs text-gray-400 hover:text-gray-600"
                    >
                      リセット
                    </button>
                  )}
                  <span className="text-xs text-gray-400">
                    推奨: {formatNumber(data?.current.recommended_order_qty ?? 0)} 枚
                  </span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
