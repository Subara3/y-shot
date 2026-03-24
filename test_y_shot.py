"""
y-shot テストスクリプト
  - test_form.html を使って要素取得とスクショ撮影をテスト
  - 使い方: py test_y_shot.py
"""

import os
import sys
import json
import time
import tempfile

# ---------------------------------------------------------------------------
# テスト1: ロジック部分（ブラウザ不要）
# ---------------------------------------------------------------------------

def test_logic():
    print("=== テスト1: ロジック部分 ===")
    from y_shot import load_csv, save_csv, load_steps, save_steps, step_display

    # CSV round-trip
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
        tmp_csv = f.name
    patterns = [
        {"label": "test1", "value": "hello"},
        {"label": "test2", "value": "あ" * 100},
    ]
    save_csv(tmp_csv, patterns)
    loaded = load_csv(tmp_csv)
    assert len(loaded) == 2, f"CSV件数が不一致: {len(loaded)}"
    assert loaded[0]["label"] == "test1"
    assert loaded[1]["value"] == "あ" * 100
    os.unlink(tmp_csv)
    print("  [OK] CSV保存/読込")

    # Steps round-trip
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp_json = f.name
    steps = [
        {"type": "入力", "selector": "#name", "value": "{パターン}"},
        {"type": "クリック", "selector": "#btn"},
        {"type": "待機", "seconds": "2.0"},
        {"type": "スクショ", "mode": "fullpage"},
    ]
    save_steps(steps, tmp_json)
    loaded_steps = load_steps(tmp_json)
    assert len(loaded_steps) == 4
    os.unlink(tmp_json)
    print("  [OK] ステップ保存/読込")

    # step_display
    assert "入力" in step_display(steps[0])
    assert "クリック" in step_display(steps[1])
    assert "2.0" in step_display(steps[2])
    assert "fullpage" in step_display(steps[3])
    print("  [OK] ステップ表示")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト2: 要素取得（ブラウザ必要）
# ---------------------------------------------------------------------------

def test_element_collection():
    print("=== テスト2: 要素取得 (test_form.html) ===")
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        print("  [SKIP] selenium がインストールされていません")
        return False

    from y_shot import collect_elements_python

    opts = Options()
    opts.add_argument("--headless=new")
    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        html_path = os.path.join(os.path.dirname(__file__), "test_form.html")
        html_path = os.path.abspath(html_path)
        driver.get(f"file:///{html_path}")
        time.sleep(1)

        elements = collect_elements_python(driver)
        print(f"  検出要素数: {len(elements)}")

        # 検証
        assert len(elements) > 0, "要素が0個"
        tags = [e["tag"] for e in elements]
        assert "input" in tags, "input要素が見つからない"
        assert "textarea" in tags, "textarea要素が見つからない"
        assert "button" in tags, "button要素が見つからない"
        assert "select" in tags, "select要素が見つからない"

        # セレクタの検証
        selectors = [e["selector"] for e in elements]
        assert "#username" in selectors, "#username セレクタがない"
        assert "#email" in selectors, "#email セレクタがない"
        assert "#message" in selectors, "#message セレクタがない"
        assert "#submit-btn" in selectors, "#submit-btn セレクタがない"

        # 各要素の詳細表示
        for e in elements:
            print(f"    {e['tag']:10} {e['type']:10} {e['selector']:30} hint={e.get('placeholder','')[:20]}")

        print("  [OK] 要素取得成功\n")
        return True

    except Exception as e:
        print(f"  [FAIL] {e}\n")
        return False
    finally:
        if driver:
            driver.quit()


# ---------------------------------------------------------------------------
# テスト3: E2Eテスト（ステップ実行＋スクショ）
# ---------------------------------------------------------------------------

def test_e2e():
    print("=== テスト3: E2E実行 (test_form.html) ===")
    try:
        from selenium import webdriver
    except ImportError:
        print("  [SKIP] selenium がインストールされていません")
        return

    from y_shot import run_selenium_job

    html_path = os.path.join(os.path.dirname(__file__), "test_form.html")
    html_path = os.path.abspath(html_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "url": f"file:///{html_path}",
            "output_dir": tmpdir,
        }
        steps = [
            {"type": "入力", "selector": "#username", "value": "テスト太郎"},
            {"type": "入力", "selector": "#message", "value": "{パターン}"},
            {"type": "クリック", "selector": "#submit-btn"},
            {"type": "待機", "seconds": "1.0"},
            {"type": "スクショ", "mode": "fullpage"},
        ]
        patterns = [
            {"label": "short", "value": "こんにちは"},
            {"label": "long", "value": "あ" * 500},
        ]

        logs = []
        done_flag = [False]

        def log_cb(msg):
            logs.append(msg)
            print(f"    {msg}")

        def done_cb():
            done_flag[0] = True

        # 同期的に実行（テスト用）
        run_selenium_job(config, steps, patterns, log_cb, done_cb)

        # 検証
        assert done_flag[0], "done_callbackが呼ばれていない"
        screenshots = [f for f in os.listdir(tmpdir) if f.endswith(".png")]
        print(f"  スクショ生成数: {len(screenshots)}")
        for ss in sorted(screenshots):
            size = os.path.getsize(os.path.join(tmpdir, ss))
            print(f"    {ss} ({size:,} bytes)")

        assert len(screenshots) >= 2, f"スクショが2枚以上必要だが {len(screenshots)} 枚"
        assert any("short" in s for s in screenshots), "short パターンのスクショがない"
        assert any("long" in s for s in screenshots), "long パターンのスクショがない"

        # ログにエラーがないことを確認
        error_logs = [l for l in logs if "[ERROR]" in l]
        assert len(error_logs) == 0, f"エラーが発生: {error_logs}"

        print("  [OK] E2Eテスト成功\n")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("y-shot テスト開始\n")
    test_logic()
    ok = test_element_collection()
    if ok:
        test_e2e()
    print("テスト完了")
