'use client';

import { useState, useEffect } from 'react';
import { AppHeader } from '@/components/AppHeader';
import {
  CheckCircle2, XCircle, AlertCircle, RefreshCw,
  Database, Clock, FileText, ExternalLink, Activity
} from 'lucide-react';

interface SourceStatus {
  name: string;
  label: string;
  status: 'ok' | 'failed' | 'no_data';
  filename: string | null;
  size: number | null;
  gcs_path: string | null;
  error: string | null;
  run_date: string | null;
  started: string | null;
  finished: string | null;
}

interface StatusResponse {
  sources: SourceStatus[];
  summary: { total: number; ok: number; failed: number; no_data: number };
  window: string;
  generated_at: string;
}

export default function IngestionStatusPage() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async () => {
    setRefreshing(true);
    try {
      const res = await fetch('/api/ingestion-status?days=7');
      if (res.ok) setData(await res.json());
    } catch {
      // ignore
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const intv = setInterval(fetchData, 60_000); // auto-refresh every 60s
    return () => clearInterval(intv);
  }, []);

  return (
    <>
      <AppHeader breadcrumbs={['データ取得状況']} />

      <main className="flex-1 px-6 py-4 overflow-y-auto">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <Database className="w-4 h-4 text-indigo-600" />
              データ取得状況
            </h1>
            <p className="text-xs text-gray-500 mt-0.5">
              ZOZOバックオフィスからの自動取得 (Pythonスクレイパー、毎朝06:30 JST実行)
            </p>
          </div>
          <button
            onClick={fetchData}
            disabled={refreshing}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-50"
          >
            <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} />
            更新
          </button>
        </div>

        {/* Summary */}
        {data && (
          <div className="grid grid-cols-4 gap-2 mb-4">
            <Stat label="全データソース" value={data.summary.total} unit="件" color="indigo" />
            <Stat label="成功"           value={data.summary.ok}    unit="件" color="green" icon={CheckCircle2} />
            <Stat label="失敗"           value={data.summary.failed} unit="件" color="red"  icon={XCircle} />
            <Stat label="未取得"         value={data.summary.no_data} unit="件" color="amber" icon={AlertCircle} />
          </div>
        )}

        {/* Status table */}
        <div className="bg-white border border-gray-200 rounded">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 border-b border-gray-200 text-gray-700">
              <tr>
                <th className="px-3 py-2 text-left font-semibold w-8">  </th>
                <th className="px-3 py-2 text-left font-semibold">データソース</th>
                <th className="px-3 py-2 text-left font-semibold">対象日</th>
                <th className="px-3 py-2 text-left font-semibold">最終実行</th>
                <th className="px-3 py-2 text-right font-semibold">サイズ</th>
                <th className="px-3 py-2 text-left font-semibold">GCS パス</th>
                <th className="px-3 py-2 text-left font-semibold">エラー</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={7} className="text-center py-6 text-gray-400">読み込み中…</td></tr>
              )}
              {!loading && data?.sources.map(s => (
                <SourceRow key={s.name} src={s} />
              ))}
            </tbody>
          </table>
        </div>

        {data && (
          <p className="text-[11px] text-gray-400 mt-2 text-right">
            最終更新: {new Date(data.generated_at).toLocaleString('ja-JP')}・
            集計対象: 過去{data.window}・
            自動更新: 60秒ごと
          </p>
        )}

        {/* Help section */}
        <details className="mt-6 bg-blue-50 border border-blue-200 rounded p-3">
          <summary className="cursor-pointer text-xs font-semibold text-blue-900 flex items-center gap-1">
            <Activity className="w-3 h-3" />
            自動取得フローについて
          </summary>
          <div className="mt-3 text-xs text-blue-900 space-y-2">
            <p>
              毎朝 <strong>06:30 JST</strong> に Cloud Scheduler が起動し、Cloud Run Job 上の
              Pythonスクレイパーが ZOZO バックオフィスにログインして 9種類の CSV を自動DLします。
            </p>
            <p>
              ダウンロードした CSV は GCS の
              <code className="bg-white px-1 mx-1 rounded">gs://...-raw-data/uploads/zozo/{`{type}`}/{`{date}`}/</code>
              に格納されます。
            </p>
            <p>
              その後 <strong>07:00 JST</strong> に ETL パイプラインが起動し、GCS の新しいCSVを
              読み取って BigQuery に取り込みます。
            </p>
            <p className="pt-2 border-t border-blue-200">
              将来的に ZOZO Partner API キーが発行されたら、スクレイピングは API 呼び出しに
              置き換えられます (それまでの暫定対応です)。
            </p>
          </div>
        </details>
      </main>
    </>
  );
}

// ── Components ────────────────────────────────────────────────────────────────

function Stat({ label, value, unit, color, icon: Icon }: any) {
  const accents: Record<string, string> = {
    indigo: 'from-indigo-500 to-indigo-600',
    green:  'from-emerald-500 to-emerald-600',
    red:    'from-red-500 to-red-600',
    amber:  'from-amber-500 to-amber-600',
  };
  return (
    <div className="bg-white border border-gray-200 rounded p-3 relative overflow-hidden">
      <div className={`absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r ${accents[color]}`} />
      <div className="flex items-center gap-1.5 mb-1">
        {Icon && <Icon className="w-3 h-3 text-gray-400" />}
        <span className="text-[10px] font-medium text-gray-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className="text-xl font-bold text-gray-900 tabular-nums">
        {value} <span className="text-[10px] text-gray-400 font-normal">{unit}</span>
      </div>
    </div>
  );
}

function SourceRow({ src }: { src: SourceStatus }) {
  const [icon, color, text] = ({
    ok:      [CheckCircle2, 'text-green-600 bg-green-50',   '成功'],
    failed:  [XCircle,      'text-red-600 bg-red-50',       '失敗'],
    no_data: [AlertCircle,  'text-amber-600 bg-amber-50',   '未取得'],
  } as any)[src.status];
  const Icon = icon;

  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50">
      <td className="px-3 py-2">
        <div className={`w-6 h-6 rounded flex items-center justify-center ${color}`}>
          <Icon className="w-3.5 h-3.5" />
        </div>
      </td>
      <td className="px-3 py-2">
        <div className="font-medium text-gray-900">{src.label}</div>
        <div className="text-[10px] text-gray-500 font-mono">{src.name}</div>
      </td>
      <td className="px-3 py-2 text-gray-600">
        {src.run_date || '—'}
      </td>
      <td className="px-3 py-2 text-gray-600">
        {src.finished
          ? new Date(src.finished).toLocaleString('ja-JP', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
          : <span className="text-gray-400">—</span>}
      </td>
      <td className="px-3 py-2 text-right text-gray-700 tabular-nums">
        {src.size ? `${(src.size / 1024).toFixed(1)} KB` : <span className="text-gray-400">—</span>}
      </td>
      <td className="px-3 py-2 text-gray-600 font-mono text-[10px] truncate max-w-[200px]">
        {src.gcs_path
          ? <span title={src.gcs_path}>{src.gcs_path.split('/').slice(-3).join('/')}</span>
          : <span className="text-gray-400">—</span>}
      </td>
      <td className="px-3 py-2 text-red-600 truncate max-w-[200px]">
        {src.error
          ? <span title={src.error}>{src.error}</span>
          : <span className="text-gray-400">—</span>}
      </td>
    </tr>
  );
}
