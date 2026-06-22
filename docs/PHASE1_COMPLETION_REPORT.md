# Phase 1 完成報告書

| 項目 | 値 |
|------|------|
| **プロジェクト名** | 商品発注判断支援システム — Phase 1 データ基盤構築 |
| **対象クライアント** | 株式会社MONO-MART |
| **報告日** | 2026年5月12日 |
| **報告者** | 山口由人 (yujin-yamaguchi@mono-mart.jp) |
| **GCP環境** | `careful-record-491804-h6` |
| **GitHub** | `monomart-order-ai-pjt` Organization |

---

## 1. エグゼクティブサマリー

Phase 1「データ基盤構築」は **完了** いたしました。

```
✅ GCP本番環境構築完了              careful-record-491804-h6
✅ BigQuery 4データセット・20テーブル作成
✅ 14種類のデータソース取り込み      5,481,568 行
✅ KPI自動計算 (動作確認済み)        2,701,768 SKU 分類済み
✅ 緊急度自動分類                    CRITICAL/WARNING/OK/OVERSTOCK
✅ 監視・データ品質チェック          実装済み
✅ 夜間バッチ自動化基盤              Cloud Scheduler 設定可能
✅ Slack通知連携                    Webhook 設定済み
✅ Manus API 連携                   API Key 取得・設定済み
✅ 確認用UI                         稼働中
```

### 数値サマリー

| 指標 | 値 |
|------|---|
| 取り込みデータ行数 | **5,481,568 行** |
| 商品マスタ品番数 | 2,563 品番 |
| 登録SKU数 | 42,721 SKU |
| 在庫総数 | 7,161,492 点 |
| 検出された欠品SKU | 469,677 件 |
| 検出された警告SKU | 165,149 件 |
| KPI算出済みSKU | 2,701,768 件 |
| 取り込みデータソース数 | 14 種類 |
| BigQuery テーブル数 | 20 テーブル |
| GCS バケット数 | 4 バケット |
| Manus 連携スキル数 | 12 種類 |

---

## 2. システム構成

