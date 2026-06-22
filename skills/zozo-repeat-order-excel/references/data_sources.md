# データソース詳細

## 目次
1. [展開SKU CSV](#1-展開sku-csv)
2. [在庫分析CSV](#2-在庫分析csv)
3. [注文生データ](#3-注文生データ)
4. [入荷予定スプレッドシート](#4-入荷予定スプレッドシート)
5. [予約管理一覧CSV](#5-予約管理一覧csv)
6. [ZOZOカラーマスタ](#6-zozoカラーマスタ)
7. [フォーマットExcel](#7-フォーマットexcel)

---

## 1. 展開SKU CSV

全ショップの登録済み商品情報（完売品含む）。品番からショップ名・商品コード・SKU一覧を取得する。

**場所:** Googleドライブ `展開SKU` フォルダ（ID: `1l-0Mtv0siPYuRq0I5xCZCBWTJVfTJFrM`）
**ファイル名:** `goods_cs.csv`（約170MB）
**エンコーディング:** cp932

**主要列:**

| 列名 | 用途 |
|------|------|
| ショップ名 | ショップ判別 |
| ブランド品番 | 品番でフィルタ |
| 商品コード | 画像URL生成に使用 |
| CS品番 | SKU識別子 |
| カラー | カラー名 |
| サイズ | サイズ名 |
| 商品名 | 商品名 |
| 販売価格（税抜） | 価格情報 |
| プロパー価格（税抜） | 定価情報 |

**読み込み注意:**
- 170MBと大きいため、全体をpandasで読むと遅い
- `grep`で品番を先に抽出してからCSVパースする方法を推奨:

```python
import subprocess, csv, io

result = subprocess.run(['grep', item_code, '/path/to/goods_cs.csv'], capture_output=True, text=True)
header = subprocess.run(['head', '-1', '/path/to/goods_cs.csv'], capture_output=True, text=True).stdout.strip()
csv_text = header + '\n' + result.stdout
df = pd.read_csv(io.StringIO(csv_text), encoding='cp932')
```

---

## 2. 在庫分析CSV

ショップ別の在庫状況CSV。販売可能数・直近販売数・お気に入り数を取得する。

**場所:** Googleドライブ `在庫分析` フォルダ（ID: `1pVDIHNPvuqPJH8Gy8hLUqvJqQGb5Ux2X`）
**ファイル名:** `在庫状況({ショップ名}).csv`（例: `在庫状況(MONO-MART).csv`）
**エンコーディング:** cp932

**ショップ名とファイル名の対応:**

| ショップ | ファイル名 |
|----------|-----------|
| MONO-MART | 在庫状況(MONO-MART).csv |
| EMMA CLOTHES | 在庫状況(EMMA CLOTHES).csv |
| ADRER | 在庫状況(ADRER).csv |
| CLEL | 在庫状況(CLEL).csv |
| Chaco closet | 在庫状況(Chaco closet).csv |
| Anchor Smith | 在庫状況(Anchor Smith).csv |
| BONLECILL | 在庫状況(BONLECILL).csv |

**主要列（列名に先頭スペースあり→.strip()必須）:**

| 列名 | 用途 |
|------|------|
| ブランド品番 | 品番でフィルタ |
| CS品番 | SKU識別子 |
| カラー | カラー名 |
| サイズ | サイズ名 |
| 販売可能数 | 現在庫 |
| 直近7日販売数 | 7日販売 |
| 直近30日販売数 | 30日販売 |
| お気に入り登録数 | お気に入り数 |
| 販売価格（税抜） | 販売価格 |
| プロパー価格（税抜） | 定価 |

**注意:** 販売可能数があるもの（完売後30日まで）しか掲載されないため、完売して30日以上経過したSKUは展開SKU CSVで補完する。

---

## 3. 注文生データ

ショップ別の月次注文データCSV。10日刻み売上実績の算出に使用する。

**場所:** Googleドライブ（zozo-order-dataスキル参照）

**ショップ別フォルダ:**

| ショップ | フォルダID |
|----------|-----------|
| MONO-MART | `1Vu2A2f-vVqvlMhJ7U3MZkGNGqrfMxaXd` |
| EMMA CLOTHES | `1xFSXQRCkxFpCBKhxH5YCGJfuWVwi5Ux7` |
| ADRER | `1VaLqHLGMVBqx3Uy5Ql5wJlxZvXMOUJBU` |
| CLEL | `1yLfvtPpL8gVPVlXPxKcYWsEVCBhkIR3l` |
| Chaco closet | `1JZlmVvfDWFkXNJJqHXHKNEYBmyHJxPj4` |
| Anchor Smith | `1tNGBwxwBBjCyoG3Fh5LFLFRmyPqBMpJE` |
| BONLECILL | `1Vu2A2f-vVqvlMhJ7U3MZkGNGqrfMxaXd` |

**ファイル名パターン:** `order_YYYYMM.csv`（例: `order_202504.csv`〜`order_202604.csv`）
**エンコーディング:** UTF-8

**主要列（28列）:**

| 列名 | 用途 |
|------|------|
| ブランド品番 | 品番でフィルタ |
| CS品番 | SKU識別子 |
| カラー | カラー名 |
| サイズ | サイズ名 |
| 注文数 | 販売数量 |
| 注文日 | 日付（10日刻み算出） |
| 販売タイプ | 予約/通常の判別 |
| 販売価格（税抜） | 平均売価算出 |
| 合計金額（税抜） | 売上金額 |

**読み込み注意:**
- ヘッダー28列に対しデータ行が末尾カンマで29列になる場合あり
- 対策: ヘッダーに`extra`列を追加するか、データ行の末尾を切り捨て

```python
header_with_extra = header + ',extra'
all_lines = [header_with_extra]
# grepで品番抽出後、all_linesに追加
df = pd.read_csv(StringIO('\n'.join(all_lines)), on_bad_lines='skip', dtype=str)
```

---

## 4. 入荷予定スプレッドシート

ブランド別シートに入荷予定データが格納されたGoogleスプレッドシート。

**スプレッドシートID:** `1Lq9xs8K_BxuDHNid2F5oGRiXCb0egLOM9ZfQVz_FJxw`

**シート名:** ブランド名（MONO-MART, EMMA CLOTHES, ADRER, CLEL等）

**データ取得方法:**
```bash
gws sheets +read --spreadsheet '1Lq9xs8K_BxuDHNid2F5oGRiXCb0egLOM9ZfQVz_FJxw' \
  --range '{ブランド名}' --output-format json > arrival_data.json
```

**主要列:**

| 列名 | 用途 |
|------|------|
| ZOZO親品番 | 品番でフィルタ |
| ZOZOカラー | カラー名 |
| ZOZOサイズ | サイズ名 |
| ZOZOCS品番 | SKU識別子 |
| 発注数 | 入荷予定数 |
| ZOZO納品予定日 | 納品予定日 |

---

## 5. 予約管理一覧CSV

ショップ別の予約管理一覧CSV。予約受注済み未出荷の枚数を取得する。

**場所:** Googleドライブ `予約管理一覧` フォルダ（ID: `18UytO2GDrMkJvWTLnqGEwlH0Nw3Qlqwv`）
**ファイル名:** `reserve_list_{ショップ名}.csv`
**エンコーディング:** cp932

**主要列:**

| 列名 | 用途 |
|------|------|
| ブランド品番 | 品番でフィルタ |
| CS品番 | SKU識別子 |
| 予約受付数 | 予約数 |
| 注文数 | 注文済み数 |
| 未処理 | 予約未処理数（発注表AA列に使用） |

---

## 6. ZOZOカラーマスタ

カラー名→カラーコードの変換マスタ。商品画像URL生成に使用する。

**場所:** Googleドライブ `ZOZOカラーマスタ` フォルダ（ID: `1VtgPjKhZ1Zy4cMJwGnxz3Zy8nDqFZxYn`）
**ファイル名:** `color_master.csv`
**エンコーディング:** cp932

**列:**

| 列名 | 用途 |
|------|------|
| カラー名 | 在庫分析のカラー名と照合 |
| カラーコード | 画像URL生成に使用 |

**画像URL生成式:**
```
https://o.imgz.jp/{商品コード末尾3桁}/{商品コード}/{商品コード}b_{カラーコード}_d.jpg
```

例: 商品コード`82343719`、カラーコード`8`（ブラック）の場合:
```
https://o.imgz.jp/719/82343719/82343719b_8_d.jpg
```

---

## 7. フォーマットExcel

リピート発注管理表のテンプレートファイル。

**場所:** Googleドライブ `AI商品発注判断支援用（仮）/発注管理表フォーマット/`
**ファイルID:** `1SMO_tV2Cs1kRqr8s9EBCftSoGV4PPiyS`
**ファイル名:** `10日刻み用.xlsm`

**ダウンロード方法:**
```bash
gws drive files get --params '{"fileId": "1SMO_tV2Cs1kRqr8s9EBCftSoGV4PPiyS"}' --download-to /path/to/template.xlsm
```

**注意:** テンプレートは.xlsmだが、出力は.xlsx（VBAなし）で保存する。
