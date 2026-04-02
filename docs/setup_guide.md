# y-shot / y-diff ソースコードセットアップ手順書

対象: ソースコードからの環境構築・ビルド・実行
バージョン: y-shot v2.3 / y-diff v1.4

---

## 1. 前提条件

| 項目 | 要件 |
|------|------|
| **OS** | Windows 10 / 11 |
| **Python** | 3.14（Selenium の互換性により 3.14 系を使用） |
| **Google Chrome** | 最新版（ChromeDriver は Selenium が自動ダウンロード） |

> **注意**:
> - Selenium の互換性のため **Python 3.14 系**を使用してください。
> - Microsoft Store 版の Python は動作しません。[python.org](https://www.python.org/downloads/) からインストールしてください。
> - インストール時に「Add Python to PATH」にチェックを入れてください。

---

## 2. 環境構築

### 2.1 Python の確認

コマンドプロンプトで以下を実行し、バージョンが表示されることを確認します。

```
py --version
```

### 2.2 依存パッケージのインストール

プロジェクトルートで以下を実行します。

```
pip install -r requirements.txt
```

インストールされるパッケージ:

| パッケージ | 用途 |
|-----------|------|
| selenium | ブラウザ自動操作 |
| Pillow | 画像処理 |
| flet | GUI フレームワーク |
| openpyxl | Excel エビデンス出力 |
| pyinstaller | exe ビルド |

---

## 3. ソースから実行

### 3.1 y-shot（メインツール）

```
py y_shot.py
```

初回起動時に `y_shot_config.ini`（設定）や各種 JSON ファイルが自動生成されます。

### 3.2 y-diff（スクリーンショット比較ツール）

```
py y_diff.py
```

---

## 4. exe ビルド

### 4.1 個別ビルド

```
build.bat          … y-shot.exe を生成
build_diff.bat     … y-diff.exe を生成
```

生成先はいずれも `dist/` フォルダです。

### 4.2 配布パッケージ作成

```
release_build.bat
```

`release/y-shot/` に exe + テンプレート + マニュアル + サンプルを同梱したフォルダと ZIP が作成されます。

> **注意**: `release_build.bat` 内のバージョン番号（ZIP ファイル名）は手動で更新してください。

---

## 5. ファイル構成

```
y-shot/
├── y_shot.py              # y-shot メインアプリ
├── y_diff.py              # y-diff 比較ツール
├── requirements.txt       # 依存パッケージ
├── y-shot.spec            # y-shot 用 PyInstaller 設定
├── y-diff.spec            # y-diff 用 PyInstaller 設定
├── build.bat              # y-shot ビルドスクリプト
├── build_diff.bat         # y-diff ビルドスクリプト
├── release_build.bat      # 配布パッケージ作成
├── test_y_shot.py         # テスト
├── templates/             # パターンテンプレート (CSV)
│   └── 入力チェック_基本.csv
├── assets/                # アイコン素材
│   ├── shot_icon.ico/png/svg
│   └── diff_icon.ico/png/svg
├── docs/                  # ドキュメント
│   ├── setup_guide.md     # 本手順書
│   ├── y-shot_manual.md   # 操作マニュアル
│   ├── partner_sample.yshot.json   # サンプルプロジェクト
│   └── wine_search_sample.yshot.json
├── .gitignore
└── README.md
```

### 自動生成ファイル（Git 管理外）

| ファイル | 内容 |
|---------|------|
| `y_shot_config.ini` | 設定（Basic 認証情報等） |
| `y_shot_tests.json` | テストケース定義 |
| `y_shot_patterns.json` | パターンセット |
| `y_shot_selectors.json` | セレクタバンク |
| `y_shot_pages.json` | ページ定義 |
| `screenshots/` | スクリーンショット出力先 |
| `log/` | 実行ログ |
| `build/` / `dist/` | ビルド中間・成果物 |

---

## 6. サンプルプロジェクトの読み込み

`docs/` フォルダにサンプルの `.yshot.json` ファイルが含まれています。

1. y-shot を起動
2. AppBar の **↓ アイコン**（インポート）をクリック
3. `.yshot.json` ファイルを選択

---

## 7. トラブルシューティング

| 症状 | 対処 |
|------|------|
| `py` コマンドが見つからない | Python の PATH 設定を確認。`python` でも可 |
| Chrome 起動時にエラー | Chrome を最新版に更新。社内プロキシがある場合はネットワーク設定を確認 |
| `flet` のインストールに失敗 | `pip install --upgrade pip` を実行してから再試行 |
| ビルドした exe が起動しない | ウイルス対策ソフトによるブロックを確認。除外設定を追加 |
| `ModuleNotFoundError` | `pip install -r requirements.txt` を再実行 |
