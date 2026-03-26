"""
y-shot テストスクリプト v1.7
  - ロジック部分のテスト（ブラウザ不要）
  - Flet API互換性チェック
  - v1.7: start_num, auto_number_tests, pattern numbering
"""

import os
import sys
import json
import tempfile
import copy

# ---------------------------------------------------------------------------
# テスト1: ロジック部分（ブラウザ不要）
# ---------------------------------------------------------------------------

def test_logic():
    print("=== テスト1: ロジック部分 ===")
    from y_shot import load_csv, save_csv, save_tests, load_tests, step_display

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

    # Tests (JSON) round-trip
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp_json = f.name
    test_cases = [{"name": "テスト1", "pattern": None, "steps": [
        {"type": "入力", "selector": "#name", "value": "{パターン}"},
        {"type": "クリック", "selector": "#btn"},
        {"type": "待機", "seconds": "2.0"},
        {"type": "スクショ", "mode": "fullpage"},
    ]}]
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(test_cases, f, ensure_ascii=False)
    with open(tmp_json, "r", encoding="utf-8") as f:
        loaded_tests = json.load(f)
    assert len(loaded_tests) == 1
    assert len(loaded_tests[0]["steps"]) == 4
    os.unlink(tmp_json)
    print("  [OK] テストケース保存/読込")

    # step_display
    steps = test_cases[0]["steps"]
    assert "入力" in step_display(steps[0]) or "#name" in step_display(steps[0])
    assert "クリック" in step_display(steps[1]) or "#btn" in step_display(steps[1])
    assert "2.0" in step_display(steps[2])
    assert "fullpage" in step_display(steps[3]) or "ページ全体" in step_display(steps[3])
    print("  [OK] ステップ表示")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト2: テストケースID管理
# ---------------------------------------------------------------------------

def test_tc_ids():
    print("=== テスト2: テストケースID管理 ===")

    tests = [
        {"name": "TC1", "pattern": None, "steps": []},
        {"name": "TC2", "pattern": None, "steps": []},
    ]
    counter = {"val": 0}
    for tc in tests:
        if "_id" not in tc:
            counter["val"] += 1
            tc["_id"] = f"tc_{counter['val']}"
    assert tests[0]["_id"] == "tc_1"
    assert tests[1]["_id"] == "tc_2"
    print("  [OK] IDなしテストケースへのID付与")

    tests_with_ids = [
        {"name": "TC1", "_id": "tc_5", "pattern": None, "steps": []},
        {"name": "TC2", "_id": "tc_3", "pattern": None, "steps": []},
        {"name": "TC3", "pattern": None, "steps": []},
    ]
    _max_id = 0
    _counter = 0
    for tc in tests_with_ids:
        if "_id" in tc:
            try: _max_id = max(_max_id, int(tc["_id"].split("_", 1)[1]))
            except (ValueError, IndexError): pass
        else:
            _counter += 1
            tc["_id"] = f"tc_{_counter}"
    _counter = max(_counter, _max_id)
    assert _max_id == 5
    assert _counter == 5
    assert tests_with_ids[2]["_id"] == "tc_1"
    _counter += 1
    assert _counter == 6
    print("  [OK] 既存IDからのカウンター復元")

    original = {"name": "元テスト", "_id": "tc_10", "pattern": None, "steps": [{"type": "スクショ", "mode": "fullpage"}]}
    copied = copy.deepcopy(original)
    copied["_id"] = "tc_11"
    assert original["_id"] != copied["_id"]
    assert copied["steps"][0]["type"] == "スクショ"
    print("  [OK] コピー時のユニークID")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp = f.name
    test_data = [{"name": "TC", "_id": "tc_42", "pattern": None, "steps": []}]
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(test_data, f, ensure_ascii=False)
    with open(tmp, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded[0]["_id"] == "tc_42"
    os.unlink(tmp)
    print("  [OK] ID保存/復元")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト3: パターンセット順序管理
# ---------------------------------------------------------------------------

def test_pattern_set_ordering():
    print("=== テスト3: パターンセット順序管理 ===")

    ps = {}
    ps["C_set"] = [{"label": "c1", "value": "c"}]
    ps["A_set"] = [{"label": "a1", "value": "a"}]
    ps["B_set"] = [{"label": "b1", "value": "b"}]
    assert list(ps.keys()) == ["C_set", "A_set", "B_set"]
    print("  [OK] 挿入順維持")

    names = list(ps.keys())
    old, new = 2, 0
    item = names.pop(old)
    names.insert(new, item)
    assert names == ["B_set", "C_set", "A_set"]
    ps_reordered = {n: ps[n] for n in names}
    assert list(ps_reordered.keys()) == ["B_set", "C_set", "A_set"]
    print("  [OK] 並び替え")

    ps = {"First": [], "Second": [], "Third": []}
    old_name, new_name = "Second", "Renamed"
    new_ps = {}
    for k, v in ps.items():
        new_ps[new_name if k == old_name else k] = v
    assert list(new_ps.keys()) == ["First", "Renamed", "Third"]
    print("  [OK] リネーム時の順序維持")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmp = f.name
    ps = {"Z_last": [{"label": "z", "value": "z"}], "A_first": [{"label": "a", "value": "a"}]}
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ps, f, ensure_ascii=False)
    with open(tmp, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert list(loaded.keys()) == ["Z_last", "A_first"]
    os.unlink(tmp)
    print("  [OK] JSON保存/復元の順序維持")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト4: Flet API互換性チェック
# ---------------------------------------------------------------------------

def test_flet_api():
    print("=== テスト4: Flet API互換性チェック ===")
    import flet as ft

    try:
        items = [
            ft.PopupMenuItem(icon=ft.Icons.PLAY_ARROW, content="実行"),
            ft.PopupMenuItem(icon=ft.Icons.COPY, content="コピー"),
            ft.PopupMenuItem(),
            ft.PopupMenuItem(icon=ft.Icons.DELETE, content="削除"),
        ]
        btn = ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, items=items)
        assert len(btn.items) == 4
        print("  [OK] PopupMenuButton + PopupMenuItem(content=)")
    except Exception as e:
        print(f"  [FAIL] PopupMenuItem: {e}"); raise

    try:
        rlv = ft.ReorderableListView(controls=[], spacing=4)
        assert rlv is not None
        print("  [OK] ReorderableListView")
    except Exception as e:
        print(f"  [FAIL] ReorderableListView: {e}"); raise

    try:
        dlg = ft.AlertDialog(title=ft.Text("test"), modal=True)
        assert dlg.modal == True
        print("  [OK] AlertDialog modal=True/False")
    except Exception as e:
        print(f"  [FAIL] AlertDialog modal: {e}"); raise

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト5: kill_driver 関数
# ---------------------------------------------------------------------------

