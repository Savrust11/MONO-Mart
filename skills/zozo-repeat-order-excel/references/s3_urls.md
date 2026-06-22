# S3アップロード済みデータURL一覧

リピート発注表生成に必要なデータファイルのS3 CDN URL。デプロイ環境（manus.space）のバックエンドAPIからはこれらのURLでデータを取得する。

## マスタデータ・参照データ

| ファイル | 説明 | S3 URL |
|---|---|---|
| format_10day.xlsm | テンプレートExcel（10日刻み用） | `https://files.manuscdn.com/user_upload_by_module/session_file/310519663457994587/SKVcNxikZTNPwEvB.xlsm` |
| color_master.json | ZOZOカラーマスタ（JSON） | `https://files.manuscdn.com/user_upload_by_module/session_file/310519663457994587/YSWMIAQeITgMGZhX.json` |
| inventory_mono.csv | 在庫分析CSV（MONO-MART） | `https://files.manuscdn.com/user_upload_by_module/session_file/310519663457994587/JzsonxVMdaTzWvoO.csv` |
| reserve_list.csv | 予約管理一覧CSV | `https://files.manuscdn.com/user_upload_by_module/session_file/310519663457994587/UZcfGAKMhWUAwuQL.csv` |
| zozo_color_master.csv | ZOZOカラーマスタ（CSV） | `https://files.manuscdn.com/user_upload_by_module/session_file/310519663457994587/OfclPORPDwSDurnw.csv` |
| arrival_data.json | 入荷予定データ（JSON） | `https://files.manuscdn.com/user_upload_by_module/session_file/310519663457994587/QhuzzgOfddmqeFVH.json` |
| goods_cs.csv | 展開SKU CSV（全ショップ、約170MB） | `https://files.manuscdn.com/user_upload_by_module/session_file/310519663457994587/JKYQoKoUqNNLFgLJ.csv` |
| sales_mono.xlsx | 売上実績Excel（MONO-MART） | `https://files.manuscdn.com/user_upload_by_module/session_file/310519663457994587/pXukJHseQqBeyzDb.xlsx` |
| summary_item.csv | 商品サマリCSV | `https://files.manuscdn.com/user_upload_by_module/session_file/310519663457994587/bjaxYdHsLVDIQUYD.csv` |

## 注文生データ

注文生データ（1年分、全ショップ）はGoogleドライブに保存済み。`zozo-order-data` スキル参照。

### ショップ別Googleドライブフォルダ

| ショップ | フォルダID |
|----------|-----------|
| MONO-MART | `1Vu2A2f-vVqvlMhJ7U3MZkGNGqrfMxaXd` |
| EMMA CLOTHES | `1xFSXQRCkxFpCBKhxH5YCGJfuWVwi5Ux7` |
| ADRER | `1VaLqHLGMVBqx3Uy5Ql5wJlxZvXMOUJBU` |
| CLEL | `1yLfvtPpL8gVPVlXPxKcYWsEVCBhkIR3l` |
| Chaco closet | `1JZlmVvfDWFkXNJJqHXHKNEYBmyHJxPj4` |
| Anchor Smith | `1tNGBwxwBBjCyoG3Fh5LFLFRmyPqBMpJE` |

ファイル名パターン: `order_YYYYMM.csv`（例: `order_202504.csv`〜`order_202604.csv`）

## データアクセス方式

### サンドボックス環境（Manusタスク実行時）
- ローカルファイルパス or `gws` CLI でGoogleドライブから直接取得

### デプロイ環境（manus.space）
- S3 CDN URLからHTTP GETで取得（上記URL一覧）
- 注文生データはサービスアカウント経由でGoogle Drive APIから取得
- **ローカルファイルパス（`/home/ubuntu/...`）は使用不可**

## 更新方法

データファイルを更新する場合:
1. 新しいファイルをサンドボックスに配置
2. `manus-upload-file` でS3にアップロード
3. このファイルのURL一覧を更新
4. バックエンドAPIのURL定数を更新
