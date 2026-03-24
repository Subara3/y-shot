# y-shot

Webページのスクリーンショットを入力パターンごとに自動撮影するツール。

## セットアップ

```bash
pip install -r requirements.txt
```

Chrome と ChromeDriver が必要です（Selenium 4.6+ なら ChromeDriver は自動ダウンロードされます）。

## 使い方

```bash
python y_shot.py
```

1. 「設定」欄に対象URL・CSSセレクタ等を入力
2. 「入力パターン」に追加ボタンでパターンを登録（CSV読込も可）
3. 「実行」で自動スクショ開始

## exe化

```bash
pip install pyinstaller
build.bat
```

`dist/y-shot.exe` が生成されます。
