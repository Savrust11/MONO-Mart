'use client';

/**
 * GlobalSimulationBar — Phase 2 / Track 3 (推奨発注ロジック調整)
 *
 * 発注管理表全体に対する what-if パラメータ調整 UI。
 *   ・安全在庫週数  (default 8)   — recommended = (weeks × 7 × daily_velocity_30d) − free_inv
 *   ・WARNING 閾値  (default 14日) — stock_days_7d ≤ N で「警告」
 *   ・OVERSTOCK 閾値 (default 90日) — stock_days_7d > N で「過剰在庫」
 *   ・季節係数      (default 1.0)  — 推奨数 × N (ピーク月補正の暫定実装)
 *
 * これらは client-side recompute なのでスライダー変更で即座にKPI/緊急度が更新。
 * 永続化はせず、リロードで default に戻る。
 */

import { useState, useCallback } from 'react';
import { Sliders, RotateCcw } from 'lucide-react';

export interface SimParams {
  weeks:              number;  // 安全在庫週数
  warningDays:        number;  // WARNING 閾値
  overstockDays:      number;  // OVERSTOCK 閾値
  seasonalMultiplier: number;  // 季節係数 (1.0 = なし)
}

export const DEFAULT_SIM_PARAMS: SimParams = {
  weeks:              8,
  warningDays:        90,   // 不足: 在庫日数 < 90日（通年品基準・顧客定義 2026）
  overstockDays:      271,  // 過剰: 在庫日数 ≥ 271日（顧客定義 2026）
  seasonalMultiplier: 1.0,
};

interface Props {
  params: SimParams;
  onChange: (params: SimParams) => void;
}

export function GlobalSimulationBar({ params, onChange }: Props) {
  const [expanded, setExpanded] = useState(false);

  const update = useCallback((patch: Partial<SimParams>) => {
    onChange({ ...params, ...patch });
  }, [params, onChange]);

  const reset = () => onChange(DEFAULT_SIM_PARAMS);

  const isModified = (
    params.weeks              !== DEFAULT_SIM_PARAMS.weeks ||
    params.warningDays        !== DEFAULT_SIM_PARAMS.warningDays ||
    params.overstockDays      !== DEFAULT_SIM_PARAMS.overstockDays ||
    params.seasonalMultiplier !== DEFAULT_SIM_PARAMS.seasonalMultiplier
  );

  return (
    <div className={`mb-3 bg-white border rounded ${isModified ? 'border-indigo-300' : 'border-gray-200'}`}>
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-gray-50"
      >
        <div className="flex items-center gap-2">
          <Sliders className="w-3.5 h-3.5 text-indigo-600" />
          <span className="font-bold text-gray-900">推奨発注ロジック</span>
          {isModified && (
            <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded text-[10px] font-semibold">
              シミュレーション中
            </span>
          )}
          <span className="text-gray-500">
            安全{params.weeks}週 / 不足 &lt; {params.warningDays}日 / 過剰 ≥ {params.overstockDays}日
            {params.seasonalMultiplier !== 1.0 && ` / 季節×${params.seasonalMultiplier.toFixed(2)}`}
          </span>
        </div>
        <span className="text-gray-400">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 px-3 py-3 grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
          {/* 安全在庫週数 */}
          <div className="flex flex-col gap-1">
            <label className="font-semibold text-gray-700 flex justify-between">
              <span>安全在庫週数</span>
              <span className="text-indigo-600 font-mono">{params.weeks}週</span>
            </label>
            <input
              type="range" min="2" max="24" step="1"
              value={params.weeks}
              onChange={(e) => update({ weeks: parseInt(e.target.value, 10) })}
              className="w-full accent-indigo-600"
            />
            <div className="text-[10px] text-gray-500">
              推奨発注数 = MAX(0, ⌈ {params.weeks}週 × 7日 × 30日販売速度
              {params.seasonalMultiplier !== 1.0 && ` × ${params.seasonalMultiplier.toFixed(2)}`}
              {' '}− フリー在庫 ⌉)
            </div>
          </div>

          {/* WARNING 閾値 */}
          <div className="flex flex-col gap-1">
            <label className="font-semibold text-gray-700 flex justify-between">
              <span>不足 閾値</span>
              <span className="text-amber-600 font-mono">&lt; {params.warningDays}日</span>
            </label>
            <input
              type="range" min="30" max="180" step="1"
              value={params.warningDays}
              onChange={(e) => update({ warningDays: parseInt(e.target.value, 10) })}
              className="w-full accent-amber-500"
            />
            <div className="text-[10px] text-gray-500">在庫日数がこの値未満で「不足」判定（通年品=90日）</div>
          </div>

          {/* 過剰 閾値 */}
          <div className="flex flex-col gap-1">
            <label className="font-semibold text-gray-700 flex justify-between">
              <span>過剰 閾値</span>
              <span className="text-blue-600 font-mono">≥ {params.overstockDays}日</span>
            </label>
            <input
              type="range" min="90" max="365" step="1"
              value={params.overstockDays}
              onChange={(e) => update({ overstockDays: parseInt(e.target.value, 10) })}
              className="w-full accent-blue-500"
            />
            <div className="text-[10px] text-gray-500">在庫日数がこの値以上で「過剰」判定（顧客定義=271日）</div>
          </div>

          {/* 季節係数 */}
          <div className="flex flex-col gap-1">
            <label className="font-semibold text-gray-700 flex justify-between">
              <span>季節係数 (推奨数 ×)</span>
              <span className="text-violet-600 font-mono">×{params.seasonalMultiplier.toFixed(2)}</span>
            </label>
            <input
              type="range" min="0.5" max="2.0" step="0.05"
              value={params.seasonalMultiplier}
              onChange={(e) => update({ seasonalMultiplier: parseFloat(e.target.value) })}
              className="w-full accent-violet-500"
            />
            <div className="text-[10px] text-gray-500">
              ピーク月補正の暫定。Manus 方式 (peak 月選択) へ拡張余地あり
            </div>
          </div>

          {/* リセットボタン */}
          <div className="md:col-span-4 flex justify-end">
            <button
              onClick={reset}
              disabled={!isModified}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
            >
              <RotateCcw className="w-3 h-3" />
              既定値に戻す (8週 / 14日 / 90日 / ×1.0)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Recompute recommended_order_qty + urgency for a single row with given params. */
export function recomputeRow(
  row: {
    free_inventory:     number;
    daily_velocity_7d:  number;
    daily_velocity_30d: number;
  },
  params: SimParams
): { recommended_order_qty: number; order_urgency: string; stock_days_7d: number | null } {
  const v30 = row.daily_velocity_30d ?? 0;
  const v7  = row.daily_velocity_7d  ?? 0;
  const free = row.free_inventory    ?? 0;
  const target = params.weeks * 7 * v30 * params.seasonalMultiplier;
  const recQty = Math.max(0, Math.ceil(target - free));
  const stockDays = v7 > 0 ? free / v7 : null;
  let urgency: string;
  if (free <= 0) urgency = 'CRITICAL';
  else if (stockDays !== null && stockDays < params.warningDays) urgency = 'WARNING';      // 不足: 90日未満
  else if (stockDays !== null && stockDays >= params.overstockDays) urgency = 'OVERSTOCK'; // 過剰: 271日以上
  else urgency = 'OK';
  return {
    recommended_order_qty: recQty,
    order_urgency: urgency,
    stock_days_7d: stockDays,
  };
}
