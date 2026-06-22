---
name: zozo-repeat-order-excel
description: ZOZOのリピート発注管理表をGoogle Spreadsheetとして自動生成するスキル。品番・発注総数・要望を入力として、展開SKU・在庫分析・注文生データ・入荷予定・予約一覧・ZOZOカラーマスタから必要データを収集し、10日刻み売上実績・SKUバランス配分・商品画像（IMAGE関数）を含むGoogle Spreadsheetを出力する。「リピート発注表を作って」「品番○○のリピート発注」「発注管理表の作成」等の依頼時に使用する。MONO BACK OFFICEへのページ追加時にも参照する。
---

# ZOZOリピート発注管理表自動生成

品番・発注総数・暫定納期・在庫カバー月数から、V2配分ロジックでリピート発注管理表をGoogle Spreadsheetとして自動生成する。

## ワークフロー

1. **入力確認**: 品番、発注総数、暫定納期、在庫カバー月数、対象カラー、抑揚モード、新色、要望を確認
2. **ショップ判別**: 展開SKU JSONから品番→ショップを自動判別
3. **データ収集**: S3 CDN + Google Drive APIから該当品番のデータを抽出
4. **V2配分算出**: 10ステップのV2ロジックで発注総数を各SKUに配分
5. **分析レポート生成**: カラー別分析コメント・比較表をsatori→sharp→PNG画像化
6. **Spreadsheet生成**: テンプレートSpreadsheetをコピーし各シートにデータを書き込み
7. **画像挿入**: レポート画像（IMAGE関数）+ 商品画像（IMAGE関数、1列間隔配置）
8. **納品**: 生成されたSpreadsheetのURLをユーザーに返却

## 入力仕様

| 項目 | 必須 | 説明 |
|------|------|------|
| 品番 | 必須 | ブランド品番（例: sc841, sh1599） |
| リピート発注総数 | 必須 | 合計着数（例: 4000） |
| 暫定納期 | 必須 | リピートが納品される日付（YYYY-MM-DD） |
| 在庫カバー月数 | 必須 | 暫定納期からの在庫期間（2〜5ヶ月、デフォルト3ヶ月） |
| 対象カラー | 任意 | 「既存色のみ」（デフォルト）/「全色」/「指定色のみ」 |
| 抑揚モード | 任意 | 「通常」（デフォルト）/「1番色重視」 |
| 新色追加 | 任意 | カラー数・合計着数を指定（発注総数から差し引き） |
| 要望・メモ | 任意 | 自由記述（例:「ブラックは少なめに」） |

## データソース

全データソースの詳細（フォルダID、列定義、エンコーディング、読み込み注意点）は `references/data_sources.md` を参照。
S3 CDN URL一覧は `references/s3_urls.md` を参照。

| データ | 用途 | 取得元 |
|--------|------|--------|
| 展開SKU JSON | SKU情報・ショップ判別 | S3 CDN（バケット分割JSON） |
| 在庫分析CSV | 現在庫・販売数・お気に入り | S3 CDN or ショップ別CSV |
| 注文生データ | 売上実績・10日刻み集計 | Googleドライブ ショップ別月次CSV |
| 入荷予定 | 納品予定数・予定日 | Googleスプレッドシート |
| 予約管理一覧CSV | 予約未処理数 | S3 CDN or ショップ別CSV |
| ZOZOカラーマスタ | 画像URL生成用カラーコード | S3 CDN（バケット分割JSON） |

### データアクセス方式

| 環境 | 方式 |
|------|------|
| サンドボックス（Manusタスク） | ローカルファイル or `gws` CLI |
| デプロイ環境（manus.space） | S3 CDN URL + サービスアカウントAPI |

**デプロイ環境ではローカルファイルパス（`/home/ubuntu/...`）と`gws` CLIは使用不可。**

### メモリ最適化

goods_all.json（20MB）とbarcode_master.json（19MB）はバケット分割済み（先頭2文字ごと）。品番の先頭2文字でバケットを特定し、必要なバケットのみ取得する。

