'use client';

import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  SortingState,
  ColumnFiltersState,
} from '@tanstack/react-table';
import { useState, useMemo } from 'react';
import { OrderAnalysisRow } from '@/lib/bigquery';
import { AlertBadge } from './AlertBadge';
import { SalesSpark } from './SalesSpark';
import {
  formatNumber,
  formatDays,
  formatPercent,
  formatTrend,
  URGENCY_STYLES,
} from '@/lib/utils';
import { clsx } from 'clsx';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';

const col = createColumnHelper<OrderAnalysisRow>();

function buildColumns(onSimulate: (skuCode: string) => void) {
  return [
  // --- Frozen left columns (product identity) ---
  col.accessor('order_urgency', {
    header: '緊急度',
    size: 60,
    cell: (info) => <AlertBadge urgency={info.getValue() as any} size="sm" />,
  }),
  col.accessor('maker_color_code', {
    header: 'メーカーカラー',
    size: 90,
    cell: (info) => <span className="font-mono text-xs">{info.getValue()}</span>,
  }),
  col.accessor('product_code', {
    header: '品番',
    size: 80,
    cell: (info) => <span className="font-mono text-xs font-semibold">{info.getValue()}</span>,
  }),
  col.accessor('color_name', {
    header: 'カラー',
    size: 80,
  }),
  col.accessor('size', {
    header: 'サイズ',
    size: 50,
    cell: (info) => <span className="font-bold">{info.getValue()}</span>,
  }),
  col.accessor('sku_code', {
    header: 'CS品番',
    size: 60,
    cell: (info) => <span className="font-mono text-xs text-gray-500">{info.getValue()}</span>,
  }),
  col.accessor('shelf_type', {
    header: '棚',
    size: 50,
  }),

  // --- Supply ---
  col.accessor('inventory', {
    header: '在庫',
    size: 60,
    cell: (info) => <span className="font-mono">{formatNumber(info.getValue())}</span>,
  }),
  col.accessor('incoming_stock', {
    header: '入荷残',
    size: 60,
    cell: (info) => <span className="font-mono text-blue-600">{formatNumber(info.getValue())}</span>,
  }),
  col.accessor('free_inventory', {
    header: 'フリー在庫',
    size: 80,
    cell: (info) => {
      const v = info.getValue();
      return (
        <span className={clsx('font-mono font-semibold', v < 0 ? 'text-red-600' : 'text-gray-900')}>
          {formatNumber(v)}
        </span>
      );
    },
  }),
  col.accessor('reservations_pending', {
    header: '予約未処理',
    size: 70,
    cell: (info) => <span className="font-mono">{formatNumber(info.getValue())}</span>,
  }),

  // --- Demand ---
  col.accessor('sales_7d', {
    header: '7日間',
    size: 60,
    cell: (info) => <span className="font-mono">{formatNumber(info.getValue())}</span>,
  }),
  col.accessor('sales_30d', {
    header: '一ヶ月',
    size: 60,
    cell: (info) => <span className="font-mono">{formatNumber(info.getValue())}</span>,
  }),
  col.accessor('sales_2w', {
    header: '直近2週間',
    size: 70,
    cell: (info) => <span className="font-mono">{formatNumber(info.getValue())}</span>,
  }),
  col.accessor('sales_ytd', {
    header: '年度累計',
    size: 70,
    cell: (info) => <span className="font-mono">{formatNumber(info.getValue())}</span>,
  }),
  col.accessor('favorites_total', {
    header: 'お気に入り',
    size: 70,
    cell: (info) => <span className="font-mono text-pink-600">{formatNumber(info.getValue())}</span>,
  }),

  // --- KPIs ---
  col.accessor('stock_days_7d', {
    header: '7日間分(日)',
    size: 80,
    cell: (info) => {
      const v = info.getValue();
      return (
        <span className={clsx('font-mono font-semibold',
          v == null ? 'text-gray-400'
          : v <= 0 ? 'text-red-600'
          : v <= 14 ? 'text-amber-600'
          : v >= 90 ? 'text-blue-600'
          : 'text-gray-900'
        )}>
          {formatDays(v)}
        </span>
      );
    },
  }),
  col.accessor('monthly_gap', {
    header: '1ヶ月差分',
    size: 80,
    cell: (info) => {
      const v = info.getValue();
      return (
        <span className={clsx('font-mono', v < 0 ? 'text-red-600' : 'text-gray-700')}>
          {v > 0 ? '+' : ''}{formatNumber(v)}
        </span>
      );
    },
  }),
  col.accessor('trend_coefficient', {
    header: 'トレンド',
    size: 70,
    cell: (info) => {
      const v = info.getValue();
      return (
        <span className={clsx('font-mono text-xs',
          v == null ? 'text-gray-400'
          : v > 1.1 ? 'text-green-600 font-bold'
          : v < 0.9 ? 'text-red-600'
          : 'text-gray-600'
        )}>
          {formatTrend(v)}
        </span>
      );
    },
  }),

  // --- Recommendation ---
  col.accessor('recommended_order_qty', {
    header: '推奨発注数',
    size: 80,
    cell: (info) => {
      const v = info.getValue();
      return (
        <span className={clsx('font-mono font-bold', v > 0 ? 'text-indigo-700' : 'text-gray-400')}>
          {v > 0 ? formatNumber(v) : '-'}
        </span>
      );
    },
  }),

  // --- Cost ---
  col.accessor('gross_margin_pct', {
    header: '粗利率',
    size: 60,
    cell: (info) => <span className="font-mono text-xs">{formatPercent(info.getValue())}</span>,
  }),

  // --- Sparkline ---
  col.accessor('daily_sales_30d', {
    header: '日次推移',
    size: 90,
    enableSorting: false,
    cell: (info) => <SalesSpark data={info.getValue() as any} />,
  }),

  // --- Simulation trigger ---
  col.display({
    id: 'simulate',
    header: '',
    size: 80,
    cell: (info) => (
      <button
        onClick={(e) => {
          e.stopPropagation();
          onSimulate(info.row.original.sku_code);
        }}
        className="px-2 py-1 text-xs text-indigo-600 border border-indigo-200 rounded hover:bg-indigo-50 font-semibold whitespace-nowrap"
      >
        試算
      </button>
    ),
  }),
];}  // end buildColumns

