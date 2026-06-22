'use client';

import { useEffect, useState } from 'react';
import { formatNumber, todayJST } from '@/lib/utils';

// ── Types ─────────────────────────────────────────────────────────────────────

interface StepRecord {
  step: string;
  status: 'success' | 'failed' | 'running';
  rows_processed: number | null;
  duration_ms: number | null;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
}

interface RunRecord {
  run_id: string;
  run_date: string;
  status: 'success' | 'failed';
  total_ms: number;
  started_at: string;
  steps: StepRecord[];
}

interface QualityReport {
  dataset: string;
  run_date: string;
  row_count: number;
  total_checks: number;
  passed_checks: number;
  failed_checks: number;
  passed: boolean;
  validated_at: string;
  all_checks_json: string;
}

interface TableCount {
  dataset: string;
  table: string;
  row_count: number;
  last_updated: string;
}

interface StatusData {
  pipeline_runs: RunRecord[];
  quality_reports: QualityReport[];
  table_counts: TableCount[];
  summary: {
    last_run_date: string | null;
    last_run_status: string | null;
    runs_last_7d: number;
    failures_last_7d: number;
  };
}

// ── Step labels ───────────────────────────────────────────────────────────────

const STEP_LABELS: Record<string, string> = {
  extract_zozo_sales:          'ZOZO 販売取得',
  extract_zozo_inventory:      'ZOZO 在庫取得',
  extract_sheets_reservations: 'Sheets 予約',
  extract_cost_excel:          '原価マスター',
  sync_product_master:         '商品マスター',
  rebuild_kpi_mart:            'KPI マート',
};

const STEP_ORDER = Object.keys(STEP_LABELS);

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000)  return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

