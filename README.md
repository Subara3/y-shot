# y-shot

Webフォームの入力チェックを自動化するスクリーンショットツール。
テストパターンを登録し、入力→スクショ→送信→結果スクショをパターン分だけ自動で繰り返します。

## セットアップ

```bash
pip install -r requirements.txt
```

Chrome が必要です（ChromeDriver は Selenium 4.6+ で自動ダウンロードされます）。

## 使い方

```bash
python y_shot.py
```

### 基本的な流れ

1. **設定** (歯車ボタン): 対象URL、Basic認証、出力先を設定
2. **パターンセット** (タブ2): テスト入力値のセットを作成（テンプレートやプリセットも利用可能）
3. **テストケース** (タブ1): テストケースを作成し、ステップとパターンセットを紐付け
4. **要素ブラウザ** (右パネル): ページの要素を取得してステップに追加
5. **実行**: 全テストケースを順番に実行

### テストケースの例

```
テストA: 全画面確認（パターンなし→1回実行）
  スクショ(fullpage)

テストB: 名前欄チェック（パターン: 名前欄チェック→13回ループ）
  入力 #name_sei ← {パターン}
  スクショ(margin) #name_sei
  クリック #submit
  スクショ(fullpage)
```

### パターンセットの例

名前欄チェック: 未入力、全角スペース、©、🦐、ＡＢＣＤＥ、12345 ...

### テンプレート

`templates/` フォルダにCSVを入れると、パターンセットに読み込めます。同梱テンプレート:

- 入力チェック_基本 (13パターン)

## exe化

```bash
pip install flet
flet pack y_shot.py --name y-shot --add-data "templates;templates"
```

`dist/y-shot.exe` が生成されます。`templates/` フォルダはexeに同梱されます。

## ファイル構成

```
y-shot/
├── y_shot.py              # メインアプリ
├── requirements.txt       # 依存パッケージ
├── build.bat              # exe化スクリプト
├── test_form.html         # ローカルテスト用フォーム
├── templates/             # パターンテンプレート (CSV)
│   └── 入力チェック_基本.csv
├── y_shot_config.ini      # 設定ファイル (自動生成、git除外)
├── y_shot_tests.json      # テストケース (自動生成)
├── y_shot_patterns.json   # パターンセット (自動生成)
├── y_shot_selectors.json  # セレクタバンク (自動生成)
└── screenshots/           # スクショ出力先 (自動生成)
```

## 開発者

Yuri Norimatsu