interface ProductTableProps {
  rows:        OrderAnalysisRow[];
  isLoading?:  boolean;
  onSimulate?: (skuCode: string) => void;
}

export function ProductTable({ rows, isLoading, onSimulate }: ProductTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'order_urgency', desc: false },
  ]);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);
  const [globalFilter, setGlobalFilter] = useState('');

  const columns = useMemo(
    () => buildColumns(onSimulate ?? (() => {})),
    [onSimulate]
  );

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, columnFilters, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        <span className="animate-pulse">データを読み込み中...</span>
      </div>
    );
  }

  return (
    <div>
      {/* Global search */}
      <div className="mb-3 flex gap-2">
        <input
          type="text"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder="品番・カラー・サイズで検索..."
          className="border border-gray-300 rounded px-3 py-1.5 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <span className="text-sm text-gray-500 self-center">
          {table.getFilteredRowModel().rows.length.toLocaleString()} / {rows.length.toLocaleString()} SKU
        </span>
      </div>

      {/* Scrollable table */}
      <div className="overflow-x-auto border border-gray-200 rounded-lg shadow-sm">
        <table className="min-w-max w-full text-sm border-collapse">
          <thead className="bg-gray-50 sticky top-0 z-10">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    style={{ width: header.getSize(), minWidth: header.getSize() }}
                    onClick={header.column.getToggleSortingHandler()}
                    className={clsx(
                      'px-2 py-2 text-left text-xs font-semibold text-gray-600 border-b border-gray-200 whitespace-nowrap',
                      header.column.getCanSort() ? 'cursor-pointer select-none hover:bg-gray-100' : ''
                    )}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getCanSort() && (
                        header.column.getIsSorted() === 'asc'  ? <ArrowUp size={10} /> :
                        header.column.getIsSorted() === 'desc' ? <ArrowDown size={10} /> :
                        <ArrowUpDown size={10} className="text-gray-300" />
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>

          <tbody>
            {table.getRowModel().rows.map((row) => {
              const urgency = row.original.order_urgency;
              const bgStyle = URGENCY_STYLES[urgency].bg;
              return (
                <tr key={row.id} className={clsx('border-b border-gray-100 hover:brightness-95', bgStyle)}>
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      style={{ width: cell.column.getSize(), minWidth: cell.column.getSize() }}
                      className="px-2 py-1.5 whitespace-nowrap"
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
