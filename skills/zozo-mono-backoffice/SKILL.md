---
name: zozo-mono-backoffice
description: MONO BACK OFFICE（株式会社MONO-MARTのZOZO分析Webアプリ）のプロジェクト構成・ページ追加・データ更新手順を提供するスキル。MONO BACK OFFICEへの新機能追加、UI修正、データ更新の依頼時に使用する。
---

# MONO BACK OFFICE スキル

MONO BACK OFFICEは株式会社MONO-MARTのZOZOデータ分析用Webアプリ。独立して運用するWebアプリケーションとして構築（Manusはこのアプリを作成するツールとして活用）。

## プロジェクト情報

- **プロジェクト名**: `mono-back-office`
- **プロジェクトパス**: `/home/ubuntu/mono-back-office`
- **テンプレート**: web-db-user（React 19 + Tailwind 4 + shadcn/ui + Express + DB）
- **デザイン**: ダークテーマ対応、和風インダストリアルデザイン
- **データ形式**: CDN上のJSONファイルをfetchで取得 + バックエンドAPI経由のデータ処理

## アーキテクチャ

```
[フロントエンド: React 19 + Tailwind 4 + shadcn/ui]
  ↓ API呼び出し
[バックエンド: Express (Node.js)]
  ↓ データ取得
[データソース: S3 CDN / Google Drive / Google Sheets API]
```

### Google Sheets API方式（サービスアカウント）

デプロイ環境（manus.space）からGoogle Sheets APIを呼ぶために**サービスアカウント方式**を採用:
1. Google Cloud Projectでサービスアカウントを作成
2. JSONキーをsecretsに設定（`GOOGLE_SERVICE_ACCOUNT_KEY`）
3. テンプレートSpreadsheetをサービスアカウントに共有
4. サーバーサイドからSheets APIを直接呼び出し

**重要**: `gws` CLIはサンドボックス環境でのみ使用可能。デプロイ環境では使えないため、Google Sheets/Drive操作はサービスアカウント経由のAPI呼び出しで実装する。

## ページ構成

詳細は `references/page_structure.md` を参照。

| パス | ページ | 関連スキル |
|---|---|---|
| `/` | 同一品番併売分析 | `zozo-same-item-cross-buy` |
| `/order-recommendation` | 発注推奨データ | `zozo-repeat-simulation` |
| `/dashboard` | 品番ダッシュボード | `zozo-product-dashboard` |
| `/md-plan` | MD計画分析 | `zozo-md-plan` |
| `/repeat-order` | リピート発注表作成（V2配分・分析レポート画像・非同期ジョブ・Google Spreadsheet生成） | `zozo-repeat-order-excel` |

## データ更新ワークフロー

各ページのデータはCDN上のJSONで管理。更新手順:

```
1. 各スキルの分析スクリプトでJSONを生成
2. manus-upload-file --webdev でCDNにアップロード
3. 対応するフックのDATA_URL定数を新しいCDN URLに更新
4. webdev_save_checkpoint でチェックポイント保存
```

| フック | データ内容 | 生成スキル |
|---|---|---|
| `useOrderRecommendation.ts` | リピートスコア・発注推奨数 | `zozo-repeat-simulation` |
| `useProductDashboard.ts` | 品番ダッシュボードデータ | `zozo-product-dashboard` |
| `useMdPlan.ts` | MD計画分析結果 | `zozo-md-plan` |

## 新ページ追加手順

1. `client/src/pages/NewPage.tsx` を作成
2. `client/src/App.tsx` に `<Route>` を追加
3. `client/src/components/Sidebar.tsx` にメニュー項目を追加
4. `client/src/components/NavBar.tsx` にアクティブ状態を追加
5. データフックが必要な場合は `client/src/hooks/` に作成
6. バックエンドAPIが必要な場合は `server/routers.ts` にtRPCプロシージャを追加、または `server/repeat-order/api.ts` のように専用モジュールを作成

## 共通コンポーネント

- `Header.tsx`: 上部ヘッダー（ロゴクリックでホームへ、検索バー、ダッシュボード品番入力）
- `NavBar.tsx`: ナビゲーションバー（商品管理、在庫管理、分析等のタブ）
- `Sidebar.tsx`: 左サイドバー（併売分析、売上分析、在庫分析、リピート分析、MD計画、ダッシュボード）

## デザインガイドライン

- テーマ: ライトデフォルト（`defaultTheme="light"`）
- フォント: Noto Sans JP + Inter
- カラー: 和風インダストリアル（スレートグレー基調、アクセントにインディゴ）
- レイアウト: サイドバー + メインコンテンツの2カラム構成

## 関連スキル一覧

| スキル | 用途 |
|---|---|
| `zozo-same-item-cross-buy` | 同一品番併売分析 |
| `zozo-repeat-simulation` | リピート発注シミュレーション |
| `zozo-repeat-order-excel` | リピート発注管理表V2生成（非同期ジョブ・V2配分・分析レポート画像・Google Spreadsheet） |
| `zozo-product-dashboard` | 品番ダッシュボードデータ生成 |
| `zozo-md-plan` | MD計画分析 |
| `zozo-affinity-analysis` | 買い回り相性分析 |
| `zozo-inventory-forecast` | 在庫消化予測 |
| `zozo-order-data` | 注文生データの場所・構造 |

## データソース

### S3 CDN上のデータ（リピート発注表用）

S3 URL一覧は `zozo-repeat-order-excel` スキルの `references/s3_urls.md` を参照。

### Google Drive上のデータ

- 買い回りデータ（月次Excel）: `買い回りデータ*.xlsx`
- ショップ指標データ（月次Excel）: `*集計*.xls`
- 分析スプレッドシート: ID `1ZmmlhitXPnCn8yh7YEZ5tYRjXgHIvhQhFvrid-9r9oo`
  - `分析_yyyymm`: 月次買い回り分析サマリー
  - `ランキング_yyyymm`: 親カテゴリ別売上ランキング
  - `データ貼付_yyyymm`: 買い回り生データ
  - `自社マスタ`: ブランド別月次売上実績

### ローカルデータ

- 注文データ: `/home/ubuntu/order_data/order_2025*.csv`, `/home/ubuntu/order_data/order_2026*.csv`
- 原価データ: `/home/ubuntu/sales_data/cost_data.csv`
- 商品別実績: `/home/ubuntu/dashboard_product_data.xlsx`

### 対象ブランド

MONO-MART, EMMA CLOTHES, CLEL, ADRER, WYM LIDNM
（ショップ名はMONO-MARTとEMMA CLOTHESの2ショップ）
