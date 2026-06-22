# ブラウザ操作リファレンス

セール予約確認画面・一括セール予約画面でのブラウザ操作の詳細。

## 目次

1. [ログイン手順](#ログイン手順)
2. [一括セール予約画面でのアップロード操作](#一括セール予約画面でのアップロード操作)
3. [セール予約確認画面での変更操作](#セール予約確認画面での変更操作)
4. [トラブルシューティング](#トラブルシューティング)

## ログイン手順

```javascript
// 1. Basic認証付きURLにアクセス
// browser_navigate: https://<ZOZO_BASIC_USER>:<ZOZO_BASIC_PASSWORD>@to.zozo.jp/to/Default.asp

// 2. browser_fill_formでログイン（最も確実な方法）
// ログインID: MONO-MART01
// パスワード: s03120420ssssssssss

// 3. ログインボタンをbrowser_clickでクリック
```

パスワードが正しく入力されない場合のフォールバック：
```javascript
document.querySelector('input[type=password]').value = 's03120420ssssssssss';
```

## 一括セール予約画面でのアップロード操作

### ページURL
```
https://<ZOZO_BASIC_USER>:<ZOZO_BASIC_PASSWORD>@to.zozo.jp/to/TimeSaleSetting.asp
```

### タイムセール選択
ページ遷移後、「タイムセール」ラジオボタンをbrowser_clickで選択する。

### ショップ設定
**必ず「指定なし」のまま。** MONO-MARTを選ぶと以下のエラーが発生する：
> ログインユーザーに紐付くショップが取得できません。再度ログインし直してください。

ショップが「MONO-MART」になっている場合のJS修正：
```javascript
var shopSelect = document.querySelector('[name="ShopID"]');
if (shopSelect) {
    shopSelect.value = '';
    $(shopSelect).trigger('change');
}
```

### ファイル入力要素の表示
ファイル入力はCSSで非表示になっているため、表示させる必要がある：
```javascript
var fi = document.querySelector('input[type="file"]');
fi.style.display = 'block';
fi.style.opacity = '1';
fi.style.position = 'static';
fi.style.width = '300px';
fi.style.height = '40px';
```

表示後、`browser_upload_file` でファイルを指定し、「アップロード」ボタンをbrowser_clickでクリック。

### 複数ファイルのアップロード
1件目のアップロード完了後、結果画面でファイル入力要素を再度表示させ、2件目をアップロードする。同じ手順を繰り返す。

## セール予約確認画面での変更操作

### ページURL
```
https://<ZOZO_BASIC_USER>:<ZOZO_BASIC_PASSWORD>@to.zozo.jp/to/SaleSettingRegist_Tenant.asp?c=Reset
```

### 品番検索
**ブランド品番のみ入力して検索する。他の条件は全てデフォルトのまま。**

```javascript
// ブランド品番を入力
document.querySelector('[name="SEARCH_BrandNo"]').value = '品番をここに';
// 検索ボタンをクリック（ボタンのindex=3）
document.querySelectorAll('button')[3].click();
```

### 値の変更

検索結果が表示されたら、以下をJavaScriptで設定する：

```javascript
// 1. チェックボックスにチェック
var cb = document.querySelector('[name="IkkatsuSaleSettingIDs"]');
if (cb) cb.checked = true;

// 2. タイムセール終了日を変更（select2）
var $dateSelect = $('select[name*="EndDate"]');  // 実際のname属性は検索結果から確認
$dateSelect.val('2026/04/12').trigger('change');

// 3. タイムセール終了時刻を変更（select2）
var $timeSelect = $('select[name*="EndTime"]');  // 実際のname属性は検索結果から確認
$timeSelect.val('18').trigger('change');

// 4. 再販売価格を変更
var resetInput = document.querySelector('[name^="ResetPrice_"]');
if (resetInput) resetInput.value = '1817';

// 5. confirmダイアログを自動承認
window.confirm = function() { return true; };
```

**注意：** select要素のname属性は商品ごとに異なる場合がある。`browser_view`で確認してから操作すること。

### 変更ボタンのクリック

**絶対にJavaScriptのform.submit()やbutton.click()を使わないこと。**

→ セッションが切れて「unknowncommand」エラーになる。

**必ず `browser_click` でUIの変更ボタンを直接クリックする。**

1. `browser_view` で変更ボタンのindex番号を確認
2. `browser_click` でそのindex番号をクリック
3. confirmダイアログは事前に `window.confirm = function() { return true; }` で自動承認

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| 「unknowncommand」エラー | form.submit()によるセッション切れ | 再ログインし、browser_clickで操作する |
| 「ショップが取得できません」 | ショップがMONO-MARTに設定されている | ショップを「指定なし」に変更 |
| 検索結果0件 | タイムセールが既に終了している | 終了済み品番はセール予約確認から消える |
| 「正常登録件数：0件」 | タイムセール中の品番を再登録しようとした | 終了後45〜60分待ってから再アップロード |
| パスワードエラー | パスワードが重複入力された | JSでvalue直接設定してからログイン |
