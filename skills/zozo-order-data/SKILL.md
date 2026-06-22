---
name: zozo-order-data
description: 株式会社MONO-MART全ショップ（MONO-MART, EMMA CLOTHES, ADRER, CLEL, Chaco closet, Anchor Smith, BONLECILL）のZOZO注文生データ（2025年4月〜2026年4月、注文レベル）のGoogleドライブ保存場所・ファイル構造・列定義を提供するスキル。併売分析、顧客分析、売上分析、リピート分析など、注文レベルの生データが必要なタスクで使用する。
---

# ZOZO注文データ（全ショップ）

## データ概要

- **会社**: 株式会社MONO-MART
- **対象ショップ**: MONO-MART, EMMA CLOTHES, ADRER, CLEL, Chaco closet, Anchor Smith, BONLECILL（anownはデータなし）
- **粒度**: 注文レベル（1行 = 1注文×1商品）
- **エンコーディング**: UTF-8（元のSHIFT_JISから変換済み）
- **ソース**: ZOZOバックオフィス > 分析 > 注文

## ショップ別Googleドライブ一覧

| ショップ | フォルダ名 | フォルダID | 期間 | 概算行数 |
|---|---|---|---|---|
| MONO-MART | MONO-MART注文データ生データ（25年5月-26年3月） | `1DEhmWxz-ysXF52Ep7he0Tp6Spm0a-HLr` | 25/04-26/04 | 約745万行 |
| EMMA CLOTHES | EMMA CLOTHES注文データ（25年4月-26年4月） | `1Xxv7XJ7_xbApdVzwBTeSUprkcazHJFdL` | 25/04-26/04 | 約156万行 |
| ADRER | ADRER注文・在庫データ（25年4月-26年4月） | `1IKive_EDqVS-2OIlfAJSoP2v6ecnBOzl` | 25/04-26/04 | 約58万行 |
| CLEL | CLEL注文・在庫データ（25年4月-26年4月） | `1VpColFrXeouYBsHYqhD8s6lcUcZsR7vi` | 25/04-26/04 | 約67万行 |
| Chaco closet | Chaco closet注文データ（25年4月-26年4月） | `1OLWmFbdU1vI4qME9qRVtx5MEc7FO21xQ` | 25/04-26/04 | 約1.5万行 |
| Anchor Smith | Anchor Smith注文データ（25年4月-26年4月） | `1YdcUxu6A4f8ZDnX-ttR-7ECmapwRYSz7` | 25/04-26/04 | 約24万行 |
| BONLECILL | BONLECILL注文データ（25年4月-26年4月） | `1X4_4DrUOlv7KTCR-eyQct_wqlb9witUW` | 25/04-26/04 | 約63万行 |

## MONO-MART ファイル一覧

フォルダ名が「25年5月-26年3月」だが、実際には25年4月・26年4月も含む。7月以降は半月分割。

| ファイル名 | 期間 | サイズ | 行数 |
|---|---|---|---|
| order_202504.csv | 2025/4/1-4/30 | 137MB | 400,197 |
| order_202505.csv | 2025/5/1-5/31 | 235MB | 681,974 |
| order_202506.csv | 2025/6/1-6/30 | 257MB | 746,776 |
| order_202507a.csv | 2025/7/1-7/15 | 138MB | 401,139 |
| order_202507b.csv | 2025/7/16-7/31 | 131MB | 374,339 |
| order_202508a.csv | 2025/8/1-8/15 | 92MB | 259,751 |
| order_202508b.csv | 2025/8/16-8/31 | 84MB | 236,442 |
| order_202509a.csv | 2025/9/1-9/15 | 50MB | 145,335 |
| order_202509b.csv | 2025/9/16-9/30 | 59MB | 171,326 |
| order_202510a.csv | 2025/10/1-10/15 | 92MB | 265,342 |
| order_202510b.csv | 2025/10/16-10/31 | 145MB | 409,110 |
| order_202511a.csv | 2025/11/1-11/15 | 148MB | 418,541 |
| order_202511b.csv | 2025/11/16-11/30 | 188MB | 530,007 |
| order_202512a.csv | 2025/12/1-12/15 | 164MB | 463,187 |
| order_202512b.csv | 2025/12/16-12/31 | 135MB | 385,899 |
| order_202601a.csv | 2026/1/1-1/15 | 164MB | 473,115 |
| order_202601b.csv | 2026/1/16-1/31 | 93MB | 262,862 |
| order_202602a.csv | 2026/2/1-2/15 | 78MB | 223,483 |
| order_202602b.csv | 2026/2/16-2/28 | 77MB | 216,712 |
| order_202603.csv | 2026/3/1-3/31 | 39MB | 108,924 |
| order_202604.csv | 2026/4/1-4/11 | 97MB | 281,420 |

## EMMA CLOTHES ファイル一覧

| ファイル名 | 期間 | サイズ | 行数 |
|---|---|---|---|
| order_202504-202506.csv | 2025/4/12-6/30 | 108MB | 307,553 |
| order_202507-202509.csv | 2025/7/1-9/30 | 114MB | 326,842 |
| order_202510-202512.csv | 2025/10/1-12/31 | 166MB | 475,414 |
| order_202601-202604.csv | 2026/1/1-4/11 | 157MB | 450,851 |

## ADRER ファイル一覧（注文データのみ）

フォルダには在庫データ・予測データも含まれるが、注文CSVのみ記載。

