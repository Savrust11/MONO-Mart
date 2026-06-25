'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { OrderAnalysisRow } from '@/lib/bigquery';
import { ProductTable } from '@/components/ProductTable';
import { KpiCard } from '@/components/KpiCard';
import { GlobalSimulationBar, DEFAULT_SIM_PARAMS, recomputeRow, SimParams }
  from '@/components/GlobalSimulationBar';
import { formatNumber, todayJST } from '@/lib/utils';
import { Download, FileSpreadsheet, RefreshCw, AlertTriangle } from 'lucide-react';

// Phase 2: GCS-hosted Excel (regenerated daily by run_daily.ps1 [3d])
const EXCEL_LATEST_URL =
  'https://storage.googleapis.com/mono-back-office-system-exports'
  + '/order_management/latest/%E7%99%BA%E6%B3%A8%E7%AE%A1%E7%90%86%E8%A1%A8.xlsx';

export function OrderAnalysisView() {
  const [date, setDate]           = useState<string>('');  // 空=最新日(マートMAX)を採用（顧客#15）
  const [rows, setRows]           = useState<OrderAnalysisRow[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [urgencyFilter, setUrgencyFilter] = useState<string>('');
  const [simParams, setSimParams] = useState<SimParams>(DEFAULT_SIM_PARAMS);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ date: date || 'latest', limit: '1000' });
      if (urgencyFilter) params.append('urgency', urgencyFilter);
      const res = await fetch(`/api/products?${params}`);
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const json = await res.json();
      setRows(json.data || []);
      if (!date && json.date) setDate(json.date);  // 最新日を日付入力に反映（顧客#15）
    } catch (err) {
      setError(String(err));
    } finally {
      setIsLoading(false);
    }
  }, [date, urgencyFilter]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Apply simulation parameters client-side ─────────────────────────────────
  // Only recompute when params differ from default to avoid pointless work.
  const simulatedRows = useMemo(() => {
    const isDefault = (
      simParams.weeks              === DEFAULT_SIM_PARAMS.weeks &&
      simParams.warningDays        === DEFAULT_SIM_PARAMS.warningDays &&
      simParams.overstockDays      === DEFAULT_SIM_PARAMS.overstockDays &&
      simParams.seasonalMultiplier === DEFAULT_SIM_PARAMS.seasonalMultiplier
    );
    if (isDefault) return rows;
    return rows.map((r) => {
      const recomputed = recomputeRow({
        free_inventory:     r.free_inventory     ?? 0,
        daily_velocity_7d:  r.daily_velocity_7d  ?? 0,
        daily_velocity_30d: r.daily_velocity_30d ?? 0,
      }, simParams);
      return {
        ...r,
        recommended_order_qty: recomputed.recommended_order_qty,
        order_urgency:         recomputed.order_urgency as any,
        stock_days_7d:         recomputed.stock_days_7d,
      };
    });
  }, [rows, simParams]);

  // Apply the urgency filter AFTER simulation so changing params shows the
  // filtered counts based on the new computation.
  const displayRows = useMemo(() => (
    urgencyFilter
      ? simulatedRows.filter((r) => r.order_urgency === urgencyFilter)
      : simulatedRows
  ), [simulatedRows, urgencyFilter]);

  const criticalCount  = simulatedRows.filter((r) => r.order_urgency === 'CRITICAL').length;
  const warningCount   = simulatedRows.filter((r) => r.order_urgency === 'WARNING').length;
  const overstockCount = simulatedRows.filter((r) => r.order_urgency === 'OVERSTOCK').length;
  const totalOrderQty  = simulatedRows.reduce((s, r) => s + (r.recommended_order_qty || 0), 0);

  return (
    <div className="px-6 py-4">
      {/* Title + filters */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-base font-bold text-gray-900">発注推奨データ</h1>
          <p className="text-xs text-gray-500">
            mart_layer.order_analysis を元に発注判断を表示 / パラメータ変更で即時シミュレーション
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="px-2 py-1 text-xs border border-gray-300 rounded"
          />
          <select
            value={urgencyFilter}
            onChange={(e) => setUrgencyFilter(e.target.value)}
            className="px-2 py-1 text-xs border border-gray-300 rounded"
          >
            <option value="">全ステータス</option>
            <option value="CRITICAL">欠品のみ</option>
            <option value="WARNING">警告のみ</option>
            <option value="OK">OK</option>
            <option value="OVERSTOCK">過剰在庫</option>
          </select>
          <button
            onClick={fetchData}
            disabled={isLoading}
            className="inline-flex items-center gap-1 px-3 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
          >
            <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
            更新
          </button>
          <a
            href={`/api/export?date=${date}`}
            className="inline-flex items-center gap-1 px-3 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
          >
            <Download className="w-3 h-3" /> CSV
          </a>
          <a
            href={EXCEL_LATEST_URL}
            target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1 px-3 py-1 text-xs bg-emerald-600 text-white rounded hover:bg-emerald-700"
            title="毎朝07:00 JSTに最新データで再生成された発注管理表.xlsx (経営者サマリ+23列詳細+緊急度別の3シート)"
          >
            <FileSpreadsheet className="w-3 h-3" /> Excel
          </a>
        </div>
      </div>

      {error && (
        <div className="mb-3 p-2.5 bg-red-50 border border-red-200 rounded flex items-center gap-2 text-red-700 text-xs">
          <AlertTriangle className="w-3.5 h-3.5" />
          {error}
        </div>
      )}

      {/* Global simulation parameters */}
      <GlobalSimulationBar params={simParams} onChange={setSimParams} />

      {/* KPI summary (reflects simulated values) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
        <KpiCard label="欠品SKU"        value={formatNumber(criticalCount)}  accent="red"     sub="フリー在庫≤0" />
        <KpiCard label="警告SKU"        value={formatNumber(warningCount)}   accent="amber"   sub={`在庫日数 ≤ ${simParams.warningDays}日`} />
        <KpiCard label="過剰在庫SKU"    value={formatNumber(overstockCount)} accent="blue"    sub={`在庫日数 > ${simParams.overstockDays}日`} />
        <KpiCard label="合計推奨発注数" value={formatNumber(totalOrderQty)}  accent="default" sub={`安全${simParams.weeks}週ベース`} />
      </div>

      {/* Product table */}
      <div className="bg-white border border-gray-200 rounded">
        <ProductTable rows={displayRows} isLoading={isLoading} onSimulate={() => {}} />
      </div>
    </div>
  );
}
