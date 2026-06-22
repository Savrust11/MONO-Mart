# MONO BACK OFFICE ページ構成

## ルーティング（App.tsx）

| パス | ページ | 概要 |
|---|---|---|
| `/` | Home.tsx | 同一品番併売分析（メイン画面） |
| `/order-recommendation` | OrderRecommendation.tsx | 発注推奨データ詳細 |
| `/dashboard` | Dashboard.tsx | 品番ダッシュボード |
| `/md-plan` | MdPlan.tsx | MD計画分析 |
| `/repeat-order` | RepeatOrder.tsx | リピート発注表作成（V2配分・分析レポート画像・非同期ジョブ・Google Spreadsheet生成） |

## 共通レイアウト

各ページは以下の共通コンポーネントを使用:

- `Header.tsx`: 上部ヘッダー（ロゴ、検索バー、ダッシュボード品番入力）
- `NavBar.tsx`: ナビゲーションバー（商品管理、在庫管理、分析等のタブ）
- `Sidebar.tsx`: 左サイドバー（併売分析、売上分析、在庫分析、リピート分析、MD計画、ダッシュボード）

## CDN URL管理

各ページのデータはCDN上のJSONファイルから取得:

| フック | CDN URL定数 | データ内容 |
|---|---|---|
| `useMdPlan.ts` | `DATA_URL` | MD計画分析結果 |
| `useProductDashboard.ts` | `DATA_URL` | 品番ダッシュボードデータ |
| `useOrderRecommendation.ts` | `SCORES_URL` | リピートスコア・発注推奨数 |

データ更新時は `manus-upload-file --webdev` でアップロードし、対応するフックのURL定数を更新する。

## ページ追加手順

1. `client/src/pages/NewPage.tsx` を作成
2. `client/src/App.tsx` に `<Route>` を追加
3. `client/src/components/Sidebar.tsx` にメニュー項目を追加
4. `client/src/components/NavBar.tsx` にアクティブ状態を追加（必要に応じて）
5. データフックが必要な場合は `client/src/hooks/` に作成
6. バックエンドAPIが必要な場合は `server/routers.ts` にtRPCプロシージャを追加、または `server/repeat-order/api.ts` のように専用モジュールを作成

## リピート発注表ページ（/repeat-order）

DBベースの非同期ジョブ管理で `POST /api/repeat-order` → jobId取得 → `GET /api/repeat-order/status/:jobId` ポーリング（3秒間隔）でGoogle Spreadsheetを生成。V2配分ロジック・分析レポート画像付き。詳細は `zozo-repeat-order-excel` スキルの `references/backoffice_integration.md` を参照。

### V2入力フォーム

| フィールド | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| 品番 | text | 必須 | ブランド品番（例: sc1402） |
| リピート発注総数 | number | 必須 | 合計着数（例: 3000） |
| 暫定納期 | date | 必須 | リピート納品日（YYYY-MM-DD） |
| 在庫カバー月数 | select | 必須 | 2〜5ヶ月（デフォルト3） |
| 対象カラー | select | 任意 | 既存色のみ / 全色 / 指定色のみ |
| 抑揚モード | select | 任意 | 通常 / 1番色重視 |
| 新色追加 | toggle+number | 任意 | カラー数・合計着数 |
| 要望・メモ | textarea | 任意 | 自由記述 |

### 処理フロー

1. フォーム入力 → POST /api/repeat-order → jobId取得
2. GET /api/repeat-order/status/:jobId を3秒間隔でポーリング
3. 進捗メッセージをリアルタイム表示
4. 完了後、「Google Spreadsheetを開く」ボタンを表示
5. エラー時はトースト通知

### 実装ファイル

| ファイル | 役割 |
|---|---|
| `server/repeat-order/api.ts` | APIエンドポイント（POST→ジョブ登録、GET status→ポーリング、GET check→品番確認） |
| `server/repeat-order/data-loader.ts` | データ取得（S3 CDN + Google Drive API、バケット分割JSON対応） |
| `server/repeat-order/sku-balance-v2.ts` | V2配分ロジック（10ステップ、全色イレギュラーフォールバック付き） |
| `server/repeat-order/sales-analyzer.ts` | 過去売れ方分析（参照期間決定・欠品期間判定） |
| `server/repeat-order/analysis-comment.ts` | 分析コメント・比較表生成 |
| `server/repeat-order/report-renderer.ts` | satori/sharpによるレポート画像生成（density 192dpi） |
| `server/repeat-order/sheets-writer.ts` | Google Sheets書き出し（テンプレートコピー→データ書込→画像挿入） |
| `server/repeat-order/config.ts` | URL定数・画像URL生成・ショップマップ |
| `server/repeat-order/excel-generator.ts` | ExcelGenerateInput型定義 |
| `client/src/pages/RepeatOrder.tsx` | フロントエンド（V2フォーム→ポーリング→Spreadsheet URL表示） |
