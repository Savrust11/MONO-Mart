---
name: zozo-ad-report
description: ZOZOバックオフィスからZOZOADの品番別CSVレポートをダウンロードし、Google Spreadsheet「ZOZOAD DETA 2026.xlsx」に新しいシートとして追加するスキル。「ZOZOAD◎月◎日分　更新お願いします」というショートカット指示で実行する。
---

# ZOZOAD レポート更新スキル

ZOZOバックオフィスのZOZOADレポートページから品番別CSVをダウンロードし、Google Spreadsheetに整形して追加する。

## ショートカットトリガー

ユーザーが「ZOZOAD◎月◎日分　更新お願いします」と送信した場合、このスキルを実行する。年は2026年。

## 対象スプレッドシート

- **ファイル名**: `ZOZOAD DETA 2026.xlsx`
- **ファイルID**: `1-X0vkCaTgycj5qIXArofLKBqDbqob05Z`
- **形式**: Google Drive上のxlsx（Sheets APIでは直接操作不可、openpyxlで編集後再アップロード）
- **URL**: `https://docs.google.com/spreadsheets/d/1-X0vkCaTgycj5qIXArofLKBqDbqob05Z/edit`

## 実行手順

### Step 1: ZOZOバックオフィスにログイン

1. `https://to.zozo.jp/to/Advertisement.asp` にアクセス
2. 1回目ログイン: ID `<ZOZO_BASIC_USER>` / PASS `<ZOZO_BASIC_PASSWORD>`
3. 2回目ログイン: ID `MONO-MART01` / パスワード `s03120420ssssssssss`

### Step 2: ZOZOADレポートページへ移動

1. メニュー「サイト管理」をクリック
2. サブメニュー「ZOZOAD」をクリック
3. 左サイドメニュー「レポート」をクリック

### Step 3: CSVダウンロード

1. ショップ：指定なし（全ショップ）
2. 期間：対象日付を設定（「日付を指定する」チェックを入れたまま、開始日と終了日を同じ日付に設定）
3. 上部の「品番別CSV」ボタンをクリックしてダウンロード

### Step 4: CSVデータの整形とスプレッドシート更新

`scripts/update_zozoad_sheet.py` を使用してデータを整形・更新する。

```bash
python3 /home/ubuntu/skills/zozo-ad-report/scripts/update_zozoad_sheet.py <csv_path> <date_mmdd>
```

- `<csv_path>`: ダウンロードしたCSVファイルのパス
- `<date_mmdd>`: シート名に使う日付（例: `0411`）

スクリプトの処理内容:
1. Google DriveからxlsxをDL
2. CSVを読み込み、ショップごとにグループ化
3. ショップ順序: MONO-MART → EMMA CLOTHES → ADRER → Anchor Smith → BONLECILL（CSVに存在するショップのみ）
4. 各ショップブロックの先頭にヘッダー行（太字）を配置
5. ショップ間に2行の空行を挿入
6. 各ショップ内はclick列で降順ソート
7. 新しいシート名は日付（例: `0411`）
8. 更新後のxlsxをGoogle Driveに再アップロード

### Step 5: ログアウトと報告

1. ZOZOバックオフィスからログアウト
2. スプレッドシートのURLをユーザーに報告

## 列構成（18列）

| 列番号 | 列名 |
|---|---|
| 1 | ショップID |
| 2 | ショップ名 |
| 3 | 親カテゴリ |
| 4 | 子カテゴリ |
| 5 | ブランド品番 |
| 6 | 商品コード |
| 7 | 商品名 |
| 8 | 親商品タイプ |
| 9 | 子商品タイプ |
| 10 | アップロード日 |
| 11 | imp |
| 12 | click |
| 13 | コスト |
| 14 | 経由売上件数 |
| 15 | 経由売上金額（税抜） |
| 16 | CTR |
| 17 | CPC |
| 18 | ROAS |

## シートフォーマット

```
[ヘッダー行 - 太字] ショップID | ショップ名 | ... | ROAS
[データ行] MONO-MARTのデータ（click降順）
[空行]
[空行]
[ヘッダー行 - 太字] ショップID | ショップ名 | ... | ROAS
[データ行] EMMA CLOTHESのデータ（click降順）
[空行]
[空行]
... 以降同様
```

## 注意事項

- ZOZOバックオフィスでは指示された操作以外は絶対にNG
- 作業完了後は必ずログアウトする
- CSVのエンコーディングはShift_JISの可能性あり（`cp932`で読み込む）
