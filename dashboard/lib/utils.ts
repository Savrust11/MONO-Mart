import { format } from 'date-fns';
import { ja } from 'date-fns/locale';

export function todayJST(): string {
  const now = new Date();
  // Adjust for JST (UTC+9)
  const jst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  return jst.toISOString().slice(0, 10);
}

export function formatDate(dateStr: string): string {
  return format(new Date(dateStr), 'yyyy/MM/dd', { locale: ja });
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return '-';
  return n.toLocaleString('ja-JP');
}

export function formatDays(days: number | null | undefined): string {
  if (days == null) return '-';
  if (days < 0) return `${Math.round(days)}日`;
  return `${Math.round(days)}日`;
}

export function formatPercent(ratio: number | null | undefined): string {
  if (ratio == null) return '-';
  return `${(ratio * 100).toFixed(1)}%`;
}

export function formatTrend(coeff: number | null | undefined): string {
  if (coeff == null) return '-';
  const pct = ((coeff - 1) * 100).toFixed(1);
  return coeff >= 1 ? `+${pct}%` : `${pct}%`;
}

export const URGENCY_STYLES = {
  CRITICAL:  { bg: 'bg-red-100',   text: 'text-red-800',   badge: 'bg-red-500 text-white',   label: '欠品' },
  WARNING:   { bg: 'bg-amber-50',  text: 'text-amber-800', badge: 'bg-amber-400 text-white',  label: '警告' },
  OK:        { bg: 'bg-white',     text: 'text-gray-900',  badge: 'bg-green-100 text-green-800', label: 'OK' },
  OVERSTOCK: { bg: 'bg-blue-50',   text: 'text-blue-900',  badge: 'bg-blue-200 text-blue-800',  label: '過剰' },
} as const;
