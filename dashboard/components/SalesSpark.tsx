'use client';
import { Sparklines, SparklinesLine, SparklinesReferenceLine } from 'react-sparklines';

interface DailyPoint {
  sale_date: string;
  qty: number;
}

interface SalesSparkProps {
  data: DailyPoint[];
  height?: number;
  width?: number;
}

/**
 * Compact sparkline chart for the product table.
 * Shows last 30 days of daily sales.
 */
export function SalesSpark({ data, height = 24, width = 80 }: SalesSparkProps) {
  if (!data || data.length === 0) {
    return <span className="text-gray-300 text-xs">-</span>;
  }

  // Sort ascending by date. BigQuery DATE inside an ARRAY<STRUCT> comes back
  // as a { value: 'YYYY-MM-DD' } object (BigQueryDate), not a string, so we
  // normalise before comparing — otherwise .localeCompare throws.
  const dateKey = (d: DailyPoint): string => {
    const v: unknown = (d as { sale_date: unknown }).sale_date;
    if (typeof v === 'string') return v;
    if (v && typeof v === 'object' && 'value' in v) return String((v as { value: unknown }).value);
    return String(v ?? '');
  };
  const sorted = [...data].sort((a, b) => dateKey(a).localeCompare(dateKey(b)));
  const values = sorted.map((d) => d.qty);
  const avg    = values.reduce((s, v) => s + v, 0) / values.length;

  return (
    <div title={`日次販売(30日): 平均${avg.toFixed(1)}/日`} className="inline-block">
      <Sparklines data={values} width={width} height={height} margin={2}>
        <SparklinesLine color="#3b82f6" style={{ fill: 'none', strokeWidth: 1.5 }} />
        <SparklinesReferenceLine type="mean" style={{ stroke: '#e5e7eb', strokeDasharray: '2,2' }} />
      </Sparklines>
    </div>
  );
}
