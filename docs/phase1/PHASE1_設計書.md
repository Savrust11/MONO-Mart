# MONO BACK OFFICE システム — Phase 1 設計書

**作成日**: 2026-05-26
**作成者**: 山口
**対象クライアント**: 株式会社MONO-MART
**Phase 1スコープ**: 発注管理表に必要最低限のデータの自動取得 + データ基盤構築

---

## 0. 設計書 / 完了書の定義

本ドキュメントは Phase 1 の **設計書（What/How/Where）** と **完了書（達成項目チェック）** を兼ねた成果物です。以下7セクションで構成されます:

1. システム全体構成
2. データソース一覧と取得方式
3. データフロー（GCS → BigQuery 3層構造）
4. BigQueryテーブル仕様
5. 業務ロジック（フリー在庫・販売速度・推奨発注数）
6. 運用情報（実行スケジュール・エラー対応）
7. Phase 1 完了確認チェックリスト + Phase 2 引き継ぎ事項

---

## 1. システム全体構成

```
┌─────────────────────────────────────────────────────────────────────┐
│  外部システム (データソース)                                        │
├─────────────────────────────────────────────────────────────────────┤
│  ZOZO BO (Back Office)    MMS              Google Sheets/Drive    │
│  - 9種類のCSV               - 評価額一覧     - PF手数料表           │
│  - 自動ログイン             - 19ショップ     - 予約管理表(発注明細) │
│  - Headless Chromium                        - ブランド別買い回り    │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Scraping Layer (Windows Server, Python 3.13 + Playwright)         │
├─────────────────────────────────────────────────────────────────────┤
│  zozo_scraper.py / fetch_mms_cost.py / fetch_sheets.py             │
│  ↓ CSV/XLSX を GCS にアップロード                                  │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GCS (Cloud Storage) — gs://mono-back-office-system-raw-data/      │
│  └ uploads/{source}/{date}/*.csv                                   │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ETL Layer (main.py --csv-ingest)                                  │
└──────────────────────┬──────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BigQuery (asia-northeast1)                                        │
│  Project: mono-back-office-system                                  │
│                                                                    │
│  raw_layer        ─→ analytics_layer       ─→ mart_layer           │
│  (CSV保存版)        (整形済み・JOIN可能)     (発注判断用最終形)    │
└─────────────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ダッシュボード / 発注管理表 (Phase 2 で構築)                       │
└─────────────────────────────────────────────────────────────────────┘
```