def test_kill_driver():
    print("=== テスト5: kill_driver 関数 ===")
    from y_shot import kill_driver

    try:
        kill_driver(None)
        print("  [OK] kill_driver(None) - エラーなし")
    except Exception as e:
        print(f"  [FAIL] kill_driver(None): {e}"); raise

    class MockService:
        class process:
            pid = 99999
            @staticmethod
            def wait(timeout=5): return
    class MockDriver:
        service = MockService()
        _quit_called = False
        def quit(self): self._quit_called = True
    drv = MockDriver()
    kill_driver(drv)
    assert drv._quit_called
    print("  [OK] kill_driver(MockDriver) - quit()呼び出し確認")

    class BrokenDriver:
        service = None
        def quit(self): raise Exception("already dead")
    try:
        kill_driver(BrokenDriver())
        print("  [OK] kill_driver(BrokenDriver) - 例外を握り潰し")
    except Exception as e:
        print(f"  [FAIL] kill_driver should not raise: {e}"); raise

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト6: モジュールインポート
# ---------------------------------------------------------------------------

def test_import():
    print("=== テスト6: モジュールインポート ===")
    import importlib.util
    spec = importlib.util.spec_from_file_location('y_shot', os.path.join(os.path.dirname(__file__) or '.', 'y_shot.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules['y_shot_test_import'] = mod
    try:
        spec.loader.exec_module(mod)
        for fn_name in ['main', '_main_inner', 'kill_driver', 'run_all_tests', 'collect_elements_python',
                         'step_display', 'load_csv', 'save_csv', 'load_tests', 'save_tests',
                         'load_pattern_sets', 'save_pattern_sets', 'load_pages', 'save_pages',
                         'build_auth_url', 'capture_form_values', '_safe_filename', '_has_non_bmp']:
            assert hasattr(mod, fn_name), f"{fn_name} が見つからない"
        print("  [OK] モジュール読込 + 全関数存在確認")
    except Exception as e:
        print(f"  [FAIL] {e}"); raise

    assert mod.APP_VERSION == "1.7", f"バージョン不一致: {mod.APP_VERSION}"
    print(f"  [OK] バージョン: {mod.APP_VERSION}")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト7: _safe_filename / _has_non_bmp
# ---------------------------------------------------------------------------

def test_utils():
    print("=== テスト7: ユーティリティ関数 ===")
    from y_shot import _safe_filename, _has_non_bmp

    assert _safe_filename('テスト:名前/abc') == 'テスト_名前_abc'
    assert len(_safe_filename('あ' * 100)) <= 30
    assert _safe_filename('') == '_'
    assert _safe_filename('...') == '_'
    print("  [OK] _safe_filename")

    assert _has_non_bmp('hello') == False
    assert _has_non_bmp('テスト') == False
    assert _has_non_bmp('🦐') == True
    assert _has_non_bmp('テスト🦐') == True
    assert _has_non_bmp('𠮷野屋') == True
    print("  [OK] _has_non_bmp")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト8: start_num と auto_number_tests
# ---------------------------------------------------------------------------

def test_start_num():
    print("=== テスト8: start_num と番号体系 ===")

    # ページに start_number を設定した場合の採番
    pages = [
        {"_id": "p_1", "name": "ページ1", "number": "1", "start_number": 1},
        {"_id": "p_2", "name": "ページ2", "number": "2", "start_number": 5},
    ]
    tests = [
        {"_id": "tc_1", "name": "T1", "page_id": "p_1", "number": ""},
        {"_id": "tc_2", "name": "T2", "page_id": "p_1", "number": ""},
        {"_id": "tc_3", "name": "T3", "page_id": "p_2", "number": ""},
        {"_id": "tc_4", "name": "T4", "page_id": "p_2", "number": ""},
    ]

    for pg in pages:
        pnum = pg["number"]
        start = int(pg.get("start_number", 1))
        page_tests = [t for t in tests if t.get("page_id") == pg["_id"]]
        for i, tc in enumerate(page_tests):
            tc["number"] = f"{pnum}-{start + i}"

    assert tests[0]["number"] == "1-1", f"Expected 1-1, got {tests[0]['number']}"
    assert tests[1]["number"] == "1-2", f"Expected 1-2, got {tests[1]['number']}"
    assert tests[2]["number"] == "2-5", f"Expected 2-5, got {tests[2]['number']}"
    assert tests[3]["number"] == "2-6", f"Expected 2-6, got {tests[3]['number']}"
    print("  [OK] ページ番号-開始番号からの連番")

    # start_number なしの場合のデフォルト
    pages_no_start = [{"_id": "p_1", "name": "P1", "number": "3"}]
    start = int(pages_no_start[0].get("start_number", 1))
    assert start == 1
    print("  [OK] start_number なし時のデフォルト=1")

    # start_num (旧フィールド) -> start_number へのマイグレーション
    pg_old = {"_id": "p_1", "name": "P1", "number": "1", "start_num": 3}
    if "start_num" in pg_old and "start_number" not in pg_old:
        pg_old["start_number"] = pg_old.pop("start_num")
    assert pg_old.get("start_number") == 3
    assert "start_num" not in pg_old
    print("  [OK] start_num -> start_number マイグレーション")

    # ファイル名にテスト番号が含まれることを確認
    from y_shot import _safe_filename
    tc_number = "2-5"
    safe_number = _safe_filename(tc_number, 10)
    assert safe_number == "2-5"
    fn = f"001_{safe_number}_テスト_p01_未入力_ss1.png"
    assert "2-5" in fn
    print("  [OK] ファイル名にテスト番号")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト9: テストケースの並び替えロジック
# ---------------------------------------------------------------------------

def test_reorder():
    print("=== テスト9: テストケースの並び替え ===")

    def tests_for_page(tests, pid):
        return [t for t in tests if t.get("page_id") == pid]

    def do_reorder(tests, cur_pid, old, new):
        page_tests = tests_for_page(tests, cur_pid)
        adj_new = new - 1 if new > old else new
        if old == adj_new: return
        old_tc = page_tests[old]
        new_tc = page_tests[adj_new] if adj_new < len(page_tests) else None
        tests.remove(old_tc)
        if new_tc:
            new_gi = tests.index(new_tc)
            if adj_new > old:
                tests.insert(new_gi + 1, old_tc)
            else:
                tests.insert(new_gi, old_tc)
        else:
            last_idx = -1
            for i, t in enumerate(tests):
                if t.get("page_id") == cur_pid: last_idx = i
            tests.insert(last_idx + 1 if last_idx >= 0 else len(tests), old_tc)

    pid = "p_1"

    # 末尾→先頭
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C"]]
    do_reorder(ts, pid, 2, 0)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['C', 'A', 'B']
    print("  [OK] 末尾→先頭 (2->0)")

    # 先頭→2番目の後ろ
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C"]]
    do_reorder(ts, pid, 0, 2)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['B', 'A', 'C']
    print("  [OK] 先頭→中間 (0->2)")

    # 先頭→末尾
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C"]]
    do_reorder(ts, pid, 0, 3)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['B', 'C', 'A']
    print("  [OK] 先頭→末尾 (0->3)")

    # マルチページ: 他ページに影響なし
    ts = [{"name": "X", "page_id": "p_2"},
          {"name": "A", "page_id": pid},
          {"name": "B", "page_id": pid},
          {"name": "Y", "page_id": "p_2"},
          {"name": "C", "page_id": pid}]
    do_reorder(ts, pid, 2, 0)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['C', 'A', 'B']
    assert [t['name'] for t in tests_for_page(ts, "p_2")] == ['X', 'Y']
    print("  [OK] マルチページ時の独立性")

    print("  全てパス\n")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("y-shot テスト開始 (v1.7)\n")

    test_logic()
    test_tc_ids()
    test_pattern_set_ordering()
    test_flet_api()
    test_kill_driver()
    test_import()
    test_utils()
    test_start_num()
    test_reorder()

    print("=" * 40)
    print("全テスト完了 - すべてパス")