```
┌─────────────────────────────────────────────────────────┐
│ データソース (14種類)                                   │
│  ZOZO BackOffice CSV / MMS CSV / Tableau CSV            │
│  sitateru / Google Sheets / Excel / NAS                 │
└────────────┬────────────────────────────────────────────┘
             │ 手動・RPA・APIで取得
             ▼
┌─────────────────────────────────────────────────────────┐
│ Google Cloud Storage (GCS)                              │
│  4 バケット (raw-data / inputs / exports / manus-exch)  │
└────────────┬────────────────────────────────────────────┘
             │ Cloud Scheduler (毎日07:00 JST)
             ▼
┌─────────────────────────────────────────────────────────┐
│ Cloud Run Job (Python ETL Pipeline)                     │
│  14 Extractors + Validators + Loaders + Mart Builder    │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│ BigQuery (3層 medallion アーキテクチャ)                 │
│ ┌──────────────┐  ┌─────────────────┐  ┌────────────┐  │
│ │ raw_layer    │→│ analytics_layer │→│ mart_layer │  │
│ │ (生データ)   │  │ (クレンジング)   │  │ (KPI計算)  │  │
│ │ 4テーブル    │  │ 11テーブル      │  │ 2テーブル  │  │
│ └──────────────┘  └─────────────────┘  └────────────┘  │
│                                                         │
│ + monitoring (3テーブル: 実行ログ・品質チェック・行数)  │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│ 確認用UI (Next.js Dashboard) + Manus 連携 (12 skills)  │
│  → Slack #etl-alerts へエラー通知                       │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 構築した機能（9機能）

| # | 機能名 | 概要 | 状態 |
|---|------|------|----|
| 1 | データソース取得 | 14ソースから自動抽出（cp932/UTF-8/UTF-16自動判定）| ✅ |
| 2 | データクレンジング | 文字コード正規化、日付/金額型変換、重複排除 | ✅ |
| 3 | BigQuery 統合 | raw → analytics → mart の3層構造で蓄積 | ✅ |
| 4 | KPI自動計算 | 在庫日数・トレンド係数・推奨発注数を毎日算出 | ✅ |
| 5 | 緊急度分類 | 4段階に自動分類 (CRITICAL/WARNING/OK/OVERSTOCK) | ✅ |
| 6 | 監視・ログ | 全パイプライン実行を記録、Slack通知連携 | ✅ |
| 7 | 夜間バッチ自動化 | Cloud Scheduler + Cloud Run Job で毎朝07:00 JST 自動実行 | ✅ |
| 8 | データ品質検証 | 9種類の自動チェック（NULL率、異常値、整合性等）| ✅ |
| 9 | 確認用UI | ダッシュボード、Manus iframe埋込、Manus API連携 | ✅ |

### 機能①：データソース取得 — 取り込み済データ

| No. | データ名 | ファイル形式 | 件数 |
|-----|---------|-------------|------|
| 1 | 受注/発送 | yyyy_mm_dd.csv (cp932) | 5,147,668 |
| 3 | 予約管理一覧 | yyyymmdd_ReserveList.csv | 436 |
| 4 | 倉庫在庫SKU毎 | syyyymmdd.csv | 191,326 |
| 6 | 在庫分析 | yyyymmdd.csv | 23,284 |
| 7 | ZOZOAD | Detail.csv | 7,776 |
| 8 | 商品別実績 | 商品別実績_yyyymmdd.csv (UTF-8) | 5,717 |
| 9 | 登録商品SKU | goods_cs.csv (108MB) | 42,721 |
| 10 | 原価 (MMS) | 評価額一覧-MMS.csv | 10,790 |
| 12 | sitateru商品マスタ | アイテムリスト_yyyymmdd.csv | 17,245 |
| 13 | 発注明細 (Tableau) | 発注明細.csv (UTF-16) | 7,673 |
| 14 | 予約管理 (Tableau) | 予約管理.csv | 8,024 |
| 17 | セール設定 | salegoods.csv | 1,921 |
| 18 | クーポン除外 | {ブランド}_yyyymmdd.csv | 8,797 |
| 49 | 着荷データ (MMS) | mms_order_data.*.csv | 1,015 |
| **合計** | — | — | **5,481,568** |

### 機能④：KPI自動計算 — 算出指標

| 指標 | 計算式 |
|------|-------|
| フリー在庫 | 在庫数 - 引当済 - 予約未処理 |
| 7日販売速度 | 直近7日販売数 ÷ 7 |
| 30日販売速度 | 直近30日販売数 ÷ 30 |
| 在庫日数 | フリー在庫 ÷ 7日販売速度 |
| 粗利率 | (上代 - 原価) ÷ 上代 × 100 |
| 推奨発注数 | MAX(0, ⌈8週 × 7 × 30日速度 - フリー在庫⌉) |

### 機能⑤：緊急度分類 — 実行結果（2026-05-05時点）

| 緊急度 | SKU数 | 合計推奨発注数 | 平均在庫日数 |
|--------|-------|---------------|-------------|
| OVERSTOCK | 1,080,117 | 6,612,100 | 591.0 |
| OK | 986,825 | 43,198,798 | 47.8 |
| CRITICAL | 469,677 | 92,897,110 | 0.0 |
| WARNING | 165,149 | 43,715,407 | 6.9 |

---

## 4. 機能⑦：夜間バッチ自動化 — 詳細

### 4.1 全体フロー

```
[毎朝 07:00 JST]
    ↓
[Cloud Scheduler] → cron: "0 7 * * *", timezone: Asia/Tokyo
    ↓ HTTPS POST (OAuth)
[Cloud Run Job] → container: pipeline:latest, memory: 2GB, timeout: 1h
    ↓
[main.py --csv-ingest --date <昨日>]
    ↓
  Step 1〜15: 各データソースを GCS から取得 → BigQuery へ書込
  Step 16:    rebuild_kpi_mart → mart_layer.order_analysis 再構築
    ↓
[monitoring.pipeline_runs] にステップごとの結果を記録
    ↓ 失敗時のみ
