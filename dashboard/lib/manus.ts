/**
 * Manus Platform API Client
 *
 * Wraps the Manus REST API for executing skills and managing tasks.
 * Configure via env vars:
 *   MANUS_API_BASE_URL  (default: https://api.manus.space)
 *   MANUS_API_KEY       (required)
 *   MANUS_WORKSPACE_ID  (optional)
 */

export interface ManusSkill {
  name: string;
  description: string;
  category: 'analysis' | 'output' | 'data' | 'integration' | 'tool';
  status: 'imported' | 'available';
  doc_url?: string;
}

export interface ManusExecuteRequest {
  skill: string;
  params?: Record<string, any>;
  async?: boolean;
}

export interface ManusExecuteResponse {
  task_id?: string;
  status: 'completed' | 'pending' | 'failed';
  output?: any;
  output_url?: string;
  error?: string;
}

// The 12 skills imported into the client's Manus environment.
// Source: skill_documentation.pdf
export const MANUS_SKILLS: ManusSkill[] = [
  {
    name: 'zozo-ad-report',
    description: 'ZOZOADのCSVレポートをダウンロードし、Googleスプレッドシートを更新します。',
    category: 'output',
    status: 'imported',
  },
  {
    name: 'zozo-affinity-analysis',
    description: 'ブランド間の買い回りデータと指標を組み合わせ、相性の良いショップを分析します。',
    category: 'analysis',
    status: 'imported',
  },
  {
    name: 'zozo-repeat-order-excel',
    description: 'リピート発注管理表（Googleスプレッドシート）を自動生成します。',
    category: 'output',
    status: 'imported',
  },
  {
    name: 'zozo-inventory-forecast',
    description: 'カテゴリ別係数と在庫データから、将来の在庫消化予測を行います。',
    category: 'analysis',
    status: 'imported',
  },
  {
    name: 'zozo-md-plan',
    description: '注文・原価・買い回りデータを統合し、MD計画を自動生成します。',
    category: 'analysis',
    status: 'imported',
  },
  {
    name: 'zozo-order-data',
    description: 'MONO-MART全ショップのZOZO注文生データの構造と定義を提供します。',
    category: 'data',
    status: 'imported',
  },
  {
    name: 'zozo-timesale-upload',
    description: 'タイムセール用ファイルの作成、アップロード、設定変更を自動化します。',
    category: 'output',
    status: 'imported',
  },
  {
    name: 'zozo-same-item-cross-buy',
    description: '同一品番の併売分析を行い、カラー展開戦略を提案します。',
    category: 'analysis',
    status: 'imported',
  },
  {
    name: 'mono-fitting',
    description: 'AI試着体験アプリ「MONO FITTING」の開発・運用手順を提供します。',
    category: 'integration',
    status: 'imported',
  },
  {
    name: 'zozo-mono-backoffice',
    description: '分析Webアプリ「MONO BACK OFFICE」の構成と更新手順を提供します。',
    category: 'integration',
    status: 'imported',
  },
  {
    name: 'manus-api',
    description: 'ManusのタスクやプロジェクトをAPI経由で管理するためのスキルです。',
    category: 'tool',
    status: 'imported',
  },
  {
    name: 'gws-best-practices',
    description: 'Google Workspace CLI (gws) の最適な利用方法を提供します。',
    category: 'tool',
    status: 'imported',
  },
];

export class ManusClient {
  private baseUrl: string;
  private apiKey: string | undefined;
  private workspaceId: string | undefined;

  constructor() {
    this.baseUrl = process.env.MANUS_API_BASE_URL || 'https://api.manus.space';
    this.apiKey = process.env.MANUS_API_KEY;
    this.workspaceId = process.env.MANUS_WORKSPACE_ID;
  }

  isConfigured(): boolean {
    return !!this.apiKey;
  }

  async listSkills(): Promise<ManusSkill[]> {
    // Returns the static skill list. In production this would call:
    //   GET /v1/workspaces/{workspaceId}/skills
    return MANUS_SKILLS;
  }

  async executeSkill(req: ManusExecuteRequest): Promise<ManusExecuteResponse> {
    if (!this.isConfigured()) {
      return {
        status: 'failed',
        error: 'Manus API not configured. Set MANUS_API_KEY environment variable.',
      };
    }

    const endpoint = `${this.baseUrl}/v1/skills/${req.skill}/execute`;
    try {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
          ...(this.workspaceId ? { 'X-Workspace-Id': this.workspaceId } : {}),
        },
        body: JSON.stringify({
          params: req.params || {},
          async: req.async ?? false,
        }),
      });

      if (!resp.ok) {
        const text = await resp.text();
        return {
          status: 'failed',
          error: `HTTP ${resp.status}: ${text.slice(0, 200)}`,
        };
      }

      const data = await resp.json();
      return {
        status: data.status || 'completed',
        task_id: data.task_id,
        output: data.output,
        output_url: data.output_url,
      };
    } catch (err: any) {
      return {
        status: 'failed',
        error: err.message || String(err),
      };
    }
  }

  async getTaskStatus(taskId: string): Promise<ManusExecuteResponse> {
    if (!this.isConfigured()) {
      return { status: 'failed', error: 'Manus API not configured' };
    }
    try {
      const resp = await fetch(`${this.baseUrl}/v1/tasks/${taskId}`, {
        headers: { 'Authorization': `Bearer ${this.apiKey}` },
      });
      if (!resp.ok) {
        return { status: 'failed', error: `HTTP ${resp.status}` };
      }
      return await resp.json();
    } catch (err: any) {
      return { status: 'failed', error: err.message };
    }
  }
}

export const manus = new ManusClient();
