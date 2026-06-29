'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { OrderAnalysisRow } from '@/lib/bigquery';
import { ProductTable } from '@/components/ProductTable';
import { KpiCard } from '@/components/KpiCard';
import { StockStatusLegend } from '@/components/StockStatusLegend';
import { CircularProgress } from '@/components/CircularProgress';
import { GlobalSimulationBar, DEFAULT_SIM_PARAMS, recomputeRow, SimParams }
  from '@/components/GlobalSimulationBar';
import { formatNumber, todayJST } from '@/lib/utils';
import { Download, FileSpreadsheet, RefreshCw, AlertTriangle } from 'lucide-react';

// Phase 2: GCS-hosted Excel（毎朝07:00 JST再生成）。非公開バケットのため /api/order-xlsx 経由で配信。

export function OrderAnalysisView() {
  const [date, setDate]           = useState<string>('');  // 空=最新日(マートMAX)を採用（顧客#15）
  const [rows, setRows]           = useState<OrderAnalysisRow[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [urgencyFilter, setUrgencyFilter] = useState<string>('');
  // 顧客要望2026: ZOZOBO同様の絞り込み（ショップ／親カテゴリ／商品主性別）。サーバ側で適用。
  const [shop, setShop] = useState<string>('');
  const [parentCategory, setParentCategory] = useState<string>('');
  const [gender, setGender] = useState<string>('');
  const [opts, setOpts] = useState<{ shops: string[]; categories: string[]; genders: string[] }>({ shops: [], categories: [], genders: [] });
  const [simParams, setSimParams] = useState<SimParams>(DEFAULT_SIM_PARAMS);
  const [busy, setBusy] = useState(true);          // 初回ロード中は円形プログレスを表示
  const [loadedOnce, setLoadedOnce] = useState(false);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ date: date || 'latest', limit: '1000' });
      if (urgencyFilter) params.append('urgency', urgencyFilter);
      if (shop) params.append('shop', shop);
      if (parentCategory) params.append('parent_category', parentCategory);
      if (gender) params.append('gender', gender);
      const res = await fetch(`/api/products?${params}`);
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const json = await res.json();
      setRows(json.data || []);
      if (json.filters) setOpts(json.filters);  // 絞り込みの選択肢（当日の対象に存在する値）
      if (!date && json.date) setDate(json.date);  // 最新日を日付入力に反映（顧客#15）
    } catch (err) {
      setError(String(err));
    } finally {
      setIsLoading(false);
      setLoadedOnce(true);
    }
  }, [date, urgencyFilter, shop, parentCategory, gender]);

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

  // 初回ロードは円形プログレスを100%まで見せてから本体表示（他画面と同パターン）
  if (busy) return (
    <div className="px-6 py-4">
      <CircularProgress active={!loadedOnce} label="発注推奨データを集計中" onDone={() => setBusy(false)} />
    </div>
  );

  // 顧客要望2026: ダウンロードも画面の絞り込みを保持。フィルタ有無でExcelの出力先を切替。
  const filterQs = [
    `date=${encodeURIComponent(date)}`,
    urgencyFilter && `urgency=${encodeURIComponent(urgencyFilter)}`,
    shop && `shop=${encodeURIComponent(shop)}`,
    parentCategory && `parent_category=${encodeURIComponent(parentCategory)}`,
    gender && `gender=${encodeURIComponent(gender)}`,
  ].filter(Boolean).join('&');
  const hasFilter = !!(urgencyFilter || shop || parentCategory || gender);

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
          {/* 顧客要望2026: ZOZOBO同様の絞り込み（ショップ／親カテゴリ／商品主性別） */}
          <select value={shop} onChange={(e) => setShop(e.target.value)}
            className="px-2 py-1 text-xs border border-gray-300 rounded max-w-[140px]">
            <option value="">全ショップ</option>
            {opts.shops.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={parentCategory} onChange={(e) => setParentCategory(e.target.value)}
            className="px-2 py-1 text-xs border border-gray-300 rounded max-w-[140px]">
            <option value="">全親カテゴリ</option>
            {opts.categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={gender} onChange={(e) => setGender(e.target.value)}
            className="px-2 py-1 text-xs border border-gray-300 rounded">
            <option value="">全性別</option>
            {opts.genders.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
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
            href={`/api/export?${filterQs}`}
            className="inline-flex items-center gap-1 px-3 py-1 text-xs border border-gray-300 rounded hover:bg-gray-50"
            title="画面の絞り込みを反映したCSVをダウンロード"
          >
            <Download className="w-3 h-3" /> CSV{hasFilter && '（絞込）'}
          </a>
          <a
            href={hasFilter ? `/api/order-xlsx-filtered?${filterQs}` : '/api/order-xlsx'}
            className="inline-flex items-center gap-1 px-3 py-1 text-xs bg-emerald-600 text-white rounded hover:bg-emerald-700"
            title={hasFilter
              ? '画面の絞り込みを反映したExcel(.xlsx)を生成してダウンロード'
              : '毎朝07:00 JSTに最新データで再生成された発注管理表.xlsx (経営者サマリ+23列詳細+緊急度別の3シート)。SA認証で非公開GCSから配信'}
          >
            <FileSpreadsheet className="w-3 h-3" /> Excel{hasFilter && '（絞込）'}
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
        <KpiCard label="不足SKU"        value={formatNumber(warningCount)}   accent="amber"   sub={`在庫日数 < ${simParams.warningDays}日`} />
        <KpiCard label="過剰在庫SKU"    value={formatNumber(overstockCount)} accent="blue"    sub={`在庫日数 ≥ ${simParams.overstockDays}日`} />
        <KpiCard label="合計推奨発注数" value={formatNumber(totalOrderQty)}  accent="default" sub={`安全${simParams.weeks}週ベース`} />
      </div>

      {/* 在庫ステータスの判定基準（社内共有・日本語）*/}
      <div className="mb-4">
        <StockStatusLegend />
      </div>

      {/* Product table */}
      <div className="bg-white border border-gray-200 rounded">
        <ProductTable rows={displayRows} isLoading={isLoading} onSimulate={() => {}} />
      </div>
    </div>
  );
}
