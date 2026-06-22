'use client';

import { OrderAnalysisRow } from '@/lib/bigquery';
import { formatNumber, formatDays, URGENCY_STYLES } from '@/lib/utils';
import { clsx } from 'clsx';

interface ColorSizeMatrixProps {
  rows: OrderAnalysisRow[];
  productCode: string;
}

/**
 * Grid view of a single product's color × size matrix.
 * Each cell shows inventory, 7-day sales, recommended order qty.
 */
export function ColorSizeMatrix({ rows, productCode }: ColorSizeMatrixProps) {
  const filtered = rows.filter((r) => r.product_code === productCode);
  if (filtered.length === 0) return null;

  // Unique colors and sizes
  const colors = [...new Set(filtered.map((r) => r.color_name))];
  const sizes  = [...new Set(filtered.map((r) => r.size))];

  const SIZE_ORDER = ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL', 'FREE'];
  sizes.sort((a, b) => {
    const ia = SIZE_ORDER.indexOf(a.toUpperCase());
    const ib = SIZE_ORDER.indexOf(b.toUpperCase());
    if (ia === -1 && ib === -1) return a.localeCompare(b);
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });

  const rowMap = new Map(filtered.map((r) => [`${r.color_name}__${r.size}`, r]));

  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-xs">
        <thead>
          <tr>
            <th className="border border-gray-200 px-3 py-1.5 bg-gray-50 text-left font-semibold">カラー</th>
            {sizes.map((size) => (
              <th key={size} className="border border-gray-200 px-3 py-1.5 bg-gray-50 font-semibold text-center">
                {size}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {colors.map((color) => (
            <tr key={color}>
              <td className="border border-gray-200 px-3 py-1.5 font-medium bg-gray-50 whitespace-nowrap">
                {color}
              </td>
              {sizes.map((size) => {
                const r = rowMap.get(`${color}__${size}`);
                if (!r) {
                  return (
                    <td key={size} className="border border-gray-200 px-2 py-1 text-center text-gray-300">
                      -
                    </td>
                  );
                }
                const bgStyle = URGENCY_STYLES[r.order_urgency].bg;
                return (
                  <td key={size} className={clsx('border border-gray-200 px-2 py-1 text-center', bgStyle)}>
                    <div className="font-mono font-bold">{formatNumber(r.free_inventory)}</div>
                    <div className="text-gray-500">
                      {r.sales_7d}日/{formatDays(r.stock_days_7d)}
                    </div>
                    {r.recommended_order_qty > 0 && (
                      <div className="text-indigo-700 font-bold">→{formatNumber(r.recommended_order_qty)}</div>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-gray-400 mt-1">
        セル内: フリー在庫 / 7日販売数・在庫日数 / 推奨発注数
      </p>
    </div>
  );
}
