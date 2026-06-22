'use client';

import { useState, useEffect } from 'react';
import { AppHeader } from '@/components/AppHeader';
import {
  Sparkles, Play, CheckCircle2, AlertCircle, Loader2,
  FileSpreadsheet, BarChart3, Database, Wrench, Workflow
} from 'lucide-react';
import type { ManusSkill } from '@/lib/manus';

const CATEGORY_META = {
  analysis:    { label: '分析',    icon: BarChart3,       color: 'bg-purple-100 text-purple-700' },
  output:      { label: '出力',    icon: FileSpreadsheet, color: 'bg-green-100 text-green-700' },
  data:        { label: 'データ',  icon: Database,        color: 'bg-blue-100 text-blue-700' },
  integration: { label: '連携',    icon: Workflow,        color: 'bg-orange-100 text-orange-700' },
  tool:        { label: 'ツール',  icon: Wrench,          color: 'bg-gray-100 text-gray-700' },
};

interface ExecutionResult {
  status: 'completed' | 'pending' | 'failed';
  output?: any;
  output_url?: string;
  error?: string;
  task_id?: string;
}

export default function ManusPage() {
  const [skills, setSkills] = useState<ManusSkill[]>([]);
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, ExecutionResult>>({});

  useEffect(() => {
    fetch('/api/manus/skills')
      .then(r => r.json())
      .then(data => {
        setSkills(data.skills || []);
        setConfigured(!!data.configured);
      })
      .finally(() => setLoading(false));
  }, []);

  const executeSkill = async (skillName: string) => {
    setExecuting(skillName);
    setResults(prev => ({ ...prev, [skillName]: { status: 'pending' } }));
    try {
      const res = await fetch('/api/manus/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill: skillName, params: {} }),
      });
      const data = await res.json();
      setResults(prev => ({ ...prev, [skillName]: data }));
    } catch (err: any) {
      setResults(prev => ({
        ...prev,
        [skillName]: { status: 'failed', error: err.message }
      }));
    } finally {
      setExecuting(null);
    }
  };

  const grouped = skills.reduce<Record<string, ManusSkill[]>>((acc, s) => {
    (acc[s.category] = acc[s.category] || []).push(s);
    return acc;
  }, {});

  return (
    <>
      <AppHeader breadcrumbs={['Manus スキル']} />

      <main className="flex-1 px-8 py-6 overflow-y-auto">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Sparkles className="w-6 h-6 text-indigo-600" />
              Manus スキル
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              MONO BACK OFFICE と連携している 12 種類の Manus スキル
            </p>
          </div>
          <div className={`px-3 py-1.5 rounded-md text-xs font-medium ${
            configured
              ? 'bg-green-100 text-green-700'
              : 'bg-amber-100 text-amber-700'
          }`}>
            {configured ? '✓ Manus API 接続済み' : '⚠ Manus API キー未設定'}
          </div>
        </div>

        {/* Configuration warning */}
        {!configured && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
            <h3 className="text-sm font-semibold text-amber-900 mb-1">
              Manus API キーが未設定です
            </h3>
            <p className="text-xs text-amber-800 mb-2">
              実際にスキルを実行するには、環境変数 <code className="bg-amber-100 px-1 rounded">MANUS_API_KEY</code> に Manus 発行の API キーを設定してください。
            </p>
            <code className="block text-xs bg-amber-100 text-amber-900 p-2 rounded font-mono">
              # .env.local{'\n'}
              MANUS_API_KEY=your-manus-api-key{'\n'}
              MANUS_API_BASE_URL=https://api.manus.space  # default{'\n'}
              MANUS_WORKSPACE_ID=your-workspace-id  # optional
            </code>
          </div>
        )}

        {/* Skills grouped by category */}
        {loading ? (
          <div className="text-center py-12 text-gray-400">読み込み中...</div>
        ) : (
          Object.entries(grouped).map(([category, items]) => {
            const meta = CATEGORY_META[category as keyof typeof CATEGORY_META];
            const Icon = meta.icon;
            return (
              <section key={category} className="mb-8">
                <div className="flex items-center gap-2 mb-3">
                  <div className={`px-2 py-1 rounded text-xs font-medium ${meta.color}`}>
                    <Icon className="w-3 h-3 inline mr-1" />
                    {meta.label}
                  </div>
                  <span className="text-xs text-gray-500">{items.length} skills</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {items.map(skill => (
                    <SkillCard
                      key={skill.name}
                      skill={skill}
                      executing={executing === skill.name}
                      result={results[skill.name]}
                      onExecute={() => executeSkill(skill.name)}
                    />
                  ))}
                </div>
              </section>
            );
          })
        )}
      </main>
    </>
  );
}

function SkillCard({
  skill, executing, result, onExecute,
}: {
  skill: ManusSkill;
  executing: boolean;
  result?: ExecutionResult;
  onExecute: () => void;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 hover:border-indigo-300 transition-colors">
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-mono text-sm font-semibold text-gray-900">{skill.name}</h3>
          <p className="text-xs text-gray-600 mt-1 leading-relaxed">{skill.description}</p>
        </div>
      </div>
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100">
        <div className="text-xs">
          {result?.status === 'completed' && (
            <span className="flex items-center gap-1 text-green-600">
              <CheckCircle2 className="w-3 h-3" /> 実行完了
            </span>
          )}
          {result?.status === 'failed' && (
            <span className="flex items-center gap-1 text-red-600" title={result.error}>
              <AlertCircle className="w-3 h-3" /> 失敗
            </span>
          )}
          {result?.status === 'pending' && (
            <span className="flex items-center gap-1 text-blue-600">
              <Loader2 className="w-3 h-3 animate-spin" /> 実行中
            </span>
          )}
          {!result && <span className="text-gray-400">未実行</span>}
        </div>
        <button
          onClick={onExecute}
          disabled={executing}
          className="flex items-center gap-1 px-3 py-1 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          <Play className="w-3 h-3" />
          実行
        </button>
      </div>
      {result?.error && (
        <div className="mt-2 p-2 bg-red-50 border border-red-100 rounded text-xs text-red-700 break-all">
          {result.error}
        </div>
      )}
      {result?.output_url && (
        <a
          href={result.output_url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 block text-xs text-indigo-600 hover:underline"
        >
          📎 結果ファイルを開く →
        </a>
      )}
    </div>
  );
}