**実行環境**:
- ホスト: Windows Server 2019 (社内サーバー、24時間稼働)
- 言語: Python 3.13
- ブラウザ自動化: Playwright + Chromium (ヘッドレス)
- GCPプロジェクト: `mono-back-office-system` (project# 560058725468)
- BQリージョン: asia-northeast1
- 実行時刻: **毎日 03:00 JST** (Windows Scheduled Task)

---

## 2. データソース一覧と取得方式

### 2.1 ZOZO Back Office — 9種類のCSV

| データリスト# | 名称 | 取得方式 | 取得スクリプト | GCS保存先 | 取得状況 |
|---|---|---|---|---|---|
| 1 | 受注 | form_post: `order_csv.asp` `c=Download&ost=order` | zozo_scraper.py | `uploads/zozo/orders/{date}/` | ✅ |
| 2 | 発送 | form_post: 同上 `ost=send` | zozo_scraper.py | `uploads/zozo/shipped/{date}/` | ✅ |
| 3 | 予約管理一覧 | page_form_submit: `Reserve.asp?c=ReserveList` | zozo_scraper.py | `uploads/zozo/reservations/{date}/` | ✅ |
| 4 | 倉庫在庫 (SKU毎) | form_post: `zaiko_csv2.asp` `SelectListType=1` | zozo_scraper.py | `uploads/zozo/inventory_sku/{date}/` | ✅ |
| 5 | 倉庫在庫 (入荷日毎) | form_post: `zaiko_csv2.asp` `SelectListType=2` | zozo_scraper.py | `uploads/zozo/inventory_arrival/{date}/` | ✅ |
| 6 | 在庫分析 | page_form_submit: `StockAnalysis.asp` | zozo_scraper.py | `uploads/zozo/stock_analysis/{date}/` | ✅ |
| 8 | 商品別実績(新) | Looker: filter→render→kebab→DL | zozo_scraper.py | `uploads/zozo/performance/{date}/` | ✅ |
| 9 | 登録商品 (SKU単位) | per-shop POST `GoodsSearch.asp` ×7ショップ | zozo_scraper.py | `uploads/zozo/product_master/{date}/` | ✅ |
| 17 | セール設定 | sales_center: `Sales_download.asp` (csrf+FileName) | zozo_scraper.py | `uploads/zozo/sale/{date}/` | ✅ |

**認証**:
- HTTP Basic 認証 (ZOZO_BASIC_USER/ZOZO_BASIC_PASS) ＋
- Form 認証 (ZOZO_USER/ZOZO_PASS)
- 全てSecret Manager (`mono-back-office-system` プロジェクト) に保管

**スクレイピング設計の特徴**:
- ソース毎に独立 (1つ失敗しても他は継続) — アシロボの「1つこけたら全部止まる」問題への対策
- リトライ・指数バックオフ機構搭載 (MAX_RETRIES_PER_SOURCE=3)
- セッション切れ自動再ログイン
- Shift-JIS (cp932) エンコーディング対応 (ZOZO BO CSV標準)

### 2.2 MMS — 原価データ (No.10)

| 項目 | 内容 |
|---|---|
| 取得方式 | Playwright ログイン → 19ショップを順次ループ → 「評価額一覧」CSV取得 |
| スクリプト | `pipeline/scrapers/fetch_mms_cost.py` |
| GCS保存先 | `uploads/mms/cost/{date}/評価額一覧-MMS.csv` |
| 認証 | LOGIN_USER (`shohin-kanri@mono-mart.jp`) / LOGIN_PASS (Secret Manager) |
| 行数 (直近) | 約 158,000行/日 (19ショップ合算) |

### 2.3 Google Sheets / Drive

| 名称 | 取得方式 | スクリプト | GCS保存先 |
|---|---|---|---|
| PF手数料表 | gspread (SA認証) | fetch_sheets.py | `uploads/sheets/pf_fee/{date}/pf_fee.csv` |
| 予約管理表(発注明細) | gspread (SA認証、2タブ合算) | fetch_sheets.py | `uploads/tableau/hacchu/{date}/発注明細.csv` |
| ブランド別買い回り | Drive API → xlsx 自動DL → CSV変換 | fetch_sheets.py | `uploads/sheets/buy_round/{date}/*.csv` |

**認証**: 専用サービスアカウント `sheets-fetcher@mono-back-office-system.iam.gserviceaccount.com`
**SA鍵**: `pipeline/sheets-sa-key.json`
**共有**: クライアント側でDriveフォルダを上記SAに「閲覧者」権限で共有

---

## 3. データフロー (GCS → BigQuery 3層構造)

### 3.1 取込みパイプライン

```
CSV (GCS) ─→ csv_ingest (main.py --csv-ingest)
              │
              ├─→ csv_orders        → analytics_layer.sales_daily      (受注)
              ├─→ csv_shipped       → analytics_layer.sales_daily      (発送、is_shipped=True)
              ├─→ csv_reservations  → analytics_layer.reservations
              ├─→ csv_inventory_sku → analytics_layer.inventory_snapshot
              ├─→ csv_stock_analysis→ analytics_layer.stock_analysis
              ├─→ csv_performance   → analytics_layer.sales_daily      (商品別実績)
              ├─→ csv_product_master→ analytics_layer.product_master   (Truncate+Insert)
              ├─→ csv_sale_settings → analytics_layer.sale_settings
              ├─→ csv_mms_cost      → analytics_layer.cost_master       (SCD2: valid_to更新)
              └─→ csv_tableau_hacchu→ analytics_layer.incoming_stock
              ↓
              rebuild_kpi_mart (06_simple_mart_build.sql)
              ↓
              mart_layer.order_analysis (1 SKU = 1 row)
```

### 3.2 BigQuery 3層構造

| 層 | 役割 | データセット名 | 用途 |
|---|---|---|---|
| **Raw** | CSV原本のスナップショット保管 | `raw_layer` | 監査・再処理用 |
| **Analytics** | 整形済・JOIN可能・パーティション分割 | `analytics_layer` | 分析クエリ・mart構築の元データ |
| **Mart** | 発注判断に必要な指標を1テーブル集約 | `mart_layer` | ダッシュボード・発注管理表の直接データソース |

---

## 4. BigQueryテーブル仕様

### 4.1 analytics_layer (基礎データ層)

| テーブル名 | 主キー | パーティション | クラスター | 行数 (直近1ヶ月) | 説明 |
|---|---|---|---|---|---|
| sales_daily | (sale_date, sku_code) | sale_date | product_code, sku_code | ~11.5M | 受注+発送+商品別実績を統合 |
| inventory_snapshot | (snapshot_date, sku_code, shop_name) | snapshot_date | product_code, sku_code | ~390K | 倉庫在庫の日次スナップショット |
| stock_analysis | (snapshot_date, sku_code) | snapshot_date | product_code, sku_code | ~246K | 在庫分析CSV（販売速度・販売可能数等） |
| reservations | (reservation_date, sku_code) | reservation_date | product_code, sku_code | ~2.8K | 予約管理一覧の未処理予約 |
| incoming_stock | (source_date, sku_code) | source_date | product_code, sku_code | ~60K | 発注明細から算出の入荷残 |
| cost_master | (sku_code, valid_from) | valid_from | product_code | ~1.75M (SCD2) | MMS原価マスタ。SCD2方式 |
| product_master | (sku_code) | なし | product_code, sku_code | ~140K | 全SKU (完売・非稼働含む) |
| sale_settings | (snapshot_date, item_code) | snapshot_date | shop_name, item_code | (Phase 1 後半で取込み) | セール設定 |

### 4.2 mart_layer.order_analysis (発注判断データ)

**1 SKU = 1 行**、`analysis_date` でパーティション。発注管理表の直接のデータソース。

| 列名 | 型 | 内容 | 計算根拠 |
|---|---|---|---|
| analysis_date | DATE | 分析対象日 (=前日) | 自動設定 |
| product_code | STRING | 品番 | inventory_snapshot or stock_analysis から |
| sku_code | STRING | CS品番 | 同上 |
| color_name | STRING | カラー | 同上 |
| size | STRING | サイズ | 同上 |
| **inventory** | INT64 | 在庫 | inventory_snapshot.stock_quantity (日付フィルタ済) |
| **incoming_stock** | INT64 | 入荷残 | 発注明細から (product+color+size でJOIN) |
| **reservations_pending** | INT64 | 予約未処理 | reservations.quantity (product+sku でJOIN) |
| **free_inventory** | INT64 | フリー在庫 | **= 在庫 + 入荷残 − 予約未処理** |
| sales_7d / 30d | INT64 | 7日 / 30日販売数 | sales_daily の集計 |
| daily_velocity_7d / 30d | FLOAT | 日次販売速度 | sales_7d/7, sales_30d/30 |
| stock_days_7d | FLOAT | 在庫日数 | = free_inventory / daily_velocity_7d |
| cost_price | NUMERIC | SKU原価 | cost_master (product+color+size でJOIN、valid_to IS NULL のみ) |
| period_revenue | NUMERIC | 30日合計売上 | sales_daily の合計金額(税抜) 30日合算 |
| period_total_cost | NUMERIC | 30日合計原価 | cost_price × 30日販売数 |
| gross_margin_pct | FLOAT | 粗利率(%) | = (period_revenue − period_total_cost) / period_revenue × 100 |
| **recommended_order_qty** | INT64 | 推奨発注数 | = MAX(0, ⌈8週 × 7日 × daily_velocity_30d − free_inventory⌉) |
| **order_urgency** | STRING | 緊急度 | CRITICAL / WARNING / OK / OVERSTOCK |
| days_to_stockout | FLOAT | 欠品まで日数 | free_inventory / daily_velocity_30d |
| monthly_sales | RECORD | 月別販売 | ARRAY<STRUCT<month, qty>> |
| daily_sales_30d | RECORD | 日別販売 (sparkline用) | 同上 |

---

## 5. 業務ロジック

### 5.1 フリー在庫公式 (クライアント最終仕様)

```
フリー在庫 = 在庫 + 入荷残 − 予約未処理
```

- **在庫**: ZOZO倉庫在庫(SKU毎)CSV の数量
- **入荷残**: 発注明細スプレッドシートの 発注数 (「入荷済みチェック」=FALSE のもの)
- **予約未処理**: 予約管理一覧CSV の未処理 quantity

**注**: 旧仕様の「÷0.7 逆算」は本Phase 1では不採用（クライアント仕様確定 2026-05-15）。

### 5.2 販売速度 (新色問題対応)

**SKU単位の実初回受注日ベース** で計算。

```
有効販売開始日 = MIN(sale_date) per (product_code, sku_code)
effective_days_7d  = MIN(7,  TODAY − 有効販売開始日 + 1)
effective_days_30d = MIN(30, TODAY − 有効販売開始日 + 1)
daily_velocity_7d  = sales_7d  / effective_days_7d
daily_velocity_30d = sales_30d / effective_days_30d
```

**理由**: 同一品番でブラック (既存・販売30日) とベージュ (新色・販売7日) を区別。ブラック÷7 過大評価／ベージュ÷30 過小評価を回避。

### 5.3 推奨発注数

```
推奨発注数 = MAX(0, ⌈8週 × 7日 × daily_velocity_30d − free_inventory⌉)
```

**8週**は将来在庫カバレッジ目標。クライアント環境変数 `TARGET_COVERAGE_WEEKS` で調整可能。

### 5.4 緊急度判定

| 緊急度 | 判定条件 |
|---|---|
| CRITICAL | stock_days_7d < `CRITICAL_STOCK_DAYS` (= 0) → 即欠品 |
| WARNING | stock_days_7d < `WARNING_STOCK_DAYS` (= 14) |
| OK | stock_days_7d ≤ `OVERSTOCK_STOCK_DAYS` (= 90) |
| OVERSTOCK | stock_days_7d > 90 → 在庫過多 |

### 5.5 粗利率

```
粗利率(%) = (period_revenue − cost_price × period_units_sold) / period_revenue × 100
```

- 30日合計売上ベース (受注CSV「合計金額（税抜）」)
- 原価は MMS評価額単価
- 値引き販売中はマイナス値が出る (= 異常検知シグナル)

---

## 6. 運用情報

### 6.1 実行スケジュール

| 時刻 | 処理 | 所要時間 |
|---|---|---|
| 03:00 JST | Windows Scheduled Task 起動 | - |
| 03:00〜03:30 | ZOZO 9源 スクレイピング (順次実行) | 約30分 |
| 03:30〜03:35 | MMS 原価 19ショップ取得 | 約5分 |
| 03:35〜03:38 | Sheets/Drive 取得 (PF手数料・発注明細・買い回り) | 約3分 |
| 03:38〜03:45 | BigQuery ETL ingest | 約7分 |
| 03:45〜03:48 | mart_layer.order_analysis 再構築 | 約3分 |
| **合計** | | **約45分** |

ZOZO BOアクセス負荷分散のため **順次実行** (PARALLEL_WORKERS=1)。

### 6.2 エラー対応

| 想定エラー | 対応 |
|---|---|
| ZOZO ログイン失敗 | 自動リトライ (最大3回、指数バックオフ) |
| セッション切れ | ページ内マーカー検出 → 自動再ログイン |
| 1ソース失敗 | 他ソースは継続実行 (アシロボ対策) |
| データ欠損 | ログ + 再実行コマンドをドキュメント化 (Phase 2 でダッシュボード化) |
| Lookeriframe不安定 | リトライ + 失敗ショップは翌日カバー |

### 6.3 ログ

- `logs/daily_{YYYYMMDD_HHmmss}.log` に全実行ログ
- 30日経過分は自動削除

### 6.4 シークレット管理

全認証情報は GCP Secret Manager (`mono-back-office-system` プロジェクト) で管理:

```
ZOZO_USER, ZOZO_PASS, ZOZO_BASIC_USER, ZOZO_BASIC_PASS
MMS_USER, MMS_PASS
SITATERU_USER, SITATERU_PASS
TABLEAU_USER, TABLEAU_PASS, TABLEAU_TOTP_SECRET
```

---

## 7. Phase 1 完了確認チェックリスト

### 7.1 達成項目

| 項目 | 達成内容 | 検証方法 |
|---|---|---|
| ✅ ZOZO BO 9源 自動取得 | 1,2,3,4,5,6,8,9,17 全て稼働 | `logs/daily_*.log` で確認 |
| ✅ MMS原価 自動取得 | 19ショップ 158K行/日 | `analytics_layer.cost_master` 1,754,221行 |
| ✅ Sheets 3種 自動取得 | PF手数料/発注明細/買い回り | GCS `uploads/sheets|tableau/` |
| ✅ BigQuery 3層構造 | raw / analytics / mart | `bq ls --project_id=mono-back-office-system` |
| ✅ mart_layer.order_analysis | 250,966 行 (直近1ヶ月) | 1 SKU = 1 行で重複なし |
| ✅ フリー在庫公式 | 在庫+入荷残−予約未処理、100%整合 | 検証クエリで `formula_ok = 100.00%` |
| ✅ 販売速度 SKU単位 | 新色問題対応済 | mart の `daily_velocity_7d/30d` |
| ✅ 推奨発注数 | 8週 × 30日販売速度 − フリー在庫 | mart の `recommended_order_qty` |
| ✅ 緊急度判定 | CRITICAL/WARNING/OK/OVERSTOCK | mart の `order_urgency` |
| ✅ 粗利率 | 30日合計売上ベース、平均49% / 中央値60% | mart の `gross_margin_pct` |
| ✅ 日次自動実行 | Windows Scheduled Task 03:00 JST | タスクスケジューラ + ログ |
| ✅ エラー継続実行 | 1ソース失敗で他継続 | zozo_scraper.py の retry/backoff |
| ✅ GCP移行 | careful-record-491804-h6 → mono-back-office-system | 全21テーブル移行完了 |

### 7.2 Phase 1 取得実績 (直近1ヶ月)

| データソース | 行数 | 最新取込日 |
|---|---|---|
| sales_daily | 11,498,688 | 2026-05-23 |
| inventory_snapshot | 390,331 | 2026-05-25 |
| stock_analysis | 246,443 | 2026-05-25 |
| reservations | 2,849 | 2026-05-25 |
| incoming_stock | 60,771 | 2026-05-24 |
| cost_master | 1,754,221 | 2026-05-25 |
| product_master | 140,429 | (常時最新) |
| **mart_layer.order_analysis** | **250,966** | **2026-05-25** |

---

## 8. Phase 2 引き継ぎ事項

### 8.1 Phase 2 と並行で進める未着手項目

| データリスト# | 項目 | 状況 | 着手予定 |
|---|---|---|---|
| 7 | ZOZOAD実績 | 未着手 | Phase 2 並行 |
| 13 | タブログ(Tableau) | API確認中 | 回答次第 |
| 15 | 商品レビュー | DL不可、ヘッドレスブラウザ方式 | Phase 2 |
| 16 | ファーストセラー | DL不可、ヘッドレスブラウザ方式 | 曜日定義確定後 |
| 18 | クーポン除外 | 取得フロー確定済 | **即着手可能** (5/29前) |
| 19 | アクセス実績(新) | クライアント側で再定義中 | 確定後 |
| 20 | 検索キーワード経由アクセス | 同上 | 確定後 |
| 21〜 | その他 | 必要に応じて | Phase 2 中盤 |

### 8.2 Phase 2 で対応するメイン作業

- **発注管理表の構築** (シート1: 経営者向け合計 / シート2: 詳細 / シート4: 別ビュー)
- **再実行UI** (ダッシュボード上クリック操作で対象データ再取得)
- **データ品質モニタリング** (取得成功/失敗をダッシュボードに可視化)
- **予約期間/欠品期間を考慮した販売速度補正**
- **入荷残の判定ロジック改善** (「何日以前は含めない」ルール導入)

### 8.3 Phase 1 で残った技術的な留意点

- Looker (商品別実績(新)) は iframe ロードが時々失敗 (5〜6/7ショップ程度)
- 商品レビュー / ファーストセラー はZOZO BO仕様上DL不可、ヘッドレスブラウザ方式は UI 変更時メンテナンス頻度高
- MMS原価は19ショップ × 評価額一覧 を毎日全件取得 (将来差分取得化検討)
- 月次xlsx (買い回り) は最新2ヶ月のみ取得 (履歴拡大は要件次第)

---

## 9. ファイル・ディレクトリ構成

```
C:/Users/Administrator/Downloads/Pictures/system/
├── run_daily.ps1                    # 日次実行オーケストレータ
├── pipeline/
│   ├── .env                          # 環境変数 (mono-back-office-system設定)
│   ├── config.py
│   ├── main.py                       # ETL CSV ingestion entry point
│   ├── sheets-sa-key.json            # Sheets SA key (mono-back-office-system)
│   ├── scrapers/
│   │   ├── zozo_scraper.py           # ZOZO BO 9源
│   │   ├── fetch_mms_cost.py         # MMS原価
│   │   ├── fetch_sheets.py           # Sheets/Drive (PF/発注/買い回り)
│   │   ├── fetch_tableau.py          # Tableau (API待ち)
│   │   └── interactive_login.py      # MMS/sitateru/Tableau セッション持続
│   ├── extractors/                   # CSV → 構造化データ変換
│   ├── loaders/                      # BigQuery 書込み
│   ├── transformers/                 # mart 再構築
│   └── sql/
│       ├── schema/                   # 各層テーブル定義 DDL
│       └── dml/06_simple_mart_build.sql  # mart 再構築 SQL
├── docs/phase1/
│   ├── PHASE1_設計書.md              # ←本ドキュメント
│   └── PHASE1_完了書.md              # 完了レポート (別紙)
└── logs/                             # 日次実行ログ (30日保持)
```

---

## 10. 連絡先

| 役割 | 連絡先 |
|---|---|
| 開発担当 | 山口（エルム） |
| クライアント | 株式会社MONO-MART |
| GCPプロジェクト | mono-back-office-system (560058725468) |
| BQリージョン | asia-northeast1 |

---

**改訂履歴**

| 日付 | 改訂内容 |
|---|---|
| 2026-05-26 | Phase 1 設計書 初版作成 |

---

**Phase 1 を本書をもって完了といたします。**
