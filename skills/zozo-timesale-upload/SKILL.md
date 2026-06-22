---
name: zozo-timesale-upload
description: ZOZOバックオフィスでタイムセール用TXTファイルの作成・アップロード、およびタイムセール終了日時・再販売価格の変更を行うスキル。タイムセールファイル作成、タイムセールアップロード、一括セール予約、タイムセール終了日時変更、再販売価格変更の依頼時に使用する。
---

# ZOZOタイムセールアップロード・変更

タイムセール関連の作業は2種類ある：

1. **作業A：タイムセールファイルのアップロード** → 新しいタイムセールを設定
2. **作業B：タイムセール終了日時・再販売価格の変更** → 既存タイムセールを変更

よくある組み合わせ：作業B（終了日時を早める）→ 終了後45〜60分待つ → 作業A（新タイムセール設定）

ブラウザ操作の詳細は `references/browser-operations.md` を参照。

## ログイン情報（厳守）

**毎回必ず以下の値をコピーして使うこと。**

| 段階 | 項目 | 値 |
|------|------|----|
| Basic認証 | URL | `https://<ZOZO_BASIC_USER>:<ZOZO_BASIC_PASSWORD>@to.zozo.jp/to/Default.asp` |
| ログイン | ID | `MONO-MART01` |
| ログイン | パスワード | `s03120420ssssssssss` |

- `browser_fill_form` でID・パスワードを同時入力するのが最も確実
- ログアウト: `window.location.href = '...Default.asp?c=Logout'`

## 作業A：タイムセールファイルのアップロード

### TXTファイルフォーマット

タブ区切り、ヘッダー行なし、1品番1行。サンプル: `templates/timesale_sample.txt`

| 列 | 内容 | 例 |
|----|------|-----|
| 1 | ブランド品番 | sc678 |
| 2 | タイムセール価格（税抜） | 1800 |
| 3 | 開始日時（YYYYMMDDhh） | 2026041409 |
| 4 | 終了日時（YYYYMMDDhh） | 2026042809 |
| 5 | 再販売価格（税抜、プロパー=0） | 1817 |

### ファイル自動生成

スクリプトで一括生成可能：

```bash
python scripts/create_timesale_txt.py <output_file> <start_dt> <end_dt> '<items_json>'
```

例：
```bash
python scripts/create_timesale_txt.py /home/ubuntu/sale.txt 2026041409 2026042809 \
  '[{"brand":"sc678","price":1800,"reset_price":1817},{"brand":"hc991","price":1500,"reset_price":1540}]'
```

### アップロード手順

1. ログイン（上記参照）
2. 一括セール予約ページに移動: `TimeSaleSetting.asp`
3. 「タイムセール」ラジオボタンを選択
4. **ショップは「指定なし」**（MONO-MARTを選ぶとエラー）
5. ファイル入力要素を表示（CSSで非表示のため）→ `browser_upload_file` → 「アップロード」クリック
6. 「正常登録件数」を確認。複数ファイルは手順5を繰り返す
7. ログアウト・結果報告

### 時間制約（重要）

- タイムセール終了後、同一品番の再アップロードは **終了時刻の45〜60分後以降**
- 例：18:00終了 → 19:00以降にアップロード可能
- 時間指定アップロードは `schedule` ツールで対応

## 作業B：タイムセール終了日時・再販売価格の変更

### 変更手順

1. ログイン（上記参照）
2. セール予約確認ページに移動: `SaleSettingRegist_Tenant.asp?c=Reset`
3. **ブランド品番のみ入力して検索**（他の条件はデフォルトのまま）
4. チェックボックスにチェック、終了日時・再販売価格をJSで変更
5. **変更ボタンは必ず `browser_click` でUIクリック**（JS submit禁止→セッション切れ）
6. confirmダイアログは `window.confirm = function() { return true; }` で自動承認
7. 「セール予約を変更しました」を確認
8. 複数品番は品番ごとに手順2〜7を繰り返す
9. ログアウト・結果報告

### 絶対禁止事項

- **form.submit() を使わない** → 「unknowncommand」エラーでセッション切れ
- **button.click() を使わない** → 同上
- 変更ボタンは必ず `browser_click` のindex指定で押す

## Googleスプレッドシート保存

タイムセールファイルの内容は `gws sheets` でGoogleスプレッドシートにも保存する。
