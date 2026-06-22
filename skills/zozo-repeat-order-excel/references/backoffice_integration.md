# MONO BACK OFFICE リピート発注表作成ページ 組み込みガイド

## 概要

MONO BACK OFFICEの「リピート発注表作成」ページ（`/repeat-order`）。品番・着数・暫定納期・在庫カバー月数・抑揚モード・新色を入力してGoogle Spreadsheetを自動生成し、URLを表示する。V2配分ロジック・分析レポート画像・非同期ジョブ管理を搭載。

## 前提条件

- MONO BACK OFFICEが`web-db-user`にアップグレード済みであること
- データファイルがS3 CDNにアップロード済みであること（`references/s3_urls.md` 参照）
- Google Sheets API用のサービスアカウントが設定済みであること（`GOOGLE_SERVICE_ACCOUNT_KEY`）
- DBテーブル `repeat_order_jobs` が作成済みであること（`drizzle/schema.ts`）

## アーキテクチャ

```
[フロントエンド]                    [バックエンド]
V2入力フォーム  →  POST /api/repeat-order  →  DBにジョブ登録、即座にjobId返却
                                                    ↓ バックグラウンド処理
ポーリング(3秒)  ←  GET /api/repeat-order/status/:jobId  ←  S3 CDN + Google Drive APIからデータ取得
                                                    ↓
Spreadsheet URL表示  ←  status=completed  ←  V2配分 → レポート画像生成 → Google Sheets書き出し
```

### データアクセス方式

| 環境 | データ取得方法 | Google Sheets |
|------|-------------|---------------|
| サンドボックス | ローカルファイル or `gws` CLI | `gws` CLI |
| デプロイ（manus.space） | S3 CDN URL経由のHTTP GET | サービスアカウントAPI |

**重要**: デプロイ環境ではローカルファイルパス（`/home/ubuntu/...`）は使用不可。`gws` CLIも使用不可。

## フロントエンド仕様

### ページ: `/repeat-order`

**V2入力フォーム:**

| フィールド | 型 | 必須 | デフォルト | 説明 |
|-----------|-----|------|-----------|------|
| 品番 | text | 必須 | - | ブランド品番（例: sc1402） |
| リピート発注総数 | number | 必須 | - | 合計着数（例: 3000） |
| 暫定納期 | date | 必須 | - | リピート納品日（YYYY-MM-DD） |
| 在庫カバー月数 | select | 必須 | 3 | 2〜5ヶ月 |
| 対象カラー | select | 任意 | 既存色のみ | 既存色のみ / 全色 / 指定色のみ |
| 指定カラー | multi-select | 条件付き | - | 対象カラー=指定色のみ の場合に表示 |
| 抑揚モード | select | 任意 | 通常 | 通常 / 1番色重視 |
| 新色追加 | toggle | 任意 | OFF | ONで新色カラー数・合計着数入力欄を表示 |
| 新色カラー数 | number | 条件付き | - | 新色追加=ON の場合 |
| 新色合計着数 | number | 条件付き | - | 新色追加=ON の場合 |
| 要望・メモ | textarea | 任意 | - | 自由記述 |

**UI要件:**
- 作成ボタン押下後、ジョブIDを取得しポーリング開始（3秒間隔）
- 進捗メッセージをリアルタイム表示（「SKU情報を取得中...」→「在庫データを取得中...」→「配分計算中...」→「Spreadsheet生成中...」）
- 完了後、「Google Spreadsheetを開く」ボタンを表示
- エラー時はトースト通知で原因を表示
- 品番が見つからない場合は「該当品番のデータが見つかりません」と表示

### 品番チェックAPI

`GET /api/repeat-order/check?brandCode={品番}` で品番の存在確認とSKU情報を取得。入力フォームで品番入力後に呼び出し、ショップ名・カラー・サイズの一覧を表示する。

## バックエンドAPI仕様

### POST `/api/repeat-order`

ジョブをDBに登録し、即座にjobIdを返す（LBタイムアウト60秒回避）。

**リクエスト:**
```json
{
  "brandCode": "sc1402",
  "totalQty": 3000,
  "targetColors": "existing",
  "deliveryDate": "2026-06-10",
  "stockCoverMonths": 3,
  "emphasisMode": "normal",
  "newColors": {
    "enabled": true,
    "colorCount": 2,
    "totalQty": 400
  },
  "memo": "ブラックは少なめに"
}
```

**レスポンス（即座）:**
```json
{
  "success": true,
  "jobId": "ro_1718000000000_abc123"
}
```

### GET `/api/repeat-order/status/:jobId`

ジョブ状態をDBから取得。フロントエンドが3秒間隔でポーリング。

