---
name: zozo-md-plan
description: ZOZO内の買い回りデータ・ショップ指標データ・注文データ・原価データを統合し、ブランド別×カテゴリ別のMD計画（強化推奨・新規参入・見直し）を自動生成するスキル。MDスコア算出、価格帯ギャップ分析、相性ショップランキングを含む。MD計画分析、カテゴリ戦略提案、品揃え最適化の依頼時に使用する。
---

# ZOZO MD計画分析スキル

## 概要

4種類のデータを統合し、ブランドごとのカテゴリ別MD提案を生成する3ステップ分析。

1. **外部環境分析**: 買い回りデータ × ショップ指標 → カテゴリ需要・相性ショップ
2. **内部環境分析**: 注文データ × 原価データ → 自社パフォーマンス
3. **クロス分析**: 外部×内部 → MDスコア算出・アクション提案・価格帯ギャップ

最終出力は MONO BACK OFFICE の MD計画ページで表示するJSON。

## 前提条件

- 買い回りデータ（月次Excel）がダウンロード済み
- ショップ指標データ（月次Excel）がダウンロード済み（Google Driveから取得）
- 注文データが `/home/ubuntu/order_data/` に存在（`zozo-order-data` スキル参照）
- 原価データが `/home/ubuntu/sales_data/cost_data.csv` に存在

## ワークフロー

```
1. データ準備・確認
2. Step1: 外部環境分析（scripts/md_plan_step1_external.py）
3. Step2: 内部環境分析（scripts/md_plan_step2_internal.py）
4. Step3: クロス分析・JSON生成（scripts/md_plan_step3_cross.py）
5. CDNアップロード（manus-upload-file --webdev）
6. フロントエンド更新（useMdPlan.ts の DATA_URL）
```

## Step 1: データ準備

### 必要ファイルの確認

```bash
# 買い回りデータ
ls /home/ubuntu/買い回りデータ*.xlsx

# ショップ指標データ（なければGoogle Driveから取得）
ls /home/ubuntu/shop_data/*.xls
# 取得例:
gws drive files list --params '{"q": "name contains '\''集計'\'' and mimeType = '\''application/vnd.ms-excel'\''"}'  
gws drive files download --file-id <ID> --output-path /home/ubuntu/shop_data/

# 注文データ
ls /home/ubuntu/order_data/order_2026*.csv

# 原価データ
ls /home/ubuntu/sales_data/cost_data.csv
```

### ファイルパスの更新

各スクリプトの先頭にあるファイルパス定数を実際のパスに合わせて編集する。

## Step 2: 外部環境分析の実行

```bash
python3 /home/ubuntu/skills/zozo-md-plan/scripts/md_plan_step1_external.py 2>&1
```

**処理内容**: 買い回りExcelの全シート（ブランド）を読み込み、カテゴリ（商品親タイプ）×価格帯で集計。ショップ指標データと結合して相性スコアを算出。

**出力**: `/home/ubuntu/md_plan_step1_result.json`

**注意点**:
- 買い回りExcelは1ファイル100MB超。メモリ節約のため1シートずつ処理する。
- カテゴリ列は `商品親タイプ`（列インデックス6）を使用。`子カテゴリ`（列インデックス5）はブランド名が入っているため不可。
- ショップ指標Excelのヘッダー位置がファイルにより異なる場合あり。

## Step 3: 内部環境分析の実行

```bash
python3 /home/ubuntu/skills/zozo-md-plan/scripts/md_plan_step2_internal.py 2>&1
```

**処理内容**: 注文CSVを1ファイルずつ読み込み、ブランド×カテゴリ別の売上・型数・FKU・SKU・プロパー比率を集計。原価データと結合して粗利率を算出。

**出力**: `/home/ubuntu/md_plan_step2_result.json`

**注意点**:
- 注文CSVの列ずれ問題: ヘッダー28列に対しデータ行29フィールド。先頭に親ショップ名「MONO-MART」が追加されている。スクリプト内の `CORRECT_COLUMNS` で正しいマッピングを定義済み。
- CSVの読み込みは `csv.reader` で行い、29フィールドの場合のみ処理する。
- メモリ節約のため1ファイルずつストリーミング処理。

## Step 4: クロス分析・JSON生成

```bash
python3 /home/ubuntu/skills/zozo-md-plan/scripts/md_plan_step3_cross.py 2>&1
```

**処理内容**: Step1・Step2の結果を統合し、MDスコアを算出。カテゴリごとにアクション（強化推奨/維持/見直し/参入検討/要調査）を判定。価格帯ギャップ分析を実施。

**出力**: `/home/ubuntu/md_plan_final.json`

**MDスコア算出**: `references/output_schema.md` 参照。

## Step 5: CDNアップロードとフロントエンド更新

```bash
# アップロード
cp /home/ubuntu/md_plan_final.json /home/ubuntu/webdev-static-assets/
manus-upload-file --webdev /home/ubuntu/webdev-static-assets/md_plan_final.json

# フロントエンド更新
# client/src/hooks/useMdPlan.ts の DATA_URL を新しいCDN URLに変更
```

## データスキーマ

詳細は `references/data_sources.md`（入力）と `references/output_schema.md`（出力）を参照。

## 分析対象ブランド

| ブランド | 買い回りデータ | 注文データ | 備考 |
|---|---|---|---|
| MONO-MART | あり | あり | メインブランド |
| EMMA CLOTHES | あり | あり（4型のみ） | 注文データ少量 |
| CLEL | あり | あり | |
| ADRER | あり | なし | 買い回りのみ |
| WYM LIDNM | あり | あり | |

注文データに含まれないブランド（ADRER等）は、外部環境分析のみでMD提案を生成する（タイプ=新規参入、内部データなし）。