// ── Components ────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    success: { label: '成功', cls: 'bg-green-100 text-green-800' },
    failed:  { label: '失敗', cls: 'bg-red-100 text-red-800' },
    running: { label: '実行中', cls: 'bg-blue-100 text-blue-800' },
  };
  const { label, cls } = map[status] ?? { label: status, cls: 'bg-gray-100 text-gray-700' };
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold ${cls}`}>
      {label}
    </span>
  );
}

function KpiCard({
  label, value, sub, color,
}: { label: string; value: string; sub: string; color: string }) {
  const borderMap: Record<string, string> = {
    green:  'border-t-green-400',
    red:    'border-t-red-400',
    blue:   'border-t-blue-400',
    purple: 'border-t-violet-400',
  };
  return (
    <div className={`bg-white rounded-xl p-4 border border-gray-200 border-t-4 ${borderMap[color] ?? ''}`}>
      <div className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-2">{label}</div>
      <div className="text-3xl font-black text-gray-900">{value}</div>
      <div className="text-xs text-gray-400 mt-1">{sub}</div>
    </div>
  );
}

function RunRow({ run }: { run: RunRecord }) {
  const [expanded, setExpanded] = useState(false);
  const completedSteps = run.steps.filter(s => s.status === 'success').length;
  const stepMap = Object.fromEntries(run.steps.map(s => [s.step, s]));

  return (
    <>
      <tr
        className="cursor-pointer hover:bg-gray-50"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-4 py-3 font-semibold">{run.run_date}</td>
        <td className="px-4 py-3"><StatusBadge status={run.status} /></td>
        <td className="px-4 py-3 font-mono text-sm">{fmtDuration(run.total_ms)}</td>
        <td className="px-4 py-3 text-sm text-gray-600">{completedSteps} / {STEP_ORDER.length}</td>
        <td className="px-4 py-3 text-xs text-gray-400">{run.started_at.slice(11, 16)} UTC</td>
        <td className="px-4 py-3 text-xs text-gray-400">{expanded ? '▲' : '▼'} 詳細</td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={6} className="p-0 bg-gray-50">
            <div className="grid grid-cols-6 gap-px bg-gray-200">
              {STEP_ORDER.map(key => {
                const s = stepMap[key];
                if (!s) {
                  return (
                    <div key={key} className="bg-white p-3 border-t-2 border-gray-200 opacity-50">
                      <div className="text-xs font-semibold text-gray-500 truncate">{STEP_LABELS[key]}</div>
                      <div className="text-xs text-gray-400 mt-1">スキップ</div>
                    </div>
                  );
                }
                const borderColor = s.status === 'success' ? 'border-green-400' : 'border-red-400';
                const bg = s.status === 'failed' ? 'bg-red-50' : 'bg-white';
                return (
                  <div key={key} className={`${bg} p-3 border-t-2 ${borderColor}`}>
                    <div className="text-xs font-semibold text-gray-700 truncate">{STEP_LABELS[key]}</div>
                    <div className="text-xs text-gray-500 mt-1">
                      {s.rows_processed != null && s.rows_processed > 0
                        ? `${formatNumber(s.rows_processed)} 件`
                        : s.status === 'success' ? '完了' : ''}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">{fmtDuration(s.duration_ms)}</div>
                    {s.error_message && (
                      <div className="text-xs text-red-600 mt-1 leading-tight">{s.error_message}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function QualityCard({ report }: { report: QualityReport }) {
  let checks: Array<{ check_name: string; passed: boolean; message: string }> = [];
  try {
    checks = JSON.parse(report.all_checks_json.replace(/'/g, '"'));
  } catch {
    // ignore parse errors
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div>
          <div className="text-sm font-bold text-gray-800">{report.dataset}</div>
          <div className="text-xs text-gray-400">{formatNumber(report.row_count)} 件 / {report.total_checks} チェック</div>
        </div>
        <StatusBadge status={report.passed ? 'success' : 'failed'} />
      </div>
      <div className="divide-y divide-gray-100">
        {checks.map(c => (
          <div key={c.check_name} className="flex items-start gap-2 px-4 py-2">
            <span className={`mt-0.5 text-sm flex-shrink-0 ${c.passed ? 'text-green-500' : 'text-red-500'}`}>
              {c.passed ? '✓' : '✗'}
            </span>
            <span className="text-xs font-mono text-gray-400 w-44 flex-shrink-0">{c.check_name}</span>
            <span className={`text-xs ${c.passed ? 'text-gray-600' : 'text-red-700 font-semibold'}`}>
              {c.message}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function StatusPage() {
  const [data, setData] = useState<StatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [date, setDate] = useState(todayJST());

  useEffect(() => {
    setLoading(true);
    fetch(`/api/status?date=${date}`)
      .then(r => r.json())
      .then(d => { setData(d); setError(null); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [date]);

  const DATASET_COLORS: Record<string, string> = {
    raw_layer:       'text-amber-600',
    analytics_layer: 'text-blue-600',
    mart_layer:      'text-violet-600',
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <div>
          <h1 className="text-base font-bold text-gray-900">データ確認画面</h1>
          <p className="text-xs text-gray-400">パイプライン実行状況・データ品質チェック</p>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="date"
            value={date}
            onChange={e => setDate(e.target.value)}
            className="border border-gray-300 rounded-md px-3 py-1.5 text-sm"
          />
          <a
            href="/dashboard"
            className="text-sm font-semibold text-indigo-600 hover:text-indigo-800"
          >
            ← 発注分析へ
          </a>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-24 text-gray-400 text-sm">
          データを読み込み中...
        </div>
      )}

      {error && (
        <div className="m-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          エラー: {error}
        </div>
      )}

      {data && !loading && (
        <div className="p-6 flex flex-col gap-5">

          {/* KPI summary */}
          <div className="grid grid-cols-4 gap-3">
            <KpiCard
              label="直近7日 成功率"
              value={data.summary.runs_last_7d > 0
                ? `${Math.round((data.summary.runs_last_7d - data.summary.failures_last_7d) / data.summary.runs_last_7d * 100)}%`
                : '-'}
              sub="パイプライン実行"
              color="green"
            />
            <KpiCard
              label="直近7日 失敗数"
              value={String(data.summary.failures_last_7d)}
              sub="要確認"
              color="red"
            />
            <KpiCard
              label="最終実行日"
              value={data.summary.last_run_date ?? '-'}
              sub={data.summary.last_run_status === 'success' ? '正常完了' : data.summary.last_run_status ?? '-'}
              color="blue"
            />
            <KpiCard
              label="実行回数（7日）"
              value={String(data.summary.runs_last_7d)}
              sub="夜間バッチ"
              color="purple"
            />
          </div>

          {/* Pipeline run history */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
              <h2 className="text-sm font-bold text-gray-900">パイプライン実行履歴（直近7日）</h2>
              <span className="text-xs text-gray-400">行をクリックでステップ詳細を展開</span>
            </div>
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b-2 border-gray-200 text-left">
                  {['実行日','ステータス','総時間','完了ステップ','開始時刻 (UTC)',''].map(h => (
                    <th key={h} className="px-4 py-2 text-xs font-bold text-gray-500 uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.pipeline_runs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                      実行履歴がありません
                    </td>
                  </tr>
                ) : (
                  data.pipeline_runs.map(run => <RunRow key={run.run_id} run={run} />)
                )}
              </tbody>
            </table>
          </div>

          {/* Data quality checks */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
              <h2 className="text-sm font-bold text-gray-900">データ品質チェック結果</h2>
              <span className="text-xs text-gray-400">対象日: {date}</span>
            </div>
            <div className="p-4 grid grid-cols-2 gap-3">
              {data.quality_reports.length === 0 ? (
                <div className="col-span-2 py-8 text-center text-gray-400 text-sm">
                  品質チェック結果がありません（パイプラインが未実行の可能性があります）
                </div>
              ) : (
                data.quality_reports.map(r => (
                  <QualityCard key={r.dataset} report={r} />
                ))
              )}
            </div>
          </div>

          {/* Table row counts */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-3 border-b border-gray-200">
              <h2 className="text-sm font-bold text-gray-900">BigQuery テーブル行数</h2>
            </div>
            <div className="p-4 grid grid-cols-3 gap-2">
              {data.table_counts.map(c => (
                <div
                  key={`${c.dataset}.${c.table}`}
                  className="flex items-center justify-between bg-gray-50 border border-gray-200 rounded-lg px-4 py-3"
                >
                  <div>
                    <div className={`text-xs font-bold ${DATASET_COLORS[c.dataset] ?? 'text-gray-600'}`}>
                      {c.table}
                    </div>
                    <div className="text-xs text-gray-400 font-mono">{c.dataset}</div>
                  </div>
                  <div className="text-lg font-black text-gray-900 font-mono">
                    {formatNumber(c.row_count)}
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      )}
    </div>
  );
}