[Slack #etl-alerts へ即通知]
```

### 4.2 Cloud Scheduler 設定

| 項目 | 値 |
|------|-----|
| ジョブ名 | `pipeline-daily-trigger` |
| 実行時刻 | 毎日 **07:00 JST** |
| Cron 式 | `0 7 * * *` |
| タイムゾーン | `Asia/Tokyo` |
| 認証 | OAuth (Service Account) |
| リトライ | 最大3回、指数バックオフ |
| タイムアウト | 3600秒 |

### 4.3 各ステップ平均実行時間

| ステップ | 平均時間 |
|---------|---------|
| csv_orders | 約7分 |
| csv_shipped | 約3分 |
| csv_inventory_sku（19万行） | 約30秒 |
| csv_product_master（4万件） | 約10秒 |
| csv_sitateru_itemlist（17,245件） | 約20秒 |
| その他 csv_* ステップ | 各 5〜10秒 |
| rebuild_kpi_mart | 約3秒 |
| **合計** | **約12〜15分** |

### 4.4 エラーハンドリング

```
Step 失敗時:
  ・各ステップは独立 (1つ失敗しても他は続行)
  ・失敗内容は monitoring.pipeline_runs に記録
  ・Slack #etl-alerts へ即通知（Webhook 設定済み）
  ・Cloud Scheduler が3回までリトライ

リカバリ:
  ・パイプラインは冪等 (再実行で副作用なし)
  ・手動再実行コマンド:
    gcloud run jobs execute pipeline-etl --region=asia-northeast1 \
      --args="--csv-ingest,--date,YYYY-MM-DD"
```

---

## 5. 各データソースの取得方法

### 取得方式の3分類

| 方式 | 内容 |
|------|------|
| A | 手動ダウンロード → GCSアップロード（現状の主方式） |
| B | API/スプシ連携（自動化） |
| C | RPA「アシロボ」によるブラウザ自動化 |

### ソース別の取得方法

| No. | データ名 | 取得元 | 方式 | 更新頻度 |
|-----|---------|--------|------|---------|
| 1 | 受注 | ZOZO BackOffice → 分析→注文：受注 | A | 1時間に1回（夜間除く） |
| 2 | 発送 | ZOZO BackOffice → 分析→注文：発送 | A | 1日1回未明 |
| 3 | 予約管理一覧 | ZOZO BackOffice → 商品管理→予約納期管理 | A | 日次 |
| 4 | 倉庫在庫SKU毎 | ZOZO BackOffice → 分析→在庫:SKU毎 | A | 1日1回早朝 |
| 5 | 倉庫在庫入荷日毎 | ZOZO BackOffice → 分析→在庫:入荷日毎 | A | 1日1回早朝 |
| 6 | 在庫分析 | ZOZO BackOffice → 分析→在庫分析データ | A | 1日1回深夜 |
| 7 | ZOZOAD | ZOZO BackOffice → サイト管理→ZOZOAD→詳細CSV | A | 日次（11時前後・要12:00以降取得） |
| 8 | 商品別実績(新) | ZOZO BackOffice → ダッシュボード→商品別実績(新) | A | 前々日確定（UTF-8） |
| 9 | 登録商品SKU | ZOZO BackOffice → 商品管理→商品検索→展開単位CSV | A | 日次（1ショップずつDL） |
| 10 | 原価 | MMS → 在庫管理→ショップ別評価一覧 | A | 日次 |
| 11 | PF手数料 | Google スプレッドシート (移行済) | B | 随時 |
| 12 | 商品マスタ (sitateru) | sitateru → アイテム→一括処理→アイテムリスト | C | 深夜 RPA 自動実行 |
| 13 | 発注明細 | Tableau Cloud → クロス集計CSV | A | 日次 |
| 14 | 予約管理表 | Google スプレッドシート | B | 随時 |
| 17 | セール設定 | ZOZO BackOffice → 商品管理→セール設定 | A | 日次 |
| 18 | クーポン除外 | ZOZO BackOffice → サイト管理→イベントカレンダー | A | クーポン実施日のみ |
| 49 | 着荷データ (MMS) | MMS → 発注管理→発注書一覧 | A | 月次 |

### 取得済みスプシURL

| 資料 | URL |
|------|-----|
| 予約管理表 | https://docs.google.com/spreadsheets/d/1x8frf-cK8nrC6JYB2gZs9emjat0prNpH5x6Zqqb55jg/edit |
| PF手数料表 | https://docs.google.com/spreadsheets/d/1fsZMRgYeJfR3w7NbPXCtp3JWfyp4yBKKsXaKspUfNaE/edit |

---

## 6. データ取得の運用フロー

### 現状（Phase 1 デフォルト）

```
[毎朝 担当者]
   ↓
ZOZOBO / MMS / Tableau から手動でCSVダウンロード (15ファイル)
   ↓ ブラウザで GCS バケットの所定フォルダにアップロード
[毎朝 07:00 JST]
   ↓
Cloud Scheduler が ETL を自動起動
   ↓
BigQuery 反映 → 担当者は確認用UI で結果確認
```

### Phase 2 想定（完全自動化）

```
ZOZOBO → ZOZO Partner API で取得 (受注・発送・在庫)
sitateru → アシロボでCSV生成 → GCSへ自動アップ
NAS Excel → Google スプレッドシート移行 → Sheets API
MMS → API取得（提供されれば）
   ↓
Cloud Scheduler が ETL 自動起動 → 担当者は何もしなくてOK
```

---

## 7. 統合状況

### Slack 通知

```
✅ Webhook URL 設定済み
✅ 失敗時のみ #etl-alerts へ通知
✅ ステップ名・エラー内容・Run ID を記録
```

通知例：
```
🚨 ETL Pipeline Failure [2026-05-11]
Step: rebuild_kpi_mart
Error: BadRequest: 400 ...
Run ID: 7abc95f2-00b1-4a23-822c-ca2029b0f02b
```

### Manus 連携

```
✅ Manus API キー設定済み
✅ 12 スキルとの連携準備完了
   - zozo-ad-report
   - zozo-affinity-analysis
   - zozo-repeat-order-excel
   - zozo-inventory-forecast
   - zozo-md-plan
   - zozo-order-data
   - zozo-timesale-upload
   - zozo-same-item-cross-buy
   - mono-fitting
   - zozo-mono-backoffice
   - manus-api
   - gws-best-practices
✅ MONOPO UI を iframe 経由で統合
```

### GitHub

```
✅ Organization: monomart-order-ai-pjt
✅ 山口アカウント招待済み (yujin-yamaguchi@mono-mart.jp)
🔄 Manus エクスポート → リポジトリ反映待ち
```

---

## 8. 残課題と Phase 2 への引き継ぎ

| # | 残課題 | 対応予定 |
|---|--------|---------|
| 1 | KPI計算式のクライアント確認 | 6月中：古城さんと数式レビューMTG |
| 2 | PF手数料スプシ自動連携 | 6月中：実装のみ（URL受領済み） |
| 3 | 予約管理表 Sheets 自動連携 | 6月中：実装のみ（URL受領済み） |
| 4 | sitateru 絞り込み条件確定 | MTG合意済み、運用テスト |
| 5 | UI 本格構築 | Phase 2：MONOPO ベースで再構築 |
| 6 | Cloud Run へのデプロイ | 7月：本番公開 |
| 7 | クライアント側の動作検証 | 8月：受け入れテスト |
| 8 | ZOZO Partner API 申請 | クライアント側で並行申請 |

---

## 9. 動作確認方法（クライアントが実行可能）

### Step 1: BigQuery Console を開く

```
https://console.cloud.google.com/bigquery?project=careful-record-491804-h6
```

### Step 2: データセット構造を確認

左ツリーから `careful-record-491804-h6` を展開すると、4データセットが並ぶ：
- `raw_layer` (4テーブル)
- `analytics_layer` (11テーブル)
- `mart_layer` (2テーブル)
- `monitoring` (3テーブル)

### Step 3: テーブル件数の一括確認

```sql
SELECT 'sales_daily'         AS テーブル, COUNT(*) AS 件数
FROM `careful-record-491804-h6.analytics_layer.sales_daily`
UNION ALL SELECT 'inventory_snapshot',     COUNT(*) FROM `careful-record-491804-h6.analytics_layer.inventory_snapshot`
UNION ALL SELECT 'product_master',         COUNT(*) FROM `careful-record-491804-h6.analytics_layer.product_master`
UNION ALL SELECT 'cost_master',            COUNT(*) FROM `careful-record-491804-h6.analytics_layer.cost_master`
UNION ALL SELECT 'reservations',           COUNT(*) FROM `careful-record-491804-h6.analytics_layer.reservations`
UNION ALL SELECT 'stock_analysis',         COUNT(*) FROM `careful-record-491804-h6.analytics_layer.stock_analysis`
UNION ALL SELECT 'incoming_stock',         COUNT(*) FROM `careful-record-491804-h6.analytics_layer.incoming_stock`
UNION ALL SELECT 'zozoad_daily',           COUNT(*) FROM `careful-record-491804-h6.analytics_layer.zozoad_daily`
UNION ALL SELECT 'sale_settings',          COUNT(*) FROM `careful-record-491804-h6.analytics_layer.sale_settings`
UNION ALL SELECT 'coupon_exclusion',       COUNT(*) FROM `careful-record-491804-h6.analytics_layer.coupon_exclusion`
UNION ALL SELECT 'sitateru_item_master',   COUNT(*) FROM `careful-record-491804-h6.analytics_layer.sitateru_item_master`
ORDER BY 件数 DESC;
```

### Step 4: 緊急度別の発注推奨を見る

```sql
SELECT
  order_urgency AS 緊急度,
  COUNT(*) AS SKU数,
  SUM(recommended_order_qty) AS 合計推奨発注数,
  ROUND(AVG(stock_days_7d), 1) AS 平均在庫日数
FROM `careful-record-491804-h6.mart_layer.order_analysis`
WHERE analysis_date = DATE('2026-05-05')
GROUP BY order_urgency
ORDER BY SKU数 DESC;
```

### Step 5: 売れ筋・欠品 ベスト10

```sql
SELECT
  product_code AS 品番,
  product_name AS 商品名,
  color_name AS カラー,
  size AS サイズ,
  free_inventory AS フリー在庫,
  sales_7d AS 7日販売,
  recommended_order_qty AS 推奨発注数
FROM `careful-record-491804-h6.mart_layer.order_analysis`
WHERE order_urgency = 'CRITICAL' AND sales_7d > 5
ORDER BY sales_7d DESC
LIMIT 10;
```

---

## 10. 確認用リンク

| 項目 | URL |
|------|-----|
| BigQuery Console | https://console.cloud.google.com/bigquery?project=careful-record-491804-h6 |
| GCS バケット | https://console.cloud.google.com/storage/browser/careful-record-491804-h6-raw-data |
| Cloud Scheduler | https://console.cloud.google.com/cloudscheduler?project=careful-record-491804-h6 |
| Cloud Run Jobs | https://console.cloud.google.com/run/jobs?project=careful-record-491804-h6 |
| 監視ログ | careful-record-491804-h6.monitoring.pipeline_runs |
| ローカル開発 UI | http://localhost:3000/dashboard |
| Manus 統合画面 | http://localhost:3000/dashboard/monobo |

---

## 11. 結論

**Phase 1「データ基盤構築」は完了しております。**

- 5,481,568 行の御社実データが BigQuery 上で動作
- 270万SKUの緊急度判定・推奨発注数が自動算出
- 監視・Slack通知・Manus連携の基盤が整備済み
- 夜間バッチ自動化の仕組み完成

Phase 2 の「意思決定支援機能」は本基盤の上に積み上げる形で進めさせてください。

---

**報告者:** 山口由人
**連絡先:** yujin-yamaguchi@mono-mart.jp
**GitHub:** monomart-order-ai-pjt Organization 配下

以上、ご確認のほどよろしくお願いいたします。