**レスポンス（処理中）:**
```json
{
  "status": "processing",
  "progress": "配分計算中..."
}
```

**レスポンス（完了）:**
```json
{
  "status": "completed",
  "resultData": {
    "spreadsheetId": "1abc...",
    "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/1abc.../edit",
    "title": "発注管理表_sc1402_リピート",
    "summary": {
      "brandCode": "sc1402",
      "shop": "MONO-MART",
      "totalQty": 3000,
      "skuCount": 32,
      "allocatedTotal": 2600,
      "newColorTotal": 400
    }
  }
}
```

**レスポンス（失敗）:**
```json
{
  "status": "failed",
  "errorMessage": "品番 xxx のデータが見つかりません"
}
```

### バックグラウンド処理フロー

1. **ショップ判別**: 展開SKU JSON（S3バケット分割）から品番→ショップを特定
2. **在庫分析CSV取得**: S3 CDNから該当ショップの在庫分析CSVを取得
3. **注文生データ取得**: Google Drive API（サービスアカウント）で該当ショップの月次CSVから品番をgrep抽出
4. **入荷予定取得**: Google Sheets API（サービスアカウント）で該当ブランドシートを取得
5. **予約管理一覧取得**: S3 CDNから該当ショップの予約管理一覧CSVを取得
6. **V2配分算出**: 10ステップのV2ロジックで配分計算（全色イレギュラーフォールバック含む）
7. **分析レポート生成**: カラー別コメント・比較表をsatori→sharp→PNG→S3アップロード
8. **Spreadsheet生成**: テンプレートSpreadsheetをコピーし各シートにデータを書き込み
9. **画像挿入**: レポート画像（IMAGE関数、B-Z結合セル）+ 商品画像（IMAGE関数、1列間隔）
10. **ジョブ完了**: DBにresultData（SpreadsheetURL等）を保存

### Google Sheets API（サービスアカウント方式）

デプロイ環境でGoogle Sheets/Driveにアクセスするための設定:

1. Google Cloud Consoleでサービスアカウントを作成
2. Sheets API と Drive API を有効化
3. サービスアカウントのJSONキーをダウンロード
4. secretsに `GOOGLE_SERVICE_ACCOUNT_KEY` として設定
5. テンプレートSpreadsheetと出力先フォルダをサービスアカウントのメールアドレスに共有

### テンプレートSpreadsheet

| 項目 | 値 |
|------|-----|
| テンプレートID | `1lfeNy7NzXhICKwPohjl9B0UnDHyvHfCrwoJkvx6BoxI` |
| 出力先フォルダID | `1s638qaQavEC4YExhnOeTYRToej8yVdcZ` |

**注意**: テンプレートにはsc841の埋め込み画像を含めないこと（コピー時に引き継がれるため）。

## 実装ファイル一覧

| ファイル | 役割 |
|---|---|
| `server/repeat-order/api.ts` | APIエンドポイント（POST→ジョブ登録、GET status→ポーリング、GET check→品番確認） |
| `server/repeat-order/data-loader.ts` | データ取得（S3 CDN + Google Drive API、バケット分割JSON対応） |
| `server/repeat-order/sku-balance-v2.ts` | V2配分ロジック（10ステップ、全色イレギュラーフォールバック付き） |
| `server/repeat-order/sales-analyzer.ts` | 過去売れ方分析（参照期間決定・欠品期間判定） |
| `server/repeat-order/analysis-comment.ts` | 分析コメント・比較表生成 |
| `server/repeat-order/report-renderer.ts` | satori/sharpによるレポート画像生成（density 192dpi、タイムアウト15秒） |
| `server/repeat-order/sheets-writer.ts` | Google Sheets書き出し（メイン処理、レポート画像+商品画像挿入） |
| `server/repeat-order/config.ts` | URL定数・画像URL生成・ショップマップ |
| `server/repeat-order/excel-generator.ts` | ExcelGenerateInput型定義 |
| `client/src/pages/RepeatOrder.tsx` | フロントエンドページ（V2フォーム、ポーリング、結果表示） |

## テスト方法

1. sc1402（MONO-MART）で3000着、新色2色×200着、暫定納期2026-06-10でテスト
2. 生成されたSpreadsheetの各シートにデータが正しく入っているか確認
3. 10日刻み実績が正しい列に入っているか確認
4. レポート画像が鮮明に表示されるか確認
5. 商品画像が全カラー分表示されるか確認（Allow accessクリック後）
6. 別ショップ（EMMA CLOTHES等）の品番でもテスト
7. カラー数が多い品番（8色以上）で画像が全て表示されるか確認
8. 全色イレギュラー品番で配分がゼロにならないことを確認
