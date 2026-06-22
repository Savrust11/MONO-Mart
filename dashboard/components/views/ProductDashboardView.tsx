'use client';

import { useState, useEffect, useCallback } from 'react';
import { Package, TrendingUp, Percent, Coins } from 'lucide-react';
import { Plan1View } from './Plan1View';
import { Plan2View } from './Plan2View';
import { LoadingProgress } from '../LoadingProgress';

type Tab = 'plan1' | 'plan2' | 'detail';

// 発注管理表（項目詳細）の1行。API /api/period-report が返す形。
type Row = { kind: 'title' | 'sec' | 'item' | 'blank'; label: string; value: string | number | null; note: string };

const NA = '（データ未取得）';
function isoDaysAgo(n: number): string {
  const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10);
}
function isoToday(): string { return new Date().toISOString().slice(0, 10); }
// 昨年同期: 指定日の1年前（YYYY-MM-DD）
function yearAgo(iso: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return iso;
  return `${Number(iso.slice(0, 4)) - 1}${iso.slice(4)}`;
}

// 集計する実績期間の3択（BO仕様）
type PeriodMode = 'lastyear' | 'last30' | 'explicit';

export function ProductDashboardView({ code }: { code: string }) {
  const [start, setStart] = useState(isoDaysAgo(30));
  const [end, setEnd] = useState(isoDaysAgo(0));
  const [rows, setRows] = useState<Row[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false); // 進捗バー表示（完了アニメ含む）
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('plan1');
  // BO入力: 集計する実績期間の3択 + 想定の販売期間 + 総数指定
  const [periodMode, setPeriodMode] = useState<PeriodMode>('explicit');
  const [planStart, setPlanStart] = useState(isoDaysAgo(30)); // 想定の販売期間（lastyearモードで使用）
  const [planEnd, setPlanEnd] = useState(isoDaysAgo(0));
  const [totalQty, setTotalQty] = useState(''); // 総数指定（任意・SKU内訳の按分用）
  // 照会で確定した条件（案1/案2ビューへ渡す。入力中の都度fetchを避ける）
  const [applied, setApplied] = useState({ start: isoDaysAgo(30), end: isoDaysAgo(0), total: 0 });

  // 実績期間モードから実効 [start,end] を決定
  const resolvePeriod = useCallback((): { start: string; end: string } => {
    if (periodMode === 'last30') return { start: isoDaysAgo(29), end: isoToday() };
    if (periodMode === 'lastyear') return { start: yearAgo(planStart), end: yearAgo(planEnd) }; // 想定販売期間の昨年同期
    return { start, end }; // explicit
  }, [periodMode, planStart, planEnd, start, end]);

  const run = useCallback(async () => {
    const eff = resolvePeriod();
    const total = Math.max(0, parseInt(totalQty, 10) || 0);
    setApplied({ ...eff, total });
    setBusy(true); setLoading(true); setError(null);
    try {
      const url = `/api/period-report?product_code=${encodeURIComponent(code)}&start=${eff.start}&end=${eff.end}`;
      const res = await fetch(url);
      const json = await res.json();
      if (!res.ok) { setError(json.error || '取得に失敗しました'); setRows(null); }
      else setRows(json.data as Row[]);
    } catch (e) {
      setError('通信エラー: ' + String(e)); setRows(null);
    } finally { setLoading(false); }
  }, [code, resolvePeriod, totalQty]);

  const [sheetMsg, setSheetMsg] = useState<string | null>(null);
  const [sheetUrl, setSheetUrl] = useState<string | null>(null);
  const toSheet = useCallback(async () => {
    setSheetMsg('スプシ出力中…'); setSheetUrl(null);
    try {
      const res = await fetch(
        `/api/period-report/to-sheet?product_code=${encodeURIComponent(code)}&start=${applied.start}&end=${applied.end}`,
        { method: 'POST' });
      const j = await res.json();
      if (res.ok) { setSheetMsg(`✓ スプレッドシートに出力しました（${j.rows}行）`); setSheetUrl(j.url || null); }
      else setSheetMsg(`エラー: ${j.error || '失敗'}`);
    } catch (e) {
      setSheetMsg('通信エラー: ' + String(e));
    }
  }, [code, applied]);

  useEffect(() => { run(); /* 初回・品番変更時に自動照会 */ }, [code]); // eslint-disable-line react-hooks/exhaustive-deps

  // 時系列・SKU別は折りたたみ（PVT的に +/- で展開・折り畳み）。既定は折りたたみ。
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!rows) return;
    const def = new Set<string>();
    for (const r of rows) if (r.kind === 'sec' && /時系列|SKU別/.test(r.label)) def.add(r.label);
    setCollapsed(def);
  }, [rows]);
  const toggleSec = (label: string) =>
    setCollapsed((prev) => { const n = new Set(prev); if (n.has(label)) n.delete(label); else n.add(label); return n; });

  const pick = (label: string): string => {
    const r = rows?.find((x) => x.kind === 'item' && x.label === label);
    return r ? String(r.value) : '—';
  };
  const productName = rows ? pick('商品名') : '';
  const shop = rows ? pick('ショップ') : '';

  return (
    <div className="px-6 py-4">
      <div className="mb-4">
        <p className="text-xs text-gray-500">商品ダッシュボード — 品番×期間 実数照会</p>
        <h1 className="text-lg font-bold text-gray-900 mt-0.5">
          <span className="font-mono">{code}</span>
          {productName && productName !== '—' && (
            <span className="font-normal text-gray-700 ml-3 text-sm">{productName}</span>
          )}
        </h1>
        {shop && shop !== '—' && (
          <span className="inline-block mt-1 px-2 py-0.5 text-[10px] font-bold bg-indigo-100 text-indigo-700 rounded">
            {shop}
          </span>
        )}
      </div>

      {/* BO入力（集計する実績期間 3択 ＋ 想定の販売期間 ＋ 総数指定） */}
      <div className="bg-white border border-gray-200 rounded p-3 mb-4 space-y-3">
        {/* 実績期間モード */}
        <div className="flex flex-wrap items-center gap-4 text-[13px]">
          <span className="text-[11px] text-gray-500">集計する実績期間</span>
          {([
            ['lastyear', '指定なし（想定販売期間の昨年同期）'],
            ['last30', '直近30日'],
            ['explicit', '期間指定'],
          ] as [PeriodMode, string][]).map(([m, lbl]) => (
            <label key={m} className="inline-flex items-center gap-1 cursor-pointer">
              <input type="radio" name="pmode" checked={periodMode === m}
                onChange={() => setPeriodMode(m)} />
              <span className={periodMode === m ? 'text-gray-900' : 'text-gray-500'}>{lbl}</span>
            </label>
          ))}
        </div>

        {/* モード別の日付入力 */}
        <div className="flex flex-wrap items-end gap-3">
          {periodMode === 'lastyear' && (
            <>
              <DateField label="想定の販売期間（開始）" value={planStart} onChange={setPlanStart} />
              <span className="pb-2 text-gray-400">〜</span>
              <DateField label="（終了）" value={planEnd} onChange={setPlanEnd} />
              <span className="pb-2 text-[11px] text-indigo-600">
                → 実績は {yearAgo(planStart)} 〜 {yearAgo(planEnd)}（昨年同期）で集計
              </span>
            </>
          )}
          {periodMode === 'explicit' && (
            <>
              <DateField label="集計開始日" value={start} onChange={setStart} />
              <span className="pb-2 text-gray-400">〜</span>
              <DateField label="集計終了日" value={end} onChange={setEnd} />
            </>
          )}
          {periodMode === 'last30' && (
            <span className="pb-2 text-[11px] text-gray-500">実績は {isoDaysAgo(29)} 〜 {isoToday()} で集計</span>
          )}

          <div>
            <label className="block text-[11px] text-gray-500 mb-1">指定総数（任意・SKU内訳の按分）</label>
            <input type="number" min={0} value={totalQty} placeholder="未指定"
              onChange={(e) => setTotalQty(e.target.value)}
              className="px-2.5 py-1.5 border border-gray-300 rounded text-sm w-32" />
          </div>

          <button onClick={run} disabled={loading}
            className="px-5 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white rounded text-sm">
            {loading ? '照会中…' : '集計'}
          </button>
          {/* CSVは№13（出力＝スプシ）確定外のため非表示。APIは残置 */}
          {tab === 'detail' && !busy && rows && (
            <button onClick={toSheet}
              className="px-4 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded text-sm">
              スプシ出力
            </button>
          )}
        </div>
      </div>
      {tab === 'detail' && (sheetMsg || sheetUrl) && (
        <div className="text-xs text-gray-700 mb-3 flex items-center gap-3">
          {sheetMsg && <span>{sheetMsg}</span>}
          {sheetUrl && (
            <a href={sheetUrl} target="_blank" rel="noopener noreferrer"
              className="text-teal-700 underline hover:text-teal-800 font-medium">
              📊 スプレッドシートを開く
            </a>
          )}
        </div>
      )}

      {/* タブ切替（案1 / 項目詳細）※案2は実装予定 */}
      <div className="flex gap-1 border-b border-gray-200 mb-4">
        <TabBtn active={tab === 'plan1'} onClick={() => setTab('plan1')}>案1（SKU別明細）</TabBtn>
        <TabBtn active={tab === 'plan2'} onClick={() => setTab('plan2')}>案2（時系列）</TabBtn>
        <TabBtn active={tab === 'detail'} onClick={() => setTab('detail')}>項目詳細</TabBtn>
      </div>

      {tab === 'plan1' && <Plan1View code={code} start={applied.start} end={applied.end} totalQty={applied.total} />}
      {tab === 'plan2' && <Plan2View code={code} start={applied.start} end={applied.end} />}

      {tab === 'detail' && busy && <LoadingProgress active={loading} label="項目詳細を集計中" onDone={() => setBusy(false)} />}

      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded p-3 text-xs text-rose-700 mb-4">{error}</div>
      )}

      {/* KPI */}
      {tab === 'detail' && !busy && rows && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
          <Kpi label="合計販売数" value={pick('合計販売数')} unit="点" icon={Package} color="indigo" />
          <Kpi label="平均売価(税抜)" value={pick('平均売価（税抜）')} unit="円" icon={Coins} color="blue" />
          <Kpi label="値引率" value={pick('合計値引率(%)')} unit="%" icon={Percent} color="amber" />
          <Kpi label="粗利率" value={pick('合計粗利率(%)')} unit="%" icon={TrendingUp} color="rose" />
        </div>
      )}

      {/* 全項目テーブル */}
      {tab === 'detail' && !busy && rows && (
        <div className="bg-white border border-gray-200 rounded overflow-hidden">
          <table className="w-full text-[13px]">
            <tbody>
              {(() => {
                let curSec = '';
                return rows.map((r, i) => {
                  if (r.kind === 'title') return null;
                  if (r.kind === 'sec') {
                    curSec = r.label;
                    const isFold = /時系列|SKU別/.test(r.label);
                    const open = !collapsed.has(r.label);
                    return (
                      <tr key={i}>
                        <td colSpan={3}
                          className={`bg-gray-100 font-bold px-3 py-1.5 ${isFold ? 'cursor-pointer select-none hover:bg-gray-200' : ''}`}
                          onClick={isFold ? () => toggleSec(r.label) : undefined}>
                          {isFold ? (open ? '▾ ' : '▸ ') : ''}{r.label}
                        </td>
                      </tr>
                    );
                  }
                  if (collapsed.has(curSec)) return null; // 折りたたみ中の項目は隠す
                  if (r.kind === 'blank') return <tr key={i}><td className="h-1.5" colSpan={3} /></tr>;
                  const na = String(r.value) === NA;
                  const isImg = typeof r.value === 'string' && r.value.startsWith('http');
                  return (
                    <tr key={i} className="border-b border-gray-50">
                      <td className="px-3 py-1.5 text-gray-600 w-[230px]">{r.label}</td>
                      <td className={`px-3 py-1.5 font-semibold w-[150px] ${na ? 'text-gray-400 font-normal' : ''}`}>
                        {isImg ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={r.value as string} alt="商品画像" className="h-20 w-20 object-cover rounded border border-gray-200" />
                        ) : (
                          typeof r.value === 'number' ? r.value.toLocaleString('ja-JP') : r.value
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-gray-400 text-[11px] italic">{r.note}</td>
                    </tr>
                  );
                });
              })()}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'detail' && !rows && !loading && !error && (
        <div className="p-8 text-gray-400 text-sm">期間を指定して「照会」を押してください。</div>
      )}
    </div>
  );
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <label className="block text-[11px] text-gray-500 mb-1">{label}</label>
      <input type="date" value={value} onChange={(e) => onChange(e.target.value)}
        className="px-2.5 py-1.5 border border-gray-300 rounded text-sm" />
    </div>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`px-4 py-2 text-[13px] font-medium border-b-2 -mb-px ${
        active ? 'border-blue-600 text-blue-700' : 'border-transparent text-gray-500 hover:text-gray-700'
      }`}>
      {children}
    </button>
  );
}

function Kpi({
  label, value, unit, icon: Icon, color,
}: {
  label: string; value: string; unit: string; icon: any;
  color: 'indigo' | 'blue' | 'amber' | 'rose';
}) {
  const map = {
    indigo: 'from-indigo-500 to-indigo-600', blue: 'from-blue-500 to-blue-600',
    amber: 'from-amber-500 to-amber-600', rose: 'from-rose-500 to-rose-600',
  };
  return (
    <div className="bg-white border border-gray-200 rounded p-3 relative overflow-hidden">
      <div className={`absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r ${map[color]}`} />
      <div className="text-[11px] text-gray-500 flex items-center gap-1"><Icon className="w-3 h-3" />{label}</div>
      <div className="text-xl font-bold text-gray-900 mt-1">
        {value}<span className="text-[11px] text-gray-400 font-normal ml-1">{unit}</span>
      </div>
    </div>
  );
}