## Excelフォーマット構造

ベースファイル: テンプレートSpreadsheet ID `1lfeNy7NzXhICKwPohjl9B0UnDHyvHfCrwoJkvx6BoxI`

全シートの列マッピング詳細は `references/excel_format.md` を参照。

### シート一覧

| シート | 内容 |
|--------|------|
| 発注表 | メイン。SKUデータ・発注数・10日刻み実績・レポート画像・商品画像 |
| 売上実績 | 注文生データ（品番分のみ、19列+計算列9列） |
| 在庫分析貼り付け | 在庫分析CSV（品番分のみ） |
| 予約管理表 | 入荷予定データ |
| 予約一覧 | 予約管理一覧データ |

## SKUバランスV2配分ロジック

V2では以下の10ステップで配分を計算する:

| Step | 内容 |
|------|------|
| 1 | 販売期間の確定（暫定納期〜暫定納期+Nヶ月） |
| 2 | 参照期間の決定（季節性判定→最売れ3ヶ月 or 過去半年） |
| 3 | 欠品期間の特定と除外（10日刻みで日販0期間をマーク） |
| 4 | 暫定納期時点の予測フリー在庫 |
| 5 | イレギュラーSKU判定（予測フリー在庫≧販売予測→除外） |
| 6 | 初期配分（在庫フル期間の販売構成比で配分） |
| 7 | カラーミニマムチェック（100着未満→除外→再配分→連鎖チェック） |
| 8 | 抑揚モード適用（1番色重視: +10/+12/+15%自動調整） |
| 9 | 10着刻み端数処理（端数<30→1番SKU、30-49→1番+2番、50以上→1-3番） |
| 10 | 新色処理（新色合計数差し引き→均等分配→1番サイズに合計記載） |

### 全色イレギュラー時のフォールバック

全SKUがイレギュラー判定（予測フリー在庫≧販売予測）された場合でも、発注総数が指定されていれば全SKUを配分対象に含める。販売構成比ベースで配分し、イレギュラーフラグは維持する。

### 分析レポート

カラー別の分析コメント（推奨◎/注意△/除外✕）、フリー在庫割合 vs カテゴリ傾向の比較表、参照期間・欠品・抑揚・新色の注記を含むPNG画像をsatori→sharpで生成し、S3にアップロード後、SpreadsheetにIMAGE関数で埋め込む。

- 画像生成: satori（SVG生成、幅1000px）→ sharp（PNG変換、density 192dpi、タイムアウト15秒）
- フォント: Noto Sans JP Regular（ローカル優先、S3フォールバック）

## 商品画像の配置

Google Sheetsでは`=IMAGE()`関数で画像を表示する。

1. SKUリストからユニークカラーを抽出
2. ZOZOカラーマスタからカラー名→カラーコードを取得
3. 画像URL生成: `https://o.imgz.jp/{商品コード末尾3桁}/{商品コード}/{商品コード}b_{カラーコード}_d.jpg`
4. IMAGE関数: `=IMAGE("url", 4, 150, 120)` … モード4（カスタムサイズ）、高さ150px、幅120px
5. 配置位置: レポート画像の下、各カラー**1列間隔**で横並び（B,C,D,E,F,...列）
6. カラー名行を画像行の1行上に記入
7. 画像列の幅を**135px**に自動調整（IMAGE関数の幅120pxが収まるように）
8. 画像行の高さを**165px**に調整

**注意**: 初回表示時にGoogle Sheetsの「Allow access」ボタンのクリックが必要（IMAGE関数が外部URLからデータを取得するため）

## Spreadsheet生成の処理フロー

実装: `server/repeat-order/sheets-writer.ts`（MONO BACK OFFICEバックエンド）