| ファイル名 | 期間 | サイズ | 行数 |
|---|---|---|---|
| ADRER注文データ_202504-202506.csv | 2025/4/12-6/30 | 31MB | 102,660 |
| ADRER注文データ_202507-202509.csv | 2025/7/1-9/30 | 45MB | 151,424 |
| ADRER注文データ_202510-202512.csv | 2025/10/1-12/31 | 45MB | 156,797 |
| ADRER注文データ_202601-202604.csv | 2026/1/1-4/7 | 46MB | 159,670 |
| order_20260408-20260411.csv | 2026/4/8-4/11 | 2MB | 6,486 |

## CLEL ファイル一覧（注文データのみ）

| ファイル名 | 期間 | サイズ | 行数 |
|---|---|---|---|
| CLEL注文データ_202504-202506.csv | 2025/4/12-6/30 | 47MB | 152,556 |
| CLEL注文データ_202507-202509.csv | 2025/7/1-9/30 | 44MB | 144,854 |
| CLEL注文データ_202510-202512.csv | 2025/10/1-12/31 | 62MB | 202,481 |
| CLEL注文データ_202601-202604.csv | 2026/1/1-4/7 | 53MB | 172,631 |

## Chaco closet / Anchor Smith / BONLECILL

各フォルダに1ファイルずつ（全期間一括）。

| ショップ | ファイル名 | 期間 | サイズ | 行数 |
|---|---|---|---|---|
| Chaco closet | order_202504-202604.csv | 2025/4/12-2026/4/11 | 5MB | 15,126 |
| Anchor Smith | order_202504-202604.csv | 2025/4/12-2026/4/11 | 82MB | 238,731 |
| BONLECILL | order_202504-202604.csv | 2025/4/12-2026/4/11 | 216MB | 627,154 |

## 列定義（28列、全ショップ共通）

```
ショップ名, 親カテゴリ, 子カテゴリ, 親商品タイプ, 子商品タイプ, 性別,
ブランド品番, CS品番, 商品名, カラー, サイズ, 販売開始日,
販売価格（税抜）, 販売タイプ, 価格タイプ, プロパー価格（税抜）,
注文番号, 注文数, 合計金額（税抜）, 注文日, 発送日, 注文時端末,
キャンセル, 会員ID, 年齢, 会員性別, 県名, モール
```

## ダウンロード方法

rcloneでGoogleドライブからダウンロードする。

```bash
# MONO-MART全ファイル
rclone copy "manus_google_drive:MONO-MART注文データ生データ（25年5月-26年3月）" /home/ubuntu/order_data/mono-mart/ \
  --config /home/ubuntu/.gdrive-rclone.ini --progress

# EMMA CLOTHES全ファイル
rclone copy "manus_google_drive:EMMA CLOTHES注文データ（25年4月-26年4月）" /home/ubuntu/order_data/emma-clothes/ \
  --config /home/ubuntu/.gdrive-rclone.ini --progress

# ADRER（注文データのみ）
rclone copy "manus_google_drive:ADRER注文・在庫データ（25年4月-26年4月）" /home/ubuntu/order_data/adrer/ \
  --config /home/ubuntu/.gdrive-rclone.ini --include "*注文*" --include "order_*" --progress

# CLEL（注文データのみ）
rclone copy "manus_google_drive:CLEL注文・在庫データ（25年4月-26年4月）" /home/ubuntu/order_data/clel/ \
  --config /home/ubuntu/.gdrive-rclone.ini --include "*注文*" --progress

# Chaco closet
rclone copy "manus_google_drive:Chaco closet注文データ（25年4月-26年4月）" /home/ubuntu/order_data/chaco-closet/ \
  --config /home/ubuntu/.gdrive-rclone.ini --progress

# Anchor Smith
rclone copy "manus_google_drive:Anchor Smith注文データ（25年4月-26年4月）" /home/ubuntu/order_data/anchor-smith/ \
  --config /home/ubuntu/.gdrive-rclone.ini --progress

# BONLECILL
rclone copy "manus_google_drive:BONLECILL注文データ（25年4月-26年4月）" /home/ubuntu/order_data/bonlecill/ \
  --config /home/ubuntu/.gdrive-rclone.ini --progress
```

## 読み込み例（Python）

```python
import pandas as pd, glob

# 特定ショップの全データ
df = pd.concat([pd.read_csv(f) for f in sorted(glob.glob('/home/ubuntu/order_data/emma-clothes/order_*.csv'))], ignore_index=True)

# MONO-MART特定月
df = pd.read_csv('/home/ubuntu/order_data/mono-mart/order_202603.csv')

# 全ショップ横断（メモリ注意）
all_dfs = []
for shop in ['mono-mart', 'emma-clothes', 'adrer', 'clel', 'chaco-closet', 'anchor-smith', 'bonlecill']:
    for f in sorted(glob.glob(f'/home/ubuntu/order_data/{shop}/*.csv')):
        all_dfs.append(pd.read_csv(f))
df_all = pd.concat(all_dfs, ignore_index=True)
```

## 注意事項

- 全ファイルにヘッダー行あり（重複ヘッダーなし、結合時そのままでOK）
- `キャンセル` 列にキャンセル済み注文が含まれる場合あり（分析時にフィルタリング推奨）
- データ量が大きいため、必要なショップ・月・列のみ読み込むことを推奨
- anownはZOZOバックオフィスにデータなし（0件）

## サマリーCSVの場所（MONO-MARTのみ）

品番別・月別等の集計済みサマリーCSVは別フォルダに保存済み。サマリーで済む分析にはこちらを優先使用する。

**フォルダ名**: `MONO-MART注文データサマリー（25年4月-26年3月）`
**フォルダID**: `1mx5kdPZxFUjE4utzEFCQ_DtF7ArOZ6VB`
**URL**: https://drive.google.com/drive/folders/1mx5kdPZxFUjE4utzEFCQ_DtF7ArOZ6VB