処理フロー:
1. テンプレートSpreadsheetをGoogle Drive APIでコピー
2. 既存データをクリア（ヘッダー・数式は保持）
3. 発注表のデータ行数をSKU数に合わせて調整（余分な行を削除）
4. 各シートにデータを書き込み（Sheets API batchUpdate/values.update）
5. レポート画像をIMAGE関数で埋め込み（B-Z列結合セル）
6. 商品画像をIMAGE関数で挿入（1列間隔、列幅135px・行高165px自動調整）
7. Spreadsheet URLをレスポンスとして返却

## 非同期ジョブ管理

デプロイ環境のLBタイムアウト（60秒）を回避するため、DBベースの非同期ジョブ管理を採用:

1. `POST /api/repeat-order` → DBにジョブ登録し即座にjobIdを返す
2. バックグラウンドでprocessJob関数を実行（30〜150秒）
3. フロントエンドは `GET /api/repeat-order/status/:jobId` を3秒間隔でポーリング
4. ジョブ完了時にSpreadsheet URLを取得

ジョブ状態はDBテーブル `repeat_order_jobs` に保存（status: pending/processing/completed/failed、progress: 進捗メッセージ）。

## 注意事項

- 注文生データCSVはヘッダー28列に対しデータ行が末尾カンマで29列になる場合あり→末尾切り捨て
- 在庫分析CSVの列名に先頭スペースが含まれる場合あり→`.strip()`で対応
- 展開SKU・カラーマスタはバケット分割JSON（先頭2文字）でオンデマンド読み込み
- 10日刻み売上実績はSUMIFS数式ではなく計算済み値を直接書き込み
- テンプレートSpreadsheetにはsc841の埋め込み画像を含めないこと（コピー時に引き継がれるため）
- IMAGE関数の初回表示時に「Allow access」クリックが必要
- 画像列の幅が120px未満だとIMAGE関数の画像が表示されない→列幅135px以上を確保
- エンコーディング: 展開SKU・在庫分析・予約管理一覧はcp932、注文生データはUTF-8
- satori/sharpの画像生成: density 192dpi、sharpタイムアウト15秒に設定
- 全色イレギュラー時はフォールバック配分で全SKUを配分対象に含める

## MONO BACK OFFICEへの組み込み

MONO BACK OFFICEに「リピート発注表作成」ページが実装済み。詳細は `references/backoffice_integration.md` を参照。

### 実装済みファイル

| ファイル | 役割 |
|---|---|
| `server/repeat-order/api.ts` | APIエンドポイント（POST /api/repeat-order, GET /api/repeat-order/status/:jobId, GET /api/repeat-order/check） |
| `server/repeat-order/data-loader.ts` | データ取得（S3 CDN + Google Drive API、バケット分割JSON対応） |
| `server/repeat-order/sku-balance-v2.ts` | V2配分ロジック（10ステップ、全色イレギュラーフォールバック付き） |
| `server/repeat-order/sales-analyzer.ts` | 過去売れ方分析（参照期間決定・欠品期間判定） |
| `server/repeat-order/analysis-comment.ts` | 分析コメント・比較表生成 |
| `server/repeat-order/report-renderer.ts` | satori/sharpによるレポート画像生成（density 192dpi） |
| `server/repeat-order/sheets-writer.ts` | Google Sheets書き出し（テンプレートコピー→データ書込→画像挿入） |
| `server/repeat-order/config.ts` | URL定数・画像URL生成・ショップマップ |
| `server/repeat-order/excel-generator.ts` | ExcelGenerateInput型定義 |
| `client/src/pages/RepeatOrder.tsx` | フロントエンド（V2入力フォーム→ポーリング→Spreadsheet URL表示） |

### テスト実績

| 品番 | 条件 | 環境 | 結果 |
|------|------|------|------|
| sc1402 | 3000着、新色2色×200着、納期2026-06-10 | デプロイ | 成功 |
| sh1599 | 4000着、新色1色×200着、納期2026-06-10 | デプロイ | 成功 |
| sh1653 | 3000着、新色1色×200着 | デプロイ | 成功 |

Vitestユニットテスト: 全28テストパス（sku-balance-v2.test.ts: 8テスト、api.test.ts: 6テスト、他）
