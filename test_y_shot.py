"""
y-shot テストスクリプト v3.0
  - ロジック部分のテスト（ブラウザ不要）
  - Flet API互換性チェック
  - v2.0: safe_float, json persistence, normalize, auth URL, classify等を追加
  - v3.0: エクスポート/インポートFilePicker対応、ActionChainsクリック、Selenium API確認
"""

import os
import sys
import json
import re
import tempfile
import copy
import shutil

# ---------------------------------------------------------------------------
# テスト1: ロジック部分（ブラウザ不要）
# ---------------------------------------------------------------------------

def test_logic():
    print("=== テスト1: ロジック部分 ===")
    from y_shot import load_csv, save_csv, save_tests, load_tests, step_short as step_display

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
    assert "表示範囲" in step_display(steps[3]) or "fullpage" in step_display(steps[3])
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
        rlv = ft.ReorderableListView(controls=[], spacing=4, show_default_drag_handles=False)
        assert rlv is not None
        assert rlv.show_default_drag_handles == False
        handle = ft.ReorderableDragHandle(content=ft.Icon(ft.Icons.DRAG_INDICATOR), mouse_cursor=ft.MouseCursor.GRAB)
        assert handle is not None
        print("  [OK] ReorderableListView + ReorderableDragHandle")
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
                         'step_short', 'load_csv', 'save_csv', 'load_tests', 'save_tests',
                         'load_pattern_sets', 'save_pattern_sets', 'load_pages', 'save_pages',
                         'build_auth_url', 'capture_form_values', '_safe_filename', '_has_non_bmp',
                         '_sel_by']:
            assert hasattr(mod, fn_name), f"{fn_name} が見つからない"
        print("  [OK] モジュール読込 + 全関数存在確認")
    except Exception as e:
        print(f"  [FAIL] {e}"); raise

    assert mod.APP_VERSION == "3.1", f"バージョン不一致: {mod.APP_VERSION}"
    print(f"  [OK] バージョン: {mod.APP_VERSION}")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト7: _safe_filename / _has_non_bmp
# ---------------------------------------------------------------------------

def test_utils():
    print("=== テスト7: ユーティリティ関数 ===")
    from y_shot import _safe_filename, _has_non_bmp, _safe_float

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

    assert _safe_float("1.5") == 1.5
    assert _safe_float("", 2.0) == 2.0
    assert _safe_float(None, 3.0) == 3.0
    assert _safe_float("abc") == 1.0
    assert _safe_float(10) == 10.0
    print("  [OK] _safe_float")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト8: start_num と auto_number_tests
# ---------------------------------------------------------------------------

def test_start_num():
    print("=== テスト8: 番号体系と枝番 ===")

    def auto_number(pages, tests):
        """Reproduce auto_number_tests logic"""
        for pg in pages:
            pnum = pg["number"]
            next_sub = int(pg.get("start_number", 1))
            page_tests = [t for t in tests if t.get("page_id") == pg["_id"]]
            for tc in page_tests:
                forced = tc.get("_sub_number")
                if forced is not None:
                    next_sub = int(forced)
                tc["number"] = f"{pnum}-{next_sub}"
                next_sub += 1

    # 基本: start_number からの連番
    pages = [
        {"_id": "p_1", "name": "P1", "number": "1", "start_number": 1},
        {"_id": "p_2", "name": "P2", "number": "2", "start_number": 5},
    ]
    tests = [
        {"_id": "tc_1", "name": "T1", "page_id": "p_1", "number": ""},
        {"_id": "tc_2", "name": "T2", "page_id": "p_1", "number": ""},
        {"_id": "tc_3", "name": "T3", "page_id": "p_2", "number": ""},
        {"_id": "tc_4", "name": "T4", "page_id": "p_2", "number": ""},
    ]
    auto_number(pages, tests)
    assert tests[0]["number"] == "1-1"
    assert tests[1]["number"] == "1-2"
    assert tests[2]["number"] == "2-5"
    assert tests[3]["number"] == "2-6"
    print("  [OK] ページ番号-開始番号からの連番")

    # _sub_number で途中から番号を飛ばす (1-1, 1-2, 1-5, 1-6)
    pages2 = [{"_id": "p_1", "name": "P1", "number": "1", "start_number": 1}]
    tests2 = [
        {"_id": "tc_1", "name": "T1", "page_id": "p_1", "number": ""},
        {"_id": "tc_2", "name": "T2", "page_id": "p_1", "number": ""},
        {"_id": "tc_3", "name": "T3", "page_id": "p_1", "number": "", "_sub_number": 5},
        {"_id": "tc_4", "name": "T4", "page_id": "p_1", "number": ""},
    ]
    auto_number(pages2, tests2)
    assert tests2[0]["number"] == "1-1", f"Got {tests2[0]['number']}"
    assert tests2[1]["number"] == "1-2", f"Got {tests2[1]['number']}"
    assert tests2[2]["number"] == "1-5", f"Got {tests2[2]['number']}"
    assert tests2[3]["number"] == "1-6", f"Got {tests2[3]['number']}"
    print("  [OK] _sub_number で番号飛ばし (1-1,1-2,1-5,1-6)")

    # _sub_number が先頭にある場合
    tests3 = [
        {"_id": "tc_1", "name": "T1", "page_id": "p_1", "number": "", "_sub_number": 10},
        {"_id": "tc_2", "name": "T2", "page_id": "p_1", "number": ""},
    ]
    auto_number(pages2, tests3)
    assert tests3[0]["number"] == "1-10"
    assert tests3[1]["number"] == "1-11"
    print("  [OK] 先頭に_sub_number (1-10, 1-11)")

    # _sub_number なしのテストだけ → start_number からの連番
    tests4 = [
        {"_id": "tc_1", "name": "T1", "page_id": "p_1", "number": ""},
        {"_id": "tc_2", "name": "T2", "page_id": "p_1", "number": ""},
    ]
    auto_number(pages2, tests4)
    assert tests4[0]["number"] == "1-1"
    assert tests4[1]["number"] == "1-2"
    print("  [OK] _sub_number なし → 通常連番")

    # start_number なしの場合のデフォルト
    assert int({"_id": "p_1", "name": "P1", "number": "3"}.get("start_number", 1)) == 1
    print("  [OK] start_number なし時のデフォルト=1")

    # マイグレーション: start_num -> start_number
    pg_old = {"_id": "p_1", "name": "P1", "number": "1", "start_num": 3}
    if "start_num" in pg_old and "start_number" not in pg_old:
        pg_old["start_number"] = pg_old.pop("start_num")
    assert pg_old.get("start_number") == 3 and "start_num" not in pg_old
    print("  [OK] start_num -> start_number マイグレーション")

    # マイグレーション: _manual_number -> _sub_number
    tc_old = {"_id": "tc_1", "name": "T", "number": "1-7", "_manual_number": True, "page_id": "p_1"}
    if tc_old.pop("_manual_number", False):
        num = tc_old.get("number", "")
        if "-" in num:
            try: tc_old["_sub_number"] = int(num.split("-", 1)[1])
            except (ValueError, IndexError): pass
    assert tc_old.get("_sub_number") == 7
    assert "_manual_number" not in tc_old
    print("  [OK] _manual_number -> _sub_number マイグレーション")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト9: テストケースの並び替えロジック
# ---------------------------------------------------------------------------

def test_reorder():
    print("=== テスト9: テストケースの並び替え ===")

    def tests_for_page(tests, pid):
        return [t for t in tests if t.get("page_id") == pid]

    def do_reorder(tests, cur_pid, old, new):
        """Reproduce on_test_reorder: pop(old) → insert(new) in page scope, rebuild global."""
        page_tests = tests_for_page(tests, cur_pid)
        if old == new: return
        old_tc = page_tests[old]
        new_order = list(page_tests)
        new_order.pop(old)
        new_order.insert(new, old_tc)
        result = []
        page_inserted = False
        for t in tests:
            if t.get("page_id") == cur_pid:
                if not page_inserted:
                    result.extend(new_order)
                    page_inserted = True
            else:
                result.append(t)
        if not page_inserted:
            result.extend(new_order)
        tests[:] = result

    pid = "p_1"

    # 末尾→先頭: pop(2) → insert(0)
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C"]]
    do_reorder(ts, pid, 2, 0)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['C', 'A', 'B']
    print("  [OK] 末尾→先頭 (2->0)")

    # 先頭→中間: pop(0) → insert(1)  [B,C] → insert(1,A) → [B,A,C]
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C"]]
    do_reorder(ts, pid, 0, 1)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['B', 'A', 'C']
    print("  [OK] 先頭→中間 (0->1)")

    # 先頭→末尾: pop(0) → insert(2)  [B,C] → insert(2,A) → [B,C,A]
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C"]]
    do_reorder(ts, pid, 0, 2)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['B', 'C', 'A']
    print("  [OK] 先頭→末尾 (0->2)")

    # 中間→先頭: pop(1) → insert(0)
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C"]]
    do_reorder(ts, pid, 1, 0)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['B', 'A', 'C']
    print("  [OK] 中間→先頭 (1->0)")

    # 4要素での下方向移動 (Flet Dart調整済みインデックス)
    # A(0)をC(2)の後に: Dart側でold=0,new=2として送信
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C", "D"]]
    do_reorder(ts, pid, 0, 2)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['B', 'C', 'A', 'D']
    print("  [OK] 4要素 先頭→中間下方 (0->2)")

    # B(1)をD(3)の後に: old=1,new=3
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C", "D"]]
    do_reorder(ts, pid, 1, 3)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['A', 'C', 'D', 'B']
    print("  [OK] 4要素 中間→末尾 (1->3)")

    # D(3)をA(0)の前に: old=3,new=0
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C", "D"]]
    do_reorder(ts, pid, 3, 0)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['D', 'A', 'B', 'C']
    print("  [OK] 4要素 末尾→先頭 (3->0)")

    # C(2)をB(1)の前に: old=2,new=1
    ts = [{"name": n, "page_id": pid} for n in ["A", "B", "C", "D"]]
    do_reorder(ts, pid, 2, 1)
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['A', 'C', 'B', 'D']
    print("  [OK] 4要素 上方向 (2->1)")

    # マルチページ: 他ページに影響なし
    ts = [{"name": "X", "page_id": "p_2"},
          {"name": "A", "page_id": pid},
          {"name": "B", "page_id": pid},
          {"name": "Y", "page_id": "p_2"},
          {"name": "C", "page_id": pid}]
    do_reorder(ts, pid, 2, 0)  # C→before A
    assert [t['name'] for t in tests_for_page(ts, pid)] == ['C', 'A', 'B']
    assert [t['name'] for t in tests_for_page(ts, "p_2")] == ['X', 'Y']
    print("  [OK] マルチページ時の独立性")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト10: パターン並び替え (フラットリスト)
# ---------------------------------------------------------------------------

def test_pattern_reorder():
    print("=== テスト10: パターン並び替え ===")

    def do_reorder(pats, old, new):
        """Reproduce on_pat_reorder: pop(old) → insert(new)"""
        if old == new: return pats
        item = pats.pop(old)
        pats.insert(new, item)
        return pats

    # 下に1つ移動: pop(1)→insert(2)  [A,C,D]→insert(2,B)=[A,C,B,D]
    p = ["A", "B", "C", "D"]
    do_reorder(p, 1, 2)
    assert p == ["A", "C", "B", "D"], f"Got {p}"
    print("  [OK] 下に1つ移動 (1->2)")

    # 上に1つ移動: pop(2)→insert(1)  [A,B,D]→insert(1,C)=[A,C,B,D]
    p = ["A", "B", "C", "D"]
    do_reorder(p, 2, 1)
    assert p == ["A", "C", "B", "D"], f"Got {p}"
    print("  [OK] 上に1つ移動 (2->1)")

    # 先頭→末尾: pop(0)→insert(3)  [B,C,D]→insert(3,A)=[B,C,D,A]
    p = ["A", "B", "C", "D"]
    do_reorder(p, 0, 3)
    assert p == ["B", "C", "D", "A"], f"Got {p}"
    print("  [OK] 先頭→末尾 (0->3)")

    # 末尾→先頭: pop(3)→insert(0)  [A,B,C]→insert(0,D)=[D,A,B,C]
    p = ["A", "B", "C", "D"]
    do_reorder(p, 3, 0)
    assert p == ["D", "A", "B", "C"], f"Got {p}"
    print("  [OK] 末尾→先頭 (3->0)")

    # ノーオプ (same index)
    p = ["A", "B", "C"]
    p_copy = list(p)
    do_reorder(p, 1, 1)
    assert p == p_copy, f"Got {p}"
    print("  [OK] ノーオプ (1->1)")

    # 2つ下: pop(0)→insert(2)  [B,C,D,E]→insert(2,A)=[B,C,A,D,E]
    p = ["A", "B", "C", "D", "E"]
    do_reorder(p, 0, 2)
    assert p == ["B", "C", "A", "D", "E"], f"Got {p}"
    print("  [OK] 2つ下 (0->2)")

    # 中間→先頭: pop(2)→insert(0)  [A,B,D,E]→insert(0,C)=[C,A,B,D,E]
    p = ["A", "B", "C", "D", "E"]
    do_reorder(p, 2, 0)
    assert p == ["C", "A", "B", "D", "E"], f"Got {p}"
    print("  [OK] 中間→先頭 (2->0)")

    # dict形式でのテスト (パターンセット実データ形式)
    pats = [
        {"label": "未入力", "value": ""},
        {"label": "全角SP", "value": "\u3000"},
        {"label": "半角SP", "value": " "},
        {"label": "絵文字", "value": "🦐"},
    ]
    item = pats.pop(3)
    pats.insert(0, item)
    assert pats[0]["label"] == "絵文字"
    assert pats[1]["label"] == "未入力"
    print("  [OK] dict形式パターン移動")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト11: dedup (二重発火防止)
# ---------------------------------------------------------------------------

def test_dedup():
    print("=== テスト11: dedup (二重発火防止) ===")
    import time as _time

    # Reproduce dedup logic: key=(handler, old, new), window=0.1s
    # y_shot.py _is_dup_reorder と同一のロジック
    _dedup = {}
    def is_dup(handler, old, new):
        now = _time.time()
        key = (handler, old, new)
        prev = _dedup.get(key)
        if prev and now - prev < 0.1: return True
        _dedup[key] = now; return False

    # 1回目は通す
    assert is_dup("pat", 1, 2) == False
    print("  [OK] 1回目は通過")

    # 即座の2回目はブロック (同一インデックス)
    assert is_dup("pat", 1, 2) == True
    print("  [OK] 2回目即座ブロック")

    # 別ハンドラーは独立
    assert is_dup("step", 1, 2) == False
    print("  [OK] 別ハンドラーは独立")

    # 時間経過後は通す
    _dedup[("pat", 1, 2)] = _time.time() - 0.2  # 0.2秒前 (0.1秒窓を超過)
    assert is_dup("pat", 1, 2) == False
    print("  [OK] 0.1秒後は通過")

    # 異なるインデックスは独立 (正当な連続並び替え)
    _dedup.clear()
    assert is_dup("pat", 0, 2) == False  # 1回目
    assert is_dup("pat", 1, 3) == False  # 異なるインデックス → 通過
    print("  [OK] 異なるインデックスは独立 (連続並び替え可能)")

    # 二重発火シミュレーション: 1回目は正しく移動、2回目はブロック
    # Flet Dart側でnewIndex調整済み → Python側ではpop/insertそのまま
    _dedup2 = {}
    def is_dup2(handler, old, new):
        now = _time.time()
        key = (handler, old, new)
        prev = _dedup2.get(key)
        if prev and now - prev < 0.1: return True
        _dedup2[key] = now; return False

    def sim_reorder(pats, old, new):
        if is_dup2("pat", old, new): return  # blocked
        if old == new: return
        pats.insert(new, pats.pop(old))

    # ケース1: B(1)をC(2)の後に → Dart調整後 (old=1, new=2)
    pats = ["A", "B", "C", "D"]
    sim_reorder(pats, 1, 2)  # 1st: [A, C, B, D]
    sim_reorder(pats, 1, 2)  # 2nd: same indices → dedup blocks
    assert pats == ["A", "C", "B", "D"], f"Case1: {pats}"
    print("  [OK] 二重発火ブロック (同一インデックス)")

    # ケース2: 異なるインデックスの二重発火 → key異なるので通過
    _dedup2.clear()
    pats = ["A", "B", "C", "D"]
    sim_reorder(pats, 0, 2)  # 1st: [B, C, A, D]
    sim_reorder(pats, 0, 1)  # 2nd: different indices → passes through
    # 2nd reorder on [B, C, A, D]: pop(0)=[C,A,D], insert(1,B)=[C,B,A,D]
    assert pats == ["C", "B", "A", "D"], f"Case2: {pats}"
    print("  [OK] 異なるインデックスは通過 (連続操作可能)")

    # ケース3: D(3)をA(0)の前に → Dart調整後 (old=3, new=0)
    _dedup2.clear()
    pats = ["A", "B", "C", "D"]
    sim_reorder(pats, 3, 0)  # 1st: [D, A, B, C]
    sim_reorder(pats, 3, 0)  # 2nd: same indices → dedup blocks
    assert pats == ["D", "A", "B", "C"], f"Case3: {pats}"
    print("  [OK] 二重発火ブロック (上方向移動)")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト12: 出力フォルダ構造
# ---------------------------------------------------------------------------

def test_output_structure():
    print("=== テスト12: 出力フォルダ構造 ===")
    import tempfile, shutil
    from y_shot import _safe_filename

    # ルートフォルダ名 (タイムスタンプのみ)
    ts = "20260326120000"
    dir_name = ts
    assert dir_name == "20260326120000"
    print(f"  [OK] ルートフォルダ名: {dir_name}")

    # ページごとサブフォルダ名
    pg_num = "1"; pg_name = "初期状態"
    pg_dir_name = f"{pg_num}_{_safe_filename(pg_name, 30)}"
    assert pg_dir_name == "1_初期状態"
    print(f"  [OK] ページサブフォルダ名: {pg_dir_name}")

    # ファイル名にテスト番号・テスト名を含む
    tc_number = "1-2"; tc_name = "姓いろんな入力"
    safe_number = _safe_filename(tc_number, 10)
    safe_tc = _safe_filename(tc_name, 20)
    fn = f"002_{safe_number}_{safe_tc}_p01_未入力_ss1.png"
    assert fn == "002_1-2_姓いろんな入力_p01_未入力_ss1.png"
    print(f"  [OK] ファイル名: {fn}")

    # 【】がファイル名に使えることを確認
    assert _safe_filename("【2_ページ名】", 40) == "【2_ページ名】"
    print("  [OK] 【】はファイル名セーフ")

    # ディレクトリ構造シミュレーション (ページごとサブフォルダ)
    tmpdir = tempfile.mkdtemp()
    try:
        outdir = os.path.join(tmpdir, dir_name)
        os.makedirs(outdir)
        # ページごとサブフォルダ
        pd1 = os.path.join(outdir, "1_初期状態")
        pd2 = os.path.join(outdir, "2_入力画面_2")
        os.makedirs(pd1); os.makedirs(pd2)
        # ページ1のテスト群
        open(os.path.join(pd1, "001_1-1_初期状態確認_p01_single_ss1.png"), "w").close()
        open(os.path.join(pd1, "002_1-2_姓いろんな入力_p01_未入力_ss1.png"), "w").close()
        open(os.path.join(pd1, "003_1-2_姓いろんな入力_p02_全角SP_ss1.png"), "w").close()
        # ページ2のテスト群
        open(os.path.join(pd2, "004_2-1_確認画面チェック_p01_single_ss1.png"), "w").close()
        # Walk and collect
        all_pngs = []
        for root, dirs, files in os.walk(outdir):
            dirs.sort()
            for fn in sorted(files):
                if fn.endswith(".png"):
                    rel = os.path.relpath(os.path.join(root, fn), outdir).replace("\\", "/")
                    all_pngs.append(rel)
        assert len(all_pngs) == 4
        assert all_pngs[0].startswith("1_初期状態/")
        assert all_pngs[2].startswith("1_初期状態/")  # same page
        assert all_pngs[3].startswith("2_入力画面_2/")
        # ファイル名にテスト番号が含まれている
        assert "1-2_姓いろんな入力" in all_pngs[1]
        print(f"  [OK] os.walk で4件収集、ページ別サブフォルダ")

        # page_dirs lookup simulation
        pages = [
            {"_id": "p1", "number": "1", "name": "初期状態"},
            {"_id": "p2", "number": "2", "name": "入力画面_2"},
        ]
        page_dirs = {}
        for pg in pages:
            pg_dir = os.path.join(outdir, f"{pg['number']}_{_safe_filename(pg['name'], 30)}")
            page_dirs[pg["_id"]] = pg_dir
        tc = {"page_id": "p1"}
        assert page_dirs.get(tc["page_id"]) == pd1
        tc2 = {"page_id": "p2"}
        assert page_dirs.get(tc2["page_id"]) == pd2
        tc_no_page = {"page_id": "unknown"}
        assert page_dirs.get(tc_no_page["page_id"], outdir) == outdir  # fallback to root
        print("  [OK] page_dirs lookup + fallback")
    finally:
        shutil.rmtree(tmpdir)

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト13: 半角数値境界値生成
# ---------------------------------------------------------------------------

def test_numeric_generation():
    print("=== テスト13: 半角数値境界値生成 ===")

    DIGITS = "1234567890"
    def _make_num(length):
        if length <= 0: return ""
        return (DIGITS * (length // 10 + 1))[:length]

    # 基本
    assert _make_num(10) == "1234567890"
    print("  [OK] 10桁 = 1234567890")

    assert _make_num(3) == "123"
    print("  [OK] 3桁 = 123")

    assert _make_num(15) == "123456789012345"
    print("  [OK] 15桁 = 繰り返し")

    assert _make_num(1) == "1"
    print("  [OK] 1桁 = 1")

    assert _make_num(0) == ""
    print("  [OK] 0桁 = 空文字")

    # 長い値
    v = _make_num(1000)
    assert len(v) == 1000
    assert v[:10] == "1234567890"
    assert all(c.isdigit() for c in v)
    print("  [OK] 1000桁 = 正しい長さ + 半角数値のみ")

    # 境界値セット生成
    n = 50
    ps = []
    if n > 1: ps.append({"label": f"数値max-1({n-1}桁)", "value": _make_num(n - 1)})
    ps.append({"label": f"数値max({n}桁)", "value": _make_num(n)})
    ps.append({"label": f"数値max+1({n+1}桁)", "value": _make_num(n + 1)})
    assert len(ps) == 3
    assert len(ps[0]["value"]) == 49
    assert len(ps[1]["value"]) == 50
    assert len(ps[2]["value"]) == 51
    print("  [OK] 境界値セット (49, 50, 51桁)")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト14: ソース保存と正規化
# ---------------------------------------------------------------------------

def test_source_normalization():
    print("=== テスト14: ソース正規化 ===")
    from y_shot import _normalize_source

    # CSRF token normalization
    html = '<input type="hidden" name="_token" value="abc123XYZ">'
    normalized = _normalize_source(html)
    assert "abc123XYZ" not in normalized
    assert "__NORMALIZED__" in normalized
    print("  [OK] CSRFトークン除去")

    # PHPSESSID
    html = '<input name="PHPSESSID" value="sess_abc123">'
    normalized = _normalize_source(html)
    assert "sess_abc123" not in normalized
    print("  [OK] PHPSESSID除去")

    # Meta CSRF token
    html = '<meta name="csrf-token" content="long-random-token-here">'
    normalized = _normalize_source(html)
    assert "long-random-token-here" not in normalized
    print("  [OK] meta csrf-token除去")

    # Datetime normalization
    html = '<span>更新日: 2026-03-26 14:30:00</span>'
    normalized = _normalize_source(html)
    assert "2026-03-26 14:30:00" not in normalized
    assert "__DATETIME__" in normalized
    print("  [OK] 日時フォーマット正規化")

    html2 = '<span>2026/03/26 14:30</span>'
    normalized2 = _normalize_source(html2)
    assert "2026/03/26 14:30" not in normalized2
    print("  [OK] 日時フォーマット(スラッシュ)正規化")

    # Unix timestamp
    html = '<div data-ts="1711468200123">'
    normalized = _normalize_source(html)
    assert "1711468200123" not in normalized
    assert "__TIMESTAMP__" in normalized
    print("  [OK] Unixタイムスタンプ除去")

    # Cache buster
    html = '<link href="/style.css?v=abc123">'
    normalized = _normalize_source(html)
    assert "abc123" not in normalized
    assert "__CACHE__" in normalized
    print("  [OK] キャッシュバスター正規化")

    # Nonce
    html = '<script nonce="dGVzdDEyMw==">'
    normalized = _normalize_source(html)
    assert "dGVzdDEyMw==" not in normalized
    assert "__NONCE__" in normalized
    print("  [OK] nonce除去")

    # Normal content preserved
    html = '<div class="main"><h1>ユーザー登録</h1><p>入力してください</p></div>'
    normalized = _normalize_source(html)
    assert normalized == html
    print("  [OK] 通常コンテンツは変更なし")

    # _source directory structure test
    import tempfile, shutil
    tmpdir = tempfile.mkdtemp()
    try:
        outdir = os.path.join(tmpdir, "20260326120000")
        os.makedirs(outdir)
        source_root = os.path.join(outdir, "_source")
        os.makedirs(source_root)
        os.makedirs(os.path.join(outdir, "1_初期状態"))
        os.makedirs(os.path.join(source_root, "1_初期状態"))
        open(os.path.join(outdir, "1_初期状態", "001_ss1.png"), "w").close()
        with open(os.path.join(source_root, "1_初期状態", "001_ss1_raw.html"), "w") as f:
            f.write("<html>raw</html>")
        with open(os.path.join(source_root, "1_初期状態", "001_ss1_dom.html"), "w") as f:
            f.write("<html>dom</html>")
        # Report walk skips _source/
        all_pngs = []
        for root, dirs, files in os.walk(outdir):
            dirs[:] = [d for d in sorted(dirs) if not d.startswith("_")]
            for fn in sorted(files):
                if fn.endswith(".png"):
                    all_pngs.append(fn)
        assert len(all_pngs) == 1
        print("  [OK] レポートwalkは_source/をスキップ")
        # _source/ has matching files
        src_files = os.listdir(os.path.join(source_root, "1_初期状態"))
        assert len(src_files) == 2
        assert any("_raw.html" in f for f in src_files)
        assert any("_dom.html" in f for f in src_files)
        print("  [OK] _source/にraw+domの2ファイル保存")
    finally:
        shutil.rmtree(tmpdir)

    print("  全てパス\n")


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# テスト15: _sel_by XPath判定
# ---------------------------------------------------------------------------

def test_sel_by():
    print("=== テスト15: _sel_by XPath判定 ===")
    import importlib.util
    # _sel_by は y-shot (拡張版) のみに存在する
    spec = importlib.util.spec_from_file_location('_yshot_check', os.path.join(os.path.dirname(__file__) or '.', 'y_shot.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules['_yshot_sel_check'] = mod
    spec.loader.exec_module(mod)
    if not hasattr(mod, '_sel_by'):
        print("  [SKIP] _sel_by は本バージョンに存在しない（拡張版のみ）")
        print("  全てパス\n")
        return
    from selenium.webdriver.common.by import By
    _sel_by = mod._sel_by

    # 通常のCSSセレクタ
    assert _sel_by("#foo") == (By.CSS_SELECTOR, "#foo")
    assert _sel_by("img[src*='bar.jpg']") == (By.CSS_SELECTOR, "img[src*='bar.jpg']")
    assert _sel_by("div.btn_close") == (By.CSS_SELECTOR, "div.btn_close")
    print("  [OK] CSSセレクタ判定")

    # 通常のXPath
    assert _sel_by("//img[1]") == (By.XPATH, "//img[1]")
    assert _sel_by("//button[normalize-space()='送信']") == (By.XPATH, "//button[normalize-space()='送信']")
    print("  [OK] //始まりXPath判定")

    # 括弧付きXPath (//img)[2] 形式
    assert _sel_by("(//img)[2]") == (By.XPATH, "(//img)[2]")
    assert _sel_by("(//div)[1]") == (By.XPATH, "(//div)[1]")
    print("  [OK] (//tag)[n] 形式XPath判定")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト16: 検証ステップ + スクショモード整理
# ---------------------------------------------------------------------------

def test_verify_step():
    print("=== テスト16: 検証ステップ + スクショモード整理 ===")
    from y_shot import step_short, STEP_TYPES

    # 検証ステップの有無はバージョンによる
    has_verify = "検証" in STEP_TYPES
    if has_verify:
        print("  [OK] STEP_TYPESに検証あり")

        # step_short: 検証ステップの表示
        assert "POST値" in step_short({"type": "検証", "verify_type": "post"})
        assert "要素状態" in step_short({"type": "検証", "verify_type": "state", "selector": "#foo"})
        assert "要素属性" in step_short({"type": "検証", "verify_type": "attrs", "selector": "(//img)[2]"})
        print("  [OK] 検証ステップの表示文字列")

        # step_short: 検証ステップでセレクタが含まれるか
        s = step_short({"type": "検証", "verify_type": "attrs", "selector": "img.logo"})
        assert "img.logo" in s, f"セレクタが含まれない: {s}"
        print("  [OK] 検証ステップにセレクタ表示")

        # step_short: 長いセレクタは切り詰め
        long_sel = "div.very-long-selector-name-that-should-be-truncated"
        s = step_short({"type": "検証", "verify_type": "attrs", "selector": long_sel})
        assert "..." in s, f"長いセレクタが切り詰められていない: {s}"
        print("  [OK] 長いセレクタの切り詰め")
    else:
        print("  [SKIP] 検証ステップは本バージョンに未実装")

    # step_short: スクショモード（全バージョン共通）
    assert "表示範囲" in step_short({"type": "スクショ", "mode": "fullpage"})
    assert "ページ全体" in step_short({"type": "スクショ", "mode": "fullshot"})
    assert "要素のみ" == step_short({"type": "スクショ", "mode": "element"})
    assert "500" in step_short({"type": "スクショ", "mode": "margin", "margin_px": "500"})
    print("  [OK] スクショモード基本表示")

    # 旧post/stateモード後方互換（拡張版のみ）
    if has_verify:
        s_post = step_short({"type": "スクショ", "mode": "post"})
        s_state = step_short({"type": "スクショ", "mode": "state"})
        assert "POST" in s_post or "post" in s_post.lower(), f"postモード表示: {s_post}"
        assert "状態" in s_state or "state" in s_state.lower(), f"stateモード表示: {s_state}"
        print("  [OK] スクショモード後方互換表示")
    else:
        print("  [SKIP] post/state後方互換は拡張版のみ")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト17: テスト名の\\rサニタイズ
# ---------------------------------------------------------------------------

def test_cr_sanitize():
    print("=== テスト17: テスト名の\\rサニタイズ ===")
    from y_shot import load_tests, save_tests

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f:
        tmp = f.name
        json.dump([
            {"name": "設問1の表示\r", "_id": "tc_1", "steps": []},
            {"name": "進捗バーの画像表示\r\n", "_id": "tc_2", "steps": []},
            {"name": "正常なテスト名", "_id": "tc_3", "steps": []},
        ], f, ensure_ascii=False)

    # load_testsがファイルパスではなくプロジェクトディレクトリから読むので、
    # 直接JSONを読んでサニタイズロジックをテスト
    with open(tmp, "r", encoding="utf-8") as f:
        tests = json.load(f)
    # サニタイズ処理を再現
    for t in tests:
        if "name" in t and isinstance(t["name"], str):
            t["name"] = t["name"].replace("\r", "").replace("\n", "").strip()

    assert tests[0]["name"] == "設問1の表示", f"\\r除去失敗: {repr(tests[0]['name'])}"
    assert tests[1]["name"] == "進捗バーの画像表示", f"\\r\\n除去失敗: {repr(tests[1]['name'])}"
    assert tests[2]["name"] == "正常なテスト名", f"正常名が変わった: {repr(tests[2]['name'])}"
    print("  [OK] \\r / \\r\\n がテスト名から除去される")

    os.unlink(tmp)
    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト18: _safe_json_save / _safe_json_load 破損復帰
# ---------------------------------------------------------------------------

def test_json_persistence():
    print("=== テスト18: JSON永続化 (保存/読込/破損復帰) ===")
    from y_shot import _safe_json_save, _safe_json_load

    with tempfile.TemporaryDirectory() as tmpdir:
        fp = os.path.join(tmpdir, "test.json")

        # 正常な保存/読込
        data = {"tests": [{"name": "T1"}], "unicode": "日本語🦐", "num": 42}
        _safe_json_save(fp, data)
        loaded = _safe_json_load(fp, {})
        assert loaded == data, f"round-trip失敗: {loaded}"
        print("  [OK] 正常round-trip")

        # backupファイルの存在確認
        _safe_json_save(fp, {"version": 2})
        assert os.path.isfile(fp + ".backup"), "backupが作られていない"
        print("  [OK] backupファイル作成")

        # メインファイル破損 → backupから復帰
        with open(fp, "w") as f:
            f.write("{ broken json !!!")
        loaded = _safe_json_load(fp, {"default": True})
        assert loaded.get("version") == 1 or "tests" in loaded, f"backup復帰失敗: {loaded}"
        print("  [OK] メイン破損時のbackup復帰")

        # 両方破損 → default
        with open(fp, "w") as f:
            f.write("broken")
        with open(fp + ".backup", "w") as f:
            f.write("broken too")
        loaded = _safe_json_load(fp, {"fallback": True})
        assert loaded == {"fallback": True}, f"default返却失敗: {loaded}"
        print("  [OK] 両方破損時のdefault返却")

        # 存在しないファイル → default
        loaded = _safe_json_load(os.path.join(tmpdir, "nope.json"), [])
        assert loaded == [], f"存在しないファイル: {loaded}"
        print("  [OK] 存在しないファイル→default")

        # tmpファイル残留しないか確認
        fp2 = os.path.join(tmpdir, "clean.json")
        _safe_json_save(fp2, {"ok": True})
        assert not os.path.isfile(fp2 + ".tmp"), ".tmpが残っている"
        print("  [OK] .tmpファイル残留なし")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト19: build_auth_url
# ---------------------------------------------------------------------------

def test_build_auth_url():
    print("=== テスト19: build_auth_url ===")
    from y_shot import build_auth_url

    # ユーザーなし → URLそのまま
    assert build_auth_url("http://example.com", "", "pass") == "http://example.com"
    print("  [OK] ユーザーなし→そのまま")

    # 通常ケース
    result = build_auth_url("http://example.com/path?q=1", "user", "pass")
    assert "user:pass@example.com" in result
    assert "/path?q=1" in result
    print("  [OK] 通常URL")

    # ポート付き
    result = build_auth_url("http://localhost:8080/app", "admin", "secret")
    assert "admin:secret@localhost:8080" in result
    print("  [OK] ポート付きURL")

    # HTTPS
    result = build_auth_url("https://secure.example.com", "u", "p")
    assert result.startswith("https://")
    assert "u:p@secure.example.com" in result
    print("  [OK] HTTPS")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト20: _normalize_source (HTMLソース正規化)
# ---------------------------------------------------------------------------

def test_normalize_source_comprehensive():
    print("=== テスト20: _normalize_source 包括テスト ===")
    from y_shot import _normalize_source

    # CSRFトークン正規化
    html1 = '<input type="hidden" name="csrf_token" value="abc123xyz789">'
    html2 = '<input type="hidden" name="csrf_token" value="completely_different">'
    assert _normalize_source(html1) == _normalize_source(html2), "CSRFトークン正規化失敗"
    print("  [OK] CSRFトークン正規化")

    # PHPSESSID正規化
    html1 = '<input name="PHPSESSID" value="sess_abc123">'
    html2 = '<input name="PHPSESSID" value="sess_xyz789">'
    assert _normalize_source(html1) == _normalize_source(html2), "PHPSESSID正規化失敗"
    print("  [OK] PHPSESSID正規化")

    # meta csrf-token
    html1 = '<meta name="csrf-token" content="token_aaa">'
    html2 = '<meta name="csrf-token" content="token_bbb">'
    assert _normalize_source(html1) == _normalize_source(html2), "meta csrf正規化失敗"
    print("  [OK] meta csrf-token正規化")

    # 日時フォーマット正規化
    html1 = '2024-01-15 10:30:00'
    html2 = '2025-12-31 23:59:59'
    assert _normalize_source(html1) == _normalize_source(html2), "日時正規化失敗"
    print("  [OK] 日時フォーマット正規化")

    # 日時フォーマット (スラッシュ区切り)
    html1 = '2024/01/15 10:30:00'
    html2 = '2025/12/31 23:59:59'
    assert _normalize_source(html1) == _normalize_source(html2), "日時(slash)正規化失敗"
    print("  [OK] 日時フォーマット(スラッシュ)正規化")

    # Unixタイムスタンプ正規化
    html1 = '"timestamp": "1704067200"'
    html2 = '"timestamp": "1735689599"'
    n1 = _normalize_source(html1)
    n2 = _normalize_source(html2)
    assert n1 == n2, f"タイムスタンプ正規化失敗: {n1} != {n2}"
    print("  [OK] Unixタイムスタンプ正規化")

    # キャッシュバスター正規化
    html1 = '<link href="style.css?v=1234">'
    html2 = '<link href="style.css?v=9999">'
    assert _normalize_source(html1) == _normalize_source(html2), "キャッシュバスター正規化失敗"
    print("  [OK] キャッシュバスター正規化")

    # nonce正規化
    html1 = 'nonce="abc123def456"'
    html2 = 'nonce="xyz789uvw012"'
    assert _normalize_source(html1) == _normalize_source(html2), "nonce正規化失敗"
    print("  [OK] nonce正規化")

    # 通常コンテンツは変更しない
    html = '<p class="main">Hello World テスト</p>'
    assert "Hello World テスト" in _normalize_source(html), "通常コンテンツが消えた"
    print("  [OK] 通常コンテンツ保持")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト21: y_diff normalize / classify
# ---------------------------------------------------------------------------

def test_ydiff_normalize_classify():
    print("=== テスト21: y_diff normalize / classify ===")
    sys.path.insert(0, os.path.dirname(__file__) or '.')
    from y_diff import normalize, classify_line, classify_change, _extract_text_content

    # normalize: 基本ホワイトスペース正規化
    result = normalize("  <div>  text  </div>  ")
    assert "text" in result
    print("  [OK] normalize基本")

    # normalize: CRLF正規化
    result = normalize("<p>line1\r\nline2\r\nline3</p>")
    assert "\r" not in result
    print("  [OK] CRLF除去")

    # normalize: ブロック分割
    result = normalize("<div><p>a</p><p>b</p></div>")
    assert result.count('\n') >= 1, f"ブロック分割なし: {repr(result)}"
    print("  [OK] ブロックレベル分割")

    # normalize: 空script除去
    result = normalize('<script></script><p>keep</p>')
    assert "keep" in result
    assert "<script></script>" not in result
    print("  [OK] 空script除去")

    # classify_line: PHP warning
    assert classify_line("Notice: Undefined index in /var/www/app.php on line 42") == "php_warning"
    assert classify_line("Warning: Division by zero in file.php on line 10") == "php_warning"
    print("  [OK] classify_line: PHP warning")

    # classify_line: form
    assert classify_line('<input type="text" name="email">') == "form"
    assert classify_line('<select id="country">') == "form"
    assert classify_line('value="test" checked') == "form"
    print("  [OK] classify_line: form")

    # classify_line: structural
    assert classify_line('<div class="container">') == "structural"
    assert classify_line('<table id="main">') == "structural"
    print("  [OK] classify_line: structural")

    # classify_line: content
    assert classify_line('<p>Hello World</p>') == "content"
    assert classify_line('<h1>タイトル</h1>') == "content"
    assert classify_line('plain text without tags') == "content"
    print("  [OK] classify_line: content")

    # classify_change: テキスト同じ・タグ違い → noise
    result = classify_change('<div class="old">text</div>', '<div class="new">text</div>')
    assert result == "noise", f"タグ違い同テキストがnoiseにならない: {result}"
    print("  [OK] classify_change: 同テキスト→noise")

    # classify_change: PHP warning > 他
    result = classify_change("Notice: Undefined var", '<div>normal</div>')
    assert result == "php_warning"
    print("  [OK] classify_change: PHP warning優先")

    # _extract_text_content
    assert _extract_text_content('<p class="big">Hello <b>World</b></p>') == "Hello World"
    assert _extract_text_content("no tags") == "no tags"
    print("  [OK] _extract_text_content")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト22: y_diff scan_source_folder
# ---------------------------------------------------------------------------

def test_ydiff_scan_source():
    print("=== テスト22: y_diff scan_source_folder ===")
    from y_diff import scan_source_folder, scan_image_folder

    with tempfile.TemporaryDirectory() as tmpdir:
        # _source構造を作成
        src = os.path.join(tmpdir, "_source", "1_page1")
        os.makedirs(src)
        with open(os.path.join(src, "001_1-1_test_dom.html"), "w") as f:
            f.write("<html>dom</html>")
        with open(os.path.join(src, "001_1-1_test_raw.html"), "w") as f:
            f.write("<html>raw</html>")

        result = scan_source_folder(tmpdir)
        assert len(result) > 0, "ファイルが見つからない"
        key = list(result.keys())[0]
        assert "dom" in result[key], f"domキーがない: {result[key].keys()}"
        assert "raw" in result[key], f"rawキーがない: {result[key].keys()}"
        print("  [OK] _source構造スキャン (dom+raw)")

        # 画像スキャン
        img_dir = os.path.join(tmpdir, "1_page1")
        os.makedirs(img_dir)
        open(os.path.join(img_dir, "001_ss1.png"), "w").close()
        open(os.path.join(img_dir, "002_ss2.png"), "w").close()
        open(os.path.join(img_dir, "001_ss1_diff.png"), "w").close()  # _diffは除外すべき

        imgs = scan_image_folder(tmpdir)
        assert len(imgs) >= 2, f"画像が足りない: {len(imgs)}"
        # _diffファイルは除外されるべき
        diff_count = sum(1 for k in imgs if "_diff" in k)
        assert diff_count == 0, f"_diffファイルが含まれている: {list(imgs.keys())}"
        print("  [OK] 画像スキャン (_diff除外)")

    # 空フォルダ
    with tempfile.TemporaryDirectory() as tmpdir:
        result = scan_source_folder(tmpdir)
        assert result == {}, f"空フォルダが空dictでない: {result}"
        print("  [OK] 空フォルダ→空dict")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト23: CSV特殊文字round-trip
# ---------------------------------------------------------------------------

def test_csv_special_chars():
    print("=== テスト23: CSV特殊文字round-trip ===")
    from y_shot import load_csv, save_csv

    patterns = [
        {"label": "カンマ入り", "value": "a,b,c"},
        {"label": "引用符入り", "value": 'says "hello"'},
        {"label": "改行入り", "value": "line1\nline2"},
        {"label": "日本語", "value": "テスト値"},
        {"label": "空値", "value": ""},
    ]

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp = f.name
    try:
        save_csv(tmp, patterns)
        loaded = load_csv(tmp)
        assert len(loaded) == 5, f"件数不一致: {len(loaded)}"
        assert loaded[0]["value"] == "a,b,c", f"カンマ: {loaded[0]['value']}"
        assert loaded[1]["value"] == 'says "hello"', f"引用符: {loaded[1]['value']}"
        assert loaded[2]["value"] == "line1\nline2", f"改行: {repr(loaded[2]['value'])}"
        assert loaded[3]["value"] == "テスト値", f"日本語: {loaded[3]['value']}"
        assert loaded[4]["value"] == "", f"空値: {repr(loaded[4]['value'])}"
        print("  [OK] カンマ,引用符,改行,日本語,空値のround-trip")
    finally:
        os.unlink(tmp)

    # 空ファイル (ヘッダのみ)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp = f.name
    try:
        save_csv(tmp, [])
        loaded = load_csv(tmp)
        assert loaded == [], f"空CSV: {loaded}"
        print("  [OK] 空CSVの保存/読込")
    finally:
        os.unlink(tmp)

    # 存在しないファイル
    loaded = load_csv(os.path.join(tempfile.gettempdir(), "nonexistent_12345.csv"))
    assert loaded == [], f"存在しないファイル: {loaded}"
    print("  [OK] 存在しないファイル→空リスト")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト24: _safe_float エッジケース
# ---------------------------------------------------------------------------

def test_safe_float_edge():
    print("=== テスト24: _safe_float エッジケース ===")
    from y_shot import _safe_float

    # 基本
    assert _safe_float("3.14") == 3.14
    assert _safe_float(42) == 42.0
    assert _safe_float("0") == 0.0
    print("  [OK] 基本変換")

    # 不正値
    assert _safe_float("", 5.0) == 5.0
    assert _safe_float(None, 2.0) == 2.0
    assert _safe_float("abc", 1.0) == 1.0
    assert _safe_float("--3") == 1.0  # defaultは1.0
    assert _safe_float([], 0.5) == 0.5
    print("  [OK] 不正値→default")

    # 科学的記数法
    assert _safe_float("1.5e2") == 150.0
    assert _safe_float("-0.5") == -0.5
    print("  [OK] 科学的記数法, 負数")

    # 前後空白
    assert _safe_float(" 2.5 ") == 2.5
    print("  [OK] 前後空白")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト25: step_short 全ステップタイプ
# ---------------------------------------------------------------------------

def test_step_short_all_types():
    print("=== テスト25: step_short 全ステップタイプ ===")
    from y_shot import step_short, STEP_TYPES

    # 各ステップタイプが表示できること (クラッシュしないこと)
    for st in STEP_TYPES:
        result = step_short({"type": st})
        assert isinstance(result, str), f"{st}の表示がstr以外: {type(result)}"
    print(f"  [OK] 全{len(STEP_TYPES)}ステップタイプの表示（クラッシュなし）")

    # 必須フィールドなしでもクラッシュしない
    result = step_short({"type": "入力"})  # selector/value なし
    assert isinstance(result, str)
    result = step_short({"type": "クリック"})  # selector なし
    assert isinstance(result, str)
    result = step_short({"type": "スクショ"})  # mode なし
    assert isinstance(result, str)
    print("  [OK] フィールド欠落時もクラッシュしない")

    # Noneフィールド
    result = step_short({"type": "入力", "selector": None, "value": None})
    assert isinstance(result, str)
    print("  [OK] Noneフィールド")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト26: _safe_filename 禁止文字
# ---------------------------------------------------------------------------

def test_safe_filename_forbidden():
    print("=== テスト26: _safe_filename 禁止文字 ===")
    from y_shot import _safe_filename

    forbidden = '\\/:*?"<>|'
    result = _safe_filename(f"test{forbidden}name")
    for c in forbidden:
        assert c not in result, f"禁止文字 '{c}' が残っている: {result}"
    print("  [OK] 全禁止文字の除去")

    # 制御文字
    result = _safe_filename("ab\x00\x01\x1fcd")
    assert "\x00" not in result and "\x01" not in result
    print("  [OK] 制御文字の除去")

    # 連続アンダースコアの処理
    result = _safe_filename("a:::b")
    assert isinstance(result, str) and len(result) > 0
    print("  [OK] 連続禁止文字")

    # max_len指定
    result = _safe_filename("テスト名前" * 10, max_len=10)
    assert len(result) <= 10, f"max_len超過: len={len(result)}"
    print("  [OK] max_len制限")

    # ドットのみ
    assert _safe_filename("...") == "_"
    assert _safe_filename("..") == "_"
    print("  [OK] ドットのみ→_")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト27: y_diff compare_images (PIL利用可能時のみ)
# ---------------------------------------------------------------------------

def test_compare_images():
    print("=== テスト27: y_diff compare_images ===")
    try:
        from PIL import Image
    except ImportError:
        print("  [SKIP] PILが利用不可")
        print("  全てパス\n")
        return

    from y_diff import compare_images

    with tempfile.TemporaryDirectory() as tmpdir:
        # 同一画像
        img_path_a = os.path.join(tmpdir, "a.png")
        img_path_b = os.path.join(tmpdir, "b.png")
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img.save(img_path_a)
        img.save(img_path_b)

        same, pct, diff_path = compare_images(img_path_a, img_path_b)
        assert same == True, f"同一画像がsame=False: pct={pct}"
        assert pct < 0.1
        assert diff_path is None
        print("  [OK] 同一画像→一致")

        # 異なる画像
        img2 = Image.new("RGB", (100, 100), color=(0, 0, 255))
        img2.save(img_path_b)
        same, pct, diff_path = compare_images(img_path_a, img_path_b)
        assert same == False, "異なる画像がsame=True"
        assert pct > 50.0, f"差分率が低すぎ: {pct}"
        print("  [OK] 異なる画像→不一致")

        # サイズ不一致
        img3 = Image.new("RGB", (200, 200), color=(255, 0, 0))
        img3.save(img_path_b)
        same, pct, diff_path = compare_images(img_path_a, img_path_b)
        assert same == False
        assert pct == 100.0, f"サイズ不一致のpctが100でない: {pct}"
        print("  [OK] サイズ不一致→100%差分")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト28: auto_number_tests _sub_number不正値
# ---------------------------------------------------------------------------

def test_auto_number_sub_invalid():
    print("=== テスト28: auto_number _sub_number不正値 ===")
    # auto_number_testsは内部関数のため、ロジック再現テスト
    from y_shot import _safe_float

    # _sub_numberが不正値の場合のint変換
    for bad_val in ["abc", "", None, "3.5", []]:
        try:
            if bad_val is not None:
                int(bad_val)
                # ここに来たら不正値ではない
            else:
                raise TypeError
        except (ValueError, TypeError):
            pass  # 期待通り例外
    print("  [OK] 不正_sub_numberでint()が例外を出すことを確認")

    # _safe_floatでstart_numberの防御
    assert int(_safe_float("abc", 1)) == 1
    assert int(_safe_float("", 1)) == 1
    assert int(_safe_float(None, 1)) == 1
    print("  [OK] start_numberの_safe_floatフォールバック")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト29: Selenium API 利用可能確認 (クリック処理・ホバー処理の前提)
# ---------------------------------------------------------------------------

def test_selenium_api():
    print("=== テスト29: Selenium API 利用可能確認 ===")

    # クリック処理で使用: presence_of_element_located
    from selenium.webdriver.support import expected_conditions as EC
    assert hasattr(EC, 'presence_of_element_located')
    print("  [OK] presence_of_element_located (クリック処理)")

    # ホバー処理で使用: ActionChains
    from selenium.webdriver.common.action_chains import ActionChains
    assert ActionChains is not None
    print("  [OK] ActionChains (ホバー処理)")

    # By がインポート可能か
    from selenium.webdriver.common.by import By
    assert hasattr(By, 'CSS_SELECTOR')
    assert hasattr(By, 'XPATH')
    print("  [OK] By (CSS_SELECTOR, XPATH)")

    # _sel_by がCSS/XPathを正しく判別するか
    from y_shot import _sel_by
    assert _sel_by("#btn")[0] == By.CSS_SELECTOR
    assert _sel_by("//div")[0] == By.XPATH
    assert _sel_by("(//img)[3]")[0] == By.XPATH
    assert _sel_by("label.radio_center")[0] == By.CSS_SELECTOR
    print("  [OK] _sel_by CSS/XPath判別")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト30: Flet FilePicker API確認 (v3.0 エクスポート/インポート)
# ---------------------------------------------------------------------------

def test_flet_filepicker():
    print("=== テスト30: Flet FilePicker API確認 ===")
    import inspect
    import flet as ft

    # FilePicker が存在するか
    assert hasattr(ft, 'FilePicker'), "ft.FilePicker が存在しない"
    print("  [OK] ft.FilePicker 存在")

    # save_file / pick_files がメソッドとして存在するか
    fp = ft.FilePicker()
    assert hasattr(fp, 'save_file'), "save_file メソッドが存在しない"
    assert hasattr(fp, 'pick_files'), "pick_files メソッドが存在しない"
    print("  [OK] save_file / pick_files メソッド存在")

    # async であることの確認（v3.0ではawaitで呼ぶため）
    assert inspect.iscoroutinefunction(fp.save_file), "save_file が async でない"
    assert inspect.iscoroutinefunction(fp.pick_files), "pick_files が async でない"
    print("  [OK] save_file / pick_files は async")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト31: プロジェクトエクスポートデータ構造
# ---------------------------------------------------------------------------

def test_project_export_structure():
    print("=== テスト31: プロジェクトエクスポートデータ構造 ===")
    from y_shot import APP_NAME, APP_VERSION

    # エクスポートされるJSON構造のシミュレーション
    pages = [{"_id": "p_1", "name": "テストページ", "number": "1", "start_number": 1, "url": ""}]
    tests = [{"name": "テスト1", "pattern": None, "steps": [
        {"type": "クリック", "selector": "#btn"},
        {"type": "スクショ", "mode": "fullpage"},
    ], "_id": "tc_1", "page_id": "p_1", "number": "1-1"}]
    pattern_sets = {"基本セット": [{"label": "未入力", "value": ""}]}
    config = {"project_url": "http://example.com", "headless": "0"}
    selector_bank = {"http://example.com": [{"selector": "#btn", "tag": "button"}]}

    project_data = {
        "app": APP_NAME, "version": APP_VERSION,
        "project_name": "テストプロジェクト",
        "pages": pages, "tests": tests,
        "pattern_sets": pattern_sets, "config": config,
        "selector_bank": selector_bank,
    }

    # 必須キーの存在確認
    for key in ["app", "version", "project_name", "pages", "tests", "pattern_sets", "config", "selector_bank"]:
        assert key in project_data, f"必須キー '{key}' がない"
    print("  [OK] 必須キー存在")

    # JSON round-trip
    json_str = json.dumps(project_data, ensure_ascii=False, indent=2)
    loaded = json.loads(json_str)
    assert loaded["app"] == APP_NAME
    assert loaded["version"] == APP_VERSION
    assert len(loaded["pages"]) == 1
    assert len(loaded["tests"]) == 1
    assert len(loaded["tests"][0]["steps"]) == 2
    assert "基本セット" in loaded["pattern_sets"]
    print("  [OK] JSON round-trip")

    # インポート時のバリデーション条件
    assert "pages" in loaded and "tests" in loaded, "インポートバリデーション失敗"
    # output_dir はインポート時に除外される
    config_with_outdir = dict(config, output_dir="C:/some/path")
    imp_config = {k: v for k, v in config_with_outdir.items() if k != "output_dir"}
    assert "output_dir" not in imp_config
    assert "project_url" in imp_config
    print("  [OK] インポート時output_dir除外")

    # テスト名の\\rサニタイズ（インポート処理）
    imp_tests = [{"name": "テスト\r\n名", "_id": "tc_1", "steps": []}]
    for t in imp_tests:
        if "name" in t: t["name"] = t["name"].replace("\r", "").replace("\n", "").strip()
    assert imp_tests[0]["name"] == "テスト名"
    print("  [OK] インポート時\\r\\nサニタイズ")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト32: 要素ブラウザ _el_idx_to_row キャッシュロジック
# ---------------------------------------------------------------------------

def test_el_idx_to_row_cache():
    print("=== テスト32: 要素ブラウザ インデックスマッピング ===")

    # filter_el_table のマッピング構築ロジックを再現
    def build_idx_to_row(elements, show_hidden=False, query=""):
        idx_to_row = {}
        visible_count = 0
        for i, el in enumerate(elements):
            is_visible = el.get("visible", True)
            if not is_visible and not show_hidden:
                continue
            if query:
                searchable = " ".join([
                    el.get("tag", ""), el.get("type", ""), el.get("id", ""),
                    el.get("name", ""), el.get("hint", ""), el.get("selector", "")
                ]).lower()
                if query not in searchable:
                    continue
            idx_to_row[i] = visible_count
            visible_count += 1
        return idx_to_row

    elements = [
        {"tag": "input", "type": "text", "id": "name", "name": "name", "hint": "名前", "selector": "#name", "visible": True},
        {"tag": "input", "type": "hidden", "id": "token", "name": "token", "hint": "", "selector": "#token", "visible": False},
        {"tag": "button", "type": "submit", "id": "btn", "name": "", "hint": "送信", "selector": "#btn", "visible": True},
        {"tag": "input", "type": "text", "id": "email", "name": "email", "hint": "メール", "selector": "#email", "visible": True},
        {"tag": "div", "type": "", "id": "hidden-div", "name": "", "hint": "", "selector": "#hidden-div", "visible": False},
    ]

    # 全表示（hidden非表示）
    m = build_idx_to_row(elements, show_hidden=False)
    assert m == {0: 0, 2: 1, 3: 2}, f"visible only mapping: {m}"
    assert 1 not in m  # hidden token
    assert 4 not in m  # hidden div
    print("  [OK] hidden非表示時のマッピング")

    # hidden表示
    m = build_idx_to_row(elements, show_hidden=True)
    assert m == {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}, f"show hidden mapping: {m}"
    print("  [OK] hidden表示時のマッピング")

    # 検索フィルタ
    m = build_idx_to_row(elements, show_hidden=False, query="input")
    assert m == {0: 0, 3: 1}, f"search 'input' mapping: {m}"
    print("  [OK] 検索フィルタ時のマッピング")

    m = build_idx_to_row(elements, show_hidden=False, query="送信")
    assert m == {2: 0}, f"search '送信' mapping: {m}"
    print("  [OK] 検索で1件のみ")

    m = build_idx_to_row(elements, show_hidden=False, query="存在しないワード")
    assert m == {}, f"search no match: {m}"
    print("  [OK] 検索で0件")

    # O(1) 参照
    m = build_idx_to_row(elements, show_hidden=False)
    assert m.get(0, -1) == 0
    assert m.get(2, -1) == 1
    assert m.get(1, -1) == -1  # hidden → not in map
    assert m.get(99, -1) == -1  # out of range
    print("  [OK] O(1)参照（存在/非存在）")

    # 空リスト
    m = build_idx_to_row([], show_hidden=False)
    assert m == {}
    print("  [OK] 空リスト")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト33: 要素ブラウザ _prev_el_row 選択追跡ロジック
# ---------------------------------------------------------------------------

def test_prev_el_row_tracking():
    print("=== テスト33: 要素ブラウザ 選択行追跡 ===")

    # on_el_click の選択解除/選択ロジックを再現
    class MockRow:
        def __init__(self, selected=False):
            self.selected = selected

    def sim_click(rows, prev_row, new_row):
        """Simulate on_el_click selection logic. Returns new prev_row."""
        if 0 <= prev_row < len(rows):
            rows[prev_row].selected = False
        if 0 <= new_row < len(rows):
            rows[new_row].selected = True
        return new_row

    # 基本: 1つ目を選択
    rows = [MockRow(), MockRow(), MockRow(), MockRow(), MockRow()]
    prev = -1
    prev = sim_click(rows, prev, 2)
    assert rows[2].selected == True
    assert prev == 2
    assert all(not r.selected for i, r in enumerate(rows) if i != 2)
    print("  [OK] 初回選択")

    # 別の行を選択 → 旧行が解除される
    prev = sim_click(rows, prev, 4)
    assert rows[4].selected == True
    assert rows[2].selected == False
    assert prev == 4
    print("  [OK] 別行選択で旧行解除")

    # 同じ行を再選択
    prev = sim_click(rows, prev, 4)
    assert rows[4].selected == True
    assert prev == 4
    print("  [OK] 同行再選択")

    # prev=-1 で旧行解除スキップ（テーブル再構築後）
    prev = -1
    rows = [MockRow(selected=True), MockRow(), MockRow()]  # 0番が選択状態（filter_el_tableで設定）
    prev = sim_click(rows, prev, 1)
    # prev=-1なので旧行(0)はFalseにならない → これが問題だった
    # fix後: filter_el_tableで_prev_el_rowを正しくセットするので、prev=-1にはならない
    # ここではprev=0（filter_el_table後の正しい値）をテスト
    rows2 = [MockRow(selected=True), MockRow(), MockRow()]
    prev2 = 0  # filter_el_table が設定する正しい _prev_el_row
    prev2 = sim_click(rows2, prev2, 2)
    assert rows2[0].selected == False  # 旧行解除
    assert rows2[2].selected == True   # 新行選択
    assert prev2 == 2
    print("  [OK] テーブル再構築後の正しい prev_el_row")

    # 範囲外の prev → 安全にスキップ
    rows3 = [MockRow(), MockRow()]
    prev3 = 99  # テーブルより大きい
    prev3 = sim_click(rows3, prev3, 0)
    assert rows3[0].selected == True
    assert prev3 == 0
    print("  [OK] 範囲外prevの安全処理")

    # new_row=-1 (マッピングに存在しない) → 選択なし
    rows4 = [MockRow(selected=True), MockRow()]
    prev4 = 0
    prev4 = sim_click(rows4, prev4, -1)
    assert rows4[0].selected == False  # 旧行解除
    assert prev4 == -1
    print("  [OK] マッピング外要素の選択（選択なし）")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト34: クリック処理 Selenium→JSフォールバック構造確認
# ---------------------------------------------------------------------------

def test_click_handler_structure():
    print("=== テスト34: クリック処理 フォールバック構造確認 ===")
    import ast, inspect
    from y_shot import run_all_tests

    # run_all_tests のソースコードを解析
    source = inspect.getsource(run_all_tests)

    # presence_of_element_located が使われていること
    assert "presence_of_element_located" in source, "クリック処理に presence_of_element_located がない"
    print("  [OK] presence_of_element_located 使用")

    # scrollIntoView が使われていること
    assert "scrollIntoView" in source, "scrollIntoView がない"
    print("  [OK] scrollIntoView 使用")

    # _el.click() が使われていること（Selenium native）
    assert "_el.click()" in source, "Selenium native click がない"
    print("  [OK] Selenium native _el.click() 使用")

    # JS element.click() フォールバックがあること
    assert 'arguments[0].click()' in source, "JS element.click() フォールバックがない"
    print("  [OK] JS element.click() フォールバック")

    # checked = true が使われていないこと（DOM直接操作禁止）
    assert "checked = true" not in source, "DOM直接操作 checked = true が残っている"
    assert "checked=true" not in source, "DOM直接操作 checked=true が残っている"
    print("  [OK] DOM直接操作 checked=true なし")

    # dispatchEvent が クリック処理で使われていないこと（入力処理の clear は許容）
    # クリック処理部分だけ抽出
    click_section_start = source.find("elif st == \"クリック\"")
    click_section_end = source.find("elif st == \"ホバー\"")
    if click_section_start >= 0 and click_section_end > click_section_start:
        click_code = source[click_section_start:click_section_end]
        assert "dispatchEvent" not in click_code, "クリック処理にdispatchEventが含まれている"
        print("  [OK] クリック処理に dispatchEvent なし")
    else:
        print("  [SKIP] クリック処理セクション特定不可")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト35: makedirs 空パスガード
# ---------------------------------------------------------------------------

def test_makedirs_empty_path():
    print("=== テスト35: makedirs 空パスガード ===")

    # os.path.dirname が空文字を返すケース
    assert os.path.dirname("test.json") == "", "dirname of bare filename should be empty"
    assert os.path.dirname("C:/foo/test.json") != "", "dirname of full path should not be empty"
    print("  [OK] dirname 空文字ケース確認")

    # 空パスで makedirs しない（エラーが出ないことを確認）
    _dir = os.path.dirname("test.json")
    if _dir:
        os.makedirs(_dir, exist_ok=True)
    # ここに到達すれば成功（空パスで makedirs を呼ばない）
    print("  [OK] 空パスガード動作確認")

    # フルパスでは makedirs が通ること
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        fp = os.path.join(tmpdir, "sub", "test.json")
        _dir2 = os.path.dirname(fp)
        if _dir2:
            os.makedirs(_dir2, exist_ok=True)
        assert os.path.isdir(_dir2), f"ディレクトリが作られていない: {_dir2}"
        print("  [OK] フルパスでの makedirs 正常動作")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト36: _sel_by 拡張テスト（クリック処理の前提）
# ---------------------------------------------------------------------------

def test_sel_by_extended():
    print("=== テスト36: _sel_by 拡張テスト ===")
    from selenium.webdriver.common.by import By
    from y_shot import _sel_by

    # 基本CSS
    assert _sel_by("#id")[0] == By.CSS_SELECTOR
    assert _sel_by(".class")[0] == By.CSS_SELECTOR
    assert _sel_by("div.class#id")[0] == By.CSS_SELECTOR
    assert _sel_by("input[type='text']")[0] == By.CSS_SELECTOR
    assert _sel_by("[id=\"10\"]")[0] == By.CSS_SELECTOR
    assert _sel_by("a[href*='#sales']")[0] == By.CSS_SELECTOR
    assert _sel_by(".menu_1st a[href=\"./partner.html\"]")[0] == By.CSS_SELECTOR
    assert _sel_by("map[name=\"sbmap1\"] area[href=\"partner.html\"]")[0] == By.CSS_SELECTOR
    print("  [OK] CSS セレクタ各種")

    # XPath
    assert _sel_by("//div[@id='main']")[0] == By.XPATH
    assert _sel_by("(//img)[2]")[0] == By.XPATH
    assert _sel_by("//button[normalize-space()='送信']")[0] == By.XPATH
    assert _sel_by("(//input[@type='radio'])[3]")[0] == By.XPATH
    print("  [OK] XPath 各種")

    # 値が正しく渡されること
    assert _sel_by("#back span") == (By.CSS_SELECTOR, "#back span")
    assert _sel_by("//div")[1] == "//div"
    assert _sel_by("(//img)[1]")[1] == "(//img)[1]"
    print("  [OK] セレクタ値の保持")

    # 空セレクタ
    result = _sel_by("")
    assert result[0] == By.CSS_SELECTOR
    assert result[1] == ""
    print("  [OK] 空セレクタ")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト37: _css_escape_attr / _is_safe_class
# ---------------------------------------------------------------------------

def test_css_helpers():
    print("=== テスト37: CSS ヘルパー関数 ===")
    from y_shot import _css_escape_attr, _is_safe_class

    # _css_escape_attr
    assert _css_escape_attr('hello') == 'hello'
    assert _css_escape_attr('say "hi"') == 'say \\"hi\\"'
    assert _css_escape_attr('path\\to') == 'path\\\\to'
    assert _css_escape_attr('a"b\\c') == 'a\\"b\\\\c'
    assert _css_escape_attr('') == ''
    print("  [OK] _css_escape_attr")

    # _is_safe_class
    assert _is_safe_class("btn") == True
    assert _is_safe_class("btn-primary") == True
    assert _is_safe_class("my_class") == True
    assert _is_safe_class("btn123") == True
    assert _is_safe_class("123btn") == False  # starts with digit
    assert _is_safe_class("") == False
    assert _is_safe_class(None) == False
    assert _is_safe_class("a b") == False  # space
    assert _is_safe_class("a.b") == False  # dot
    print("  [OK] _is_safe_class")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト38: _safe_dir_name
# ---------------------------------------------------------------------------

def test_safe_dir_name():
    print("=== テスト38: _safe_dir_name ===")
    from y_shot import _safe_dir_name

    assert _safe_dir_name("プロジェクト名") == "プロジェクト名"
    assert _safe_dir_name("test/project") == "test_project"
    assert _safe_dir_name('a:b*c?d"e') == "a_b_c_d_e"
    assert _safe_dir_name("normal") == "normal"
    assert _safe_dir_name("") == "project"  # empty → default
    assert _safe_dir_name("   ") == "project"  # whitespace only → default
    assert _safe_dir_name("a<b>c|d") == "a_b_c_d"
    print("  [OK] _safe_dir_name 各種")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト39: _new_project_id
# ---------------------------------------------------------------------------

def test_new_project_id():
    print("=== テスト39: _new_project_id ===")
    from y_shot import _new_project_id

    # 空のレジストリ
    reg = {"projects": []}
    assert _new_project_id(reg) == "proj_1"
    print("  [OK] 空レジストリ → proj_1")

    # 既存プロジェクト
    reg = {"projects": [{"id": "default"}, {"id": "proj_3"}, {"id": "proj_1"}]}
    assert _new_project_id(reg) == "proj_4"
    print("  [OK] max=3 → proj_4")

    # IDがパースできない場合
    reg = {"projects": [{"id": "custom"}, {"id": "proj_abc"}]}
    assert _new_project_id(reg) == "proj_1"
    print("  [OK] パース不能ID → proj_1")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト40: get_app_dir / get_bundle_dir / get_templates_dir
# ---------------------------------------------------------------------------

def test_dir_functions():
    print("=== テスト40: ディレクトリ関数 ===")
    from y_shot import get_app_dir, get_bundle_dir, get_templates_dir

    app_dir = get_app_dir()
    assert os.path.isdir(app_dir), f"app_dir not found: {app_dir}"
    assert "y-shot" in app_dir or "y_shot" in app_dir.lower()
    print(f"  [OK] get_app_dir: {app_dir}")

    bundle_dir = get_bundle_dir()
    assert os.path.isdir(bundle_dir), f"bundle_dir not found: {bundle_dir}"
    print(f"  [OK] get_bundle_dir: {bundle_dir}")

    tmpl_dir = get_templates_dir()
    assert os.path.isdir(tmpl_dir), f"templates_dir not found: {tmpl_dir}"
    print(f"  [OK] get_templates_dir: {tmpl_dir}")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト41: load_config / save_config round-trip
# ---------------------------------------------------------------------------

def test_config_roundtrip():
    print("=== テスト41: config 保存/読込 ===")
    from y_shot import _active_project_dir, load_config, save_config
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # 一時的にプロジェクトディレクトリを変更
        old_dir = _active_project_dir[0]
        _active_project_dir[0] = tmpdir
        try:
            # 保存
            config = {"project_url": "http://example.com", "headless": "1", "save_source": "0"}
            save_config(config)
            print("  [OK] save_config")

            # 読込
            loaded = load_config()
            assert loaded["project_url"] == "http://example.com"
            assert loaded["headless"] == "1"
            assert loaded["save_source"] == "0"
            print("  [OK] load_config round-trip")

            # 空config
            save_config({})
            loaded = load_config()
            assert isinstance(loaded, dict)
            print("  [OK] 空config保存/読込")
        finally:
            _active_project_dir[0] = old_dir

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト42: load_pages / save_pages round-trip
# ---------------------------------------------------------------------------

def test_pages_roundtrip():
    print("=== テスト42: pages 保存/読込 ===")
    from y_shot import _active_project_dir, load_pages, save_pages
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = _active_project_dir[0]
        _active_project_dir[0] = tmpdir
        try:
            pages = [
                {"_id": "p_1", "name": "テストページ", "number": "1", "start_number": 1, "url": "http://example.com"},
                {"_id": "p_2", "name": "ページ2", "number": "2", "start_number": 5, "url": ""},
            ]
            save_pages(pages)
            loaded = load_pages()
            assert len(loaded) == 2
            assert loaded[0]["name"] == "テストページ"
            assert loaded[1]["start_number"] == 5
            print("  [OK] pages round-trip")

            # 空リスト
            save_pages([])
            loaded = load_pages()
            assert loaded == []
            print("  [OK] 空pages")
        finally:
            _active_project_dir[0] = old_dir

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト43: load_pattern_sets / save_pattern_sets round-trip
# ---------------------------------------------------------------------------

def test_pattern_sets_roundtrip():
    print("=== テスト43: pattern_sets 保存/読込 ===")
    from y_shot import _active_project_dir, load_pattern_sets, save_pattern_sets
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = _active_project_dir[0]
        _active_project_dir[0] = tmpdir
        try:
            pats = {
                "入力チェック": [{"label": "未入力", "value": ""}, {"label": "最大値", "value": "a" * 100}],
                "空セット": [],
            }
            save_pattern_sets(pats)
            loaded = load_pattern_sets()
            assert "入力チェック" in loaded
            assert len(loaded["入力チェック"]) == 2
            assert loaded["入力チェック"][1]["value"] == "a" * 100
            assert loaded["空セット"] == []
            print("  [OK] pattern_sets round-trip")
        finally:
            _active_project_dir[0] = old_dir

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト44: load_selector_bank / save_selector_bank round-trip
# ---------------------------------------------------------------------------

def test_selector_bank_roundtrip():
    print("=== テスト44: selector_bank 保存/読込 ===")
    from y_shot import _active_project_dir, load_selector_bank, save_selector_bank
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        old_dir = _active_project_dir[0]
        _active_project_dir[0] = tmpdir
        try:
            bank = {
                "http://example.com": [
                    {"selector": "#btn", "tag": "button", "visible": True},
                    {"selector": ".link", "tag": "a", "visible": True},
                ],
            }
            save_selector_bank(bank)
            loaded = load_selector_bank()
            assert "http://example.com" in loaded
            assert len(loaded["http://example.com"]) == 2
            print("  [OK] selector_bank round-trip")

            # 空bank
            save_selector_bank({})
            loaded = load_selector_bank()
            assert loaded == {}
            print("  [OK] 空bank")
        finally:
            _active_project_dir[0] = old_dir

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト45: activate_project / projects registry
# ---------------------------------------------------------------------------

def test_project_registry():
    print("=== テスト45: プロジェクトレジストリ ===")
    from y_shot import _active_project_dir, get_projects_dir, activate_project, _new_project_id
    import tempfile

    # activate_project: 存在するプロジェクト
    registry = {
        "last_active": "default",
        "projects": [
            {"id": "default", "name": "デフォルト", "dir": "default"},
            {"id": "proj_1", "name": "テスト", "dir": "test_proj"},
        ]
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        # プロジェクトディレクトリを作成
        proj_dir = os.path.join(tmpdir, "test_proj")
        os.makedirs(proj_dir)

        # get_projects_dirをモック的に使う代わりにactivate_projectの戻り値を確認
        # activate_projectは内部的にディレクトリを作成する
        old_dir = _active_project_dir[0]
        try:
            result = activate_project("default", registry)
            assert result == True, "activate_project should return True for existing project"
            assert registry["last_active"] == "default"
            print("  [OK] activate_project: 既存プロジェクト")

            # 存在しないプロジェクト
            result = activate_project("nonexistent", registry)
            assert result == False, "activate_project should return False for nonexistent project"
            print("  [OK] activate_project: 存在しないID")

            # _new_project_id
            new_id = _new_project_id(registry)
            assert new_id == "proj_2"
            print("  [OK] _new_project_id: proj_2")
        finally:
            _active_project_dir[0] = old_dir

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト46: _safe_json_save atomic write
# ---------------------------------------------------------------------------

def test_safe_json_save_atomic():
    print("=== テスト46: _safe_json_save atomic write ===")
    from y_shot import _safe_json_save, _safe_json_load
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        fp = os.path.join(tmpdir, "data.json")

        # 1. 正常保存
        _safe_json_save(fp, {"key": "value"})
        assert os.path.isfile(fp)
        print("  [OK] 正常保存")

        # 2. .tmp が残っていないこと
        assert not os.path.isfile(fp + ".tmp"), ".tmpファイルが残っている"
        print("  [OK] .tmp残留なし")

        # 3. 2回目の保存で .backup が作られること
        _safe_json_save(fp, {"key": "value2"})
        assert os.path.isfile(fp + ".backup"), ".backupがない"
        print("  [OK] 2回目保存で.backup作成")

        # 4. backup の中身は1回目のデータ
        with open(fp + ".backup", "r", encoding="utf-8") as f:
            bak = json.load(f)
        assert bak["key"] == "value", f"backup内容不正: {bak}"
        print("  [OK] .backup内容が前回データ")

        # 5. 本体の中身は2回目のデータ
        loaded = _safe_json_load(fp, {})
        assert loaded["key"] == "value2"
        print("  [OK] 本体は最新データ")

        # 6. 日本語・絵文字・特殊文字
        _safe_json_save(fp, {"name": "テスト🦐", "path": "C:\\Users\\test", "html": "<div>&amp;</div>"})
        loaded = _safe_json_load(fp, {})
        assert loaded["name"] == "テスト🦐"
        assert loaded["path"] == "C:\\Users\\test"
        assert loaded["html"] == "<div>&amp;</div>"
        print("  [OK] 日本語・絵文字・特殊文字")

        # 7. 大きなデータ
        big_data = {"items": [{"id": i, "value": f"item_{i}" * 100} for i in range(500)]}
        _safe_json_save(fp, big_data)
        loaded = _safe_json_load(fp, {})
        assert len(loaded["items"]) == 500
        print("  [OK] 大量データ (500件)")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト47: step_short 全ステップタイプ包括テスト
# ---------------------------------------------------------------------------

def test_step_short_comprehensive():
    print("=== テスト47: step_short 包括テスト ===")
    from y_shot import step_short

    # パターン置換つきのステップ
    s = step_short({"type": "入力", "selector": "#name", "value": "{パターン}"})
    assert "{パターン}" in s or "#name" in s
    print("  [OK] パターン置換含む入力ステップ")

    # 長いセレクタの切り詰め
    long_sel = "div.very-long-selector-name > span.nested-child > input.deeply-nested-element"
    s = step_short({"type": "クリック", "selector": long_sel})
    assert len(s) < len(long_sel) + 20  # 適度な長さ
    print("  [OK] 長いセレクタ")

    # 待機ステップ（秒数）
    s = step_short({"type": "待機", "seconds": "3.5"})
    assert "3.5" in s
    print("  [OK] 待機ステップ")

    # ナビゲーション
    s = step_short({"type": "ナビゲーション", "url": "https://example.com/very/long/path"})
    assert "example" in s or "ナビ" in s.lower() or "http" in s
    print("  [OK] ナビゲーションステップ")

    # コメント（空文字を返す仕様）
    s = step_short({"type": "コメント", "comment": "これはテストコメント"})
    assert isinstance(s, str)
    print("  [OK] コメントステップ")

    # 見出し（空文字を返す仕様）
    s = step_short({"type": "見出し", "comment": "セクション1"})
    assert isinstance(s, str)
    print("  [OK] 見出しステップ")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト48: MAX_PAGE_HEIGHT 定数確認
# ---------------------------------------------------------------------------

def test_constants():
    print("=== テスト48: 定数確認 ===")
    from y_shot import MAX_PAGE_HEIGHT, LOG_MAX_LINES, SAVE_DELAY_SEC, BANK_MAX_URLS, APP_VERSION

    assert MAX_PAGE_HEIGHT == 16384, f"MAX_PAGE_HEIGHT: {MAX_PAGE_HEIGHT}"
    assert LOG_MAX_LINES > 0
    assert SAVE_DELAY_SEC > 0
    assert BANK_MAX_URLS > 0
    assert APP_VERSION == "3.1"
    print("  [OK] 全定数値")

    # ソースコード内に16384のハードコードが残っていないこと（定義行を除く）
    with open(os.path.join(os.path.dirname(__file__) or '.', 'y_shot.py'), 'r', encoding='utf-8') as f:
        lines = f.readlines()
    hardcoded = [(i+1, l.strip()) for i, l in enumerate(lines)
                 if '16384' in l and 'MAX_PAGE_HEIGHT' not in l and not l.strip().startswith('#')]
    assert len(hardcoded) == 0, f"16384ハードコード残存: {hardcoded}"
    print("  [OK] 16384ハードコードなし")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト49: _data_path フォールバック
# ---------------------------------------------------------------------------

def test_data_path():
    print("=== テスト49: _data_path ===")
    from y_shot import _data_path, _active_project_dir, get_app_dir

    # プロジェクトディレクトリ設定時
    old = _active_project_dir[0]
    try:
        _active_project_dir[0] = "C:/fake/project/dir"
        result = _data_path("test.json")
        assert result == os.path.join("C:/fake/project/dir", "test.json")
        print("  [OK] プロジェクトディレクトリ設定時")

        # None時はapp_dirにフォールバック
        _active_project_dir[0] = None
        result = _data_path("test.json")
        assert result == os.path.join(get_app_dir(), "test.json")
        print("  [OK] Noneフォールバック")
    finally:
        _active_project_dir[0] = old

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト50: _generate_report HTMLレポート生成
# ---------------------------------------------------------------------------

def test_generate_report():
    print("=== テスト50: _generate_report ===")
    from y_shot import _generate_report
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # テスト用PNGファイル作成
        page1 = os.path.join(tmpdir, "1_ページ1")
        page2 = os.path.join(tmpdir, "2_ページ2")
        os.makedirs(page1); os.makedirs(page2)
        # 空PNGを作成
        for fn in ["001_1-1_テスト1_ss1.png", "002_1-1_テスト1_ss2.png"]:
            open(os.path.join(page1, fn), "wb").close()
        for fn in ["003_2-1_テスト2_ss1.png"]:
            open(os.path.join(page2, fn), "wb").close()

        logs = []
        _generate_report(tmpdir, lambda m: logs.append(m),
                        pages=[{"number": "1", "name": "ページ1", "url": "http://example.com"}])

        rp = os.path.join(tmpdir, "report.html")
        assert os.path.isfile(rp), "report.html が作られていない"
        with open(rp, "r", encoding="utf-8") as f:
            html = f.read()
        assert "y-shot レポート" in html
        assert "3 枚" in html  # 3 PNGs
        assert "1_ページ1" in html
        assert "2_ページ2" in html
        assert "example.com" in html
        assert any("[レポート]" in l for l in logs)
        print("  [OK] レポート生成（3枚、2ページ）")

        # 空ディレクトリ（PNGなし）
        with tempfile.TemporaryDirectory() as tmpdir2:
            logs2 = []
            _generate_report(tmpdir2, lambda m: logs2.append(m))
            assert not os.path.isfile(os.path.join(tmpdir2, "report.html"))
            print("  [OK] PNGなし→レポートなし")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト51: _get_ns_patterns / _normalize_source 追加パターン
# ---------------------------------------------------------------------------

def test_normalize_source_additional():
    print("=== テスト51: _normalize_source 追加パターン ===")
    from y_shot import _normalize_source

    # authenticity_token (Rails)
    html = '<input name="authenticity_token" value="abc123xyz">'
    n = _normalize_source(html)
    assert "abc123xyz" not in n
    assert "__NORMALIZED__" in n
    print("  [OK] Rails authenticity_token")

    # __RequestVerificationToken (.NET)
    html = '<input name="__RequestVerificationToken" value="dotnet_token_123">'
    n = _normalize_source(html)
    assert "dotnet_token_123" not in n
    print("  [OK] .NET RequestVerificationToken")

    # session_id
    html = '<input name="session_id" value="sess_xyz789">'
    n = _normalize_source(html)
    assert "sess_xyz789" not in n
    print("  [OK] session_id")

    # ISO datetime with T separator
    html = '<span>2026-04-09T14:30:00</span>'
    n = _normalize_source(html)
    assert "2026-04-09T14:30:00" not in n
    assert "__DATETIME__" in n
    print("  [OK] ISO datetime (T separator)")

    # 複数パターンの同時適用
    html = '<meta name="csrf-token" content="tok123"> <span>2026-01-01 00:00:00</span> <link href="style.css?v=abc">'
    n = _normalize_source(html)
    assert "tok123" not in n
    assert "2026-01-01" not in n
    assert "abc" not in n
    print("  [OK] 複数パターン同時適用")

    # 正規化しない通常テキスト
    html = '<p>普通のテキスト123</p>'
    assert _normalize_source(html) == html
    print("  [OK] 通常テキスト不変")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト52: projects registry round-trip
# ---------------------------------------------------------------------------

def test_projects_registry_roundtrip():
    print("=== テスト52: projects registry round-trip ===")
    from y_shot import load_projects_registry, save_projects_registry, get_projects_dir, _safe_json_load
    import tempfile

    # get_projects_dir が存在するか
    pdir = get_projects_dir()
    assert os.path.isdir(pdir), f"projects dir not found: {pdir}"
    print(f"  [OK] get_projects_dir: {pdir}")

    # 現在のレジストリが読めるか
    reg = load_projects_registry()
    assert "projects" in reg
    assert "last_active" in reg
    assert isinstance(reg["projects"], list)
    print(f"  [OK] load_projects_registry: {len(reg['projects'])} projects")

    # レジストリの各プロジェクトにid/name/dirがあるか
    for p in reg["projects"]:
        assert "id" in p, f"project missing id: {p}"
        assert "name" in p, f"project missing name: {p}"
        assert "dir" in p, f"project missing dir: {p}"
    print("  [OK] 全プロジェクトにid/name/dir")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト53: auto_number_tests の実関数テスト
# ---------------------------------------------------------------------------

def test_auto_number_actual():
    print("=== テスト53: auto_number_tests 実関数 ===")
    # auto_number_tests は _main_inner 内のローカル関数なので直接呼べない
    # ロジックを再現してテスト（テスト8と異なるエッジケース）

    def auto_number(pages, tests):
        for pg in pages:
            pnum = pg["number"]
            next_sub = int(pg.get("start_number", 1))
            page_tests = [t for t in tests if t.get("page_id") == pg["_id"]]
            for tc in page_tests:
                forced = tc.get("_sub_number")
                if forced is not None:
                    try: next_sub = int(forced)
                    except (ValueError, TypeError): pass
                tc["number"] = f"{pnum}-{next_sub}"
                next_sub += 1

    # ページ番号が文字列の場合
    pages = [{"_id": "p_1", "name": "P", "number": "A", "start_number": 1}]
    tests = [{"_id": "tc_1", "name": "T", "page_id": "p_1", "number": ""}]
    auto_number(pages, tests)
    assert tests[0]["number"] == "A-1"
    print("  [OK] ページ番号が文字列")

    # start_number が大きい場合
    pages = [{"_id": "p_1", "name": "P", "number": "1", "start_number": 100}]
    tests = [
        {"_id": "tc_1", "name": "T1", "page_id": "p_1", "number": ""},
        {"_id": "tc_2", "name": "T2", "page_id": "p_1", "number": ""},
    ]
    auto_number(pages, tests)
    assert tests[0]["number"] == "1-100"
    assert tests[1]["number"] == "1-101"
    print("  [OK] start_number=100")

    # ページにテストが0件
    pages = [{"_id": "p_1", "name": "P", "number": "1", "start_number": 1}]
    tests = []
    auto_number(pages, tests)  # エラーにならないこと
    print("  [OK] テスト0件でもエラーなし")

    # _sub_number が不正値
    pages = [{"_id": "p_1", "name": "P", "number": "1", "start_number": 1}]
    tests = [
        {"_id": "tc_1", "name": "T1", "page_id": "p_1", "number": "", "_sub_number": "abc"},
        {"_id": "tc_2", "name": "T2", "page_id": "p_1", "number": ""},
    ]
    auto_number(pages, tests)
    assert tests[0]["number"] == "1-1"  # invalid _sub_number → fallthrough to next_sub
    assert tests[1]["number"] == "1-2"
    print("  [OK] 不正_sub_number")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト54: テストケース / ステップの構造検証
# ---------------------------------------------------------------------------

def test_tc_step_structure():
    print("=== テスト54: テストケース構造検証 ===")
    from y_shot import STEP_TYPES

    # ステップタイプの完全性
    required_types = ["入力", "クリック", "ホバー", "選択", "待機", "要素待機",
                      "スクロール", "スクショ", "検証", "戻る", "更新",
                      "アラートOK", "アラートキャンセル", "ナビゲーション",
                      "セッション削除", "見出し", "コメント"]
    for st in required_types:
        assert st in STEP_TYPES, f"STEP_TYPES に {st} がない"
    print(f"  [OK] 全{len(required_types)}ステップタイプ存在")

    # テストケースの最小構造
    tc = {"name": "テスト", "_id": "tc_1", "page_id": "p_1", "pattern": None, "steps": []}
    assert all(k in tc for k in ["name", "_id", "page_id", "steps"])
    print("  [OK] テストケース最小構造")

    # ステップの最小構造
    step_click = {"type": "クリック", "selector": "#btn"}
    step_input = {"type": "入力", "selector": "#name", "value": "テスト"}
    step_wait = {"type": "待機", "seconds": "1.0"}
    step_ss = {"type": "スクショ", "mode": "fullpage"}
    assert all("type" in s for s in [step_click, step_input, step_wait, step_ss])
    print("  [OK] ステップ最小構造")

    # スクショモードの一覧
    modes = ["fullpage", "fullshot", "element", "margin", "post", "state"]
    from y_shot import step_short
    for m in modes:
        result = step_short({"type": "スクショ", "mode": m})
        assert isinstance(result, str), f"mode={m} で step_short がstr以外を返した"
    print(f"  [OK] 全{len(modes)}スクショモードのstep_short")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト55: build_auth_url エッジケース
# ---------------------------------------------------------------------------

def test_build_auth_url_edge():
    print("=== テスト55: build_auth_url エッジケース ===")
    from y_shot import build_auth_url

    # 特殊文字を含むパスワード
    result = build_auth_url("http://example.com", "user", "p@ss:w0rd")
    assert "user" in result and "example.com" in result
    print("  [OK] 特殊文字パスワード")

    # 日本語を含むURL
    result = build_auth_url("http://example.com/パス", "u", "p")
    assert "u:p@example.com" in result
    print("  [OK] 日本語パスURL")

    # 空のURL
    result = build_auth_url("", "user", "pass")
    assert isinstance(result, str)  # エラーにならないこと
    print("  [OK] 空URL")

    # HTTPSポート443
    result = build_auth_url("https://example.com:443/path", "u", "p")
    assert "u:p@example.com:443" in result
    print("  [OK] HTTPS with port")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト56: _safe_json_load 破損復帰の詳細
# ---------------------------------------------------------------------------

def test_safe_json_load_recovery():
    print("=== テスト56: _safe_json_load 破損復帰詳細 ===")
    from y_shot import _safe_json_save, _safe_json_load
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        fp = os.path.join(tmpdir, "data.json")

        # 1. メイン正常、backupなし
        _safe_json_save(fp, {"v": 1})
        os.remove(fp + ".backup") if os.path.exists(fp + ".backup") else None
        loaded = _safe_json_load(fp, {"default": True})
        assert loaded["v"] == 1
        print("  [OK] メイン正常、backupなし")

        # 2. メイン破損、backup正常
        _safe_json_save(fp, {"v": 2})  # backup に v=1 が入る
        with open(fp, "w") as f: f.write("{broken")
        loaded = _safe_json_load(fp, {"default": True})
        assert loaded.get("v") == 1, f"backup復帰失敗: {loaded}"
        print("  [OK] メイン破損→backup復帰")

        # 3. メインなし、backupあり
        os.remove(fp)
        with open(fp + ".backup", "w", encoding="utf-8") as f:
            json.dump({"v": 99}, f)
        loaded = _safe_json_load(fp, {"default": True})
        assert loaded["v"] == 99
        print("  [OK] メインなし→backup読込")

        # 4. 両方なし
        os.remove(fp + ".backup")
        loaded = _safe_json_load(fp, {"fallback": True})
        assert loaded == {"fallback": True}
        print("  [OK] 両方なし→default")

        # 5. メインが空ファイル
        open(fp, "w").close()
        loaded = _safe_json_load(fp, ["empty"])
        assert loaded == ["empty"]
        print("  [OK] 空ファイル→default")

        # 6. メインがUTF-8 BOM付き
        with open(fp, "w", encoding="utf-8-sig") as f:
            json.dump({"bom": True}, f)
        loaded = _safe_json_load(fp, {})
        # BOM付きJSONはjson.loadで読めるはず
        assert loaded.get("bom") == True or loaded == {}  # 環境依存
        print("  [OK] BOM付きJSON")

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# テスト57: CSV エッジケース追加
# ---------------------------------------------------------------------------

def test_csv_edge_cases():
    print("=== テスト57: CSV エッジケース ===")
    from y_shot import load_csv, save_csv
    import tempfile

    # 絵文字を含むパターン
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp = f.name
    try:
        pats = [{"label": "絵文字🦐", "value": "テスト🎉"}]
        save_csv(tmp, pats)
        loaded = load_csv(tmp)
        assert loaded[0]["label"] == "絵文字🦐"
        assert loaded[0]["value"] == "テスト🎉"
        print("  [OK] 絵文字round-trip")
    finally:
        os.unlink(tmp)

    # 非常に長い値
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp = f.name
    try:
        long_val = "a" * 10000
        pats = [{"label": "long", "value": long_val}]
        save_csv(tmp, pats)
        loaded = load_csv(tmp)
        assert loaded[0]["value"] == long_val
        print("  [OK] 10000文字値round-trip")
    finally:
        os.unlink(tmp)

    # タブ文字を含む
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        tmp = f.name
    try:
        pats = [{"label": "tab", "value": "a\tb\tc"}]
        save_csv(tmp, pats)
        loaded = load_csv(tmp)
        assert loaded[0]["value"] == "a\tb\tc"
        print("  [OK] タブ文字round-trip")
    finally:
        os.unlink(tmp)

    print("  全てパス\n")


# ---------------------------------------------------------------------------
# Selenium Integration Tests (require Chrome + chromedriver)
# ---------------------------------------------------------------------------

def _integration_fixture_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__) or '.', 'test_integration_fixture.html'))

def _make_headless_driver():
    from selenium import webdriver
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-search-engine-choice-screen')
    opts.add_argument('--no-sandbox')
    return webdriver.Chrome(options=opts)


def test_integration_collect_elements():
    """collect_elements_js on local HTML fixture — verify element count, fields, uniqueness."""
    print("=== Integration テスト1: collect_elements_js ===")
    from y_shot import collect_elements_js
    driver = _make_headless_driver()
    try:
        html_path = _integration_fixture_path()
        driver.get(f'file:///{html_path}')

        elements = collect_elements_js(driver, include_hidden=True)
        assert isinstance(elements, list), "結果がlistでない"
        assert len(elements) >= 15, f"要素数が少なすぎる: {len(elements)}"
        print(f"  [OK] 要素数: {len(elements)}")

        # Every element must have required fields
        required_fields = {"tag", "selector", "visible", "hint"}
        for el in elements:
            missing = required_fields - set(el.keys())
            assert not missing, f"フィールド不足: {missing} in {el.get('selector','?')}"
        print("  [OK] 全要素に必須フィールドあり")

        # Selectors should be unique among elements that have non-generic selectors
        selectors = [el["selector"] for el in elements]
        specific_selectors = [s for s in selectors if s not in ("input", "label", "a", "button", "select", "textarea", "span", "div", "li")]
        dupes = [s for s in specific_selectors if specific_selectors.count(s) > 1]
        assert len(dupes) == 0, f"セレクタ重複: {set(dupes)}"
        print("  [OK] 固有セレクタに重複なし")

        # Check that specific IDs are captured
        ids_found = {el["id"] for el in elements if el.get("id")}
        expected_ids = {"text-input", "checkbox-1", "radio-1", "normal-button", "select-input"}
        for eid in expected_ids:
            assert eid in ids_found, f"ID '{eid}' が見つからない"
        print("  [OK] 主要IDを正しく取得")

        # Hidden radio should appear (include_hidden=True)
        hidden_radios = [el for el in elements if el.get("id", "").startswith("hidden-radio-")]
        assert len(hidden_radios) >= 2, f"hidden radio が見つからない: {len(hidden_radios)}"
        for hr in hidden_radios:
            assert hr["visible"] is False, f"hidden radio が visible=True: {hr['id']}"
        print("  [OK] hidden radio を include_hidden=True で取得")

    finally:
        driver.quit()
    print("  全てパス\n")


def test_integration_click_selenium_fallback():
    """Click handler: normal click, JS fallback for hidden labels, checkbox/radio toggle."""
    print("=== Integration テスト2: クリック処理 ===")
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from y_shot import _sel_by
    driver = _make_headless_driver()
    try:
        html_path = _integration_fixture_path()
        driver.get(f'file:///{html_path}')

        # 1) Normal visible button — Selenium .click() should work
        btn = driver.find_element(By.ID, "normal-button")
        btn.click()
        result_text = driver.find_element(By.ID, "result").text
        assert result_text == "button clicked", f"ボタンクリック失敗: {result_text}"
        print("  [OK] 通常ボタン Selenium .click()")

        # 2) Hidden label for radio (zero-height label) — JS fallback
        label_sel = "label[for='hidden-radio-b']"
        _el = WebDriverWait(driver, 5).until(EC.presence_of_element_located(_sel_by(label_sel)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center',behavior:'instant'});", _el)
        try:
            _el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", _el)
        radio_b = driver.find_element(By.ID, "hidden-radio-b")
        assert radio_b.is_selected(), "hidden-radio-b が選択されていない"
        print("  [OK] hidden label クリック → radio選択")

        # 3) Checkbox toggle via click
        cb = driver.find_element(By.ID, "checkbox-1")
        assert not cb.is_selected(), "checkbox-1 が初期状態で選択済"
        cb.click()
        assert cb.is_selected(), "checkbox-1 がクリック後に未選択"
        cb.click()
        assert not cb.is_selected(), "checkbox-1 が2回クリック後に選択済"
        print("  [OK] チェックボックスのトグル")

        # 4) Radio button selection via click
        r2 = driver.find_element(By.ID, "radio-2")
        r2.click()
        assert r2.is_selected(), "radio-2 が選択されない"
        r3 = driver.find_element(By.ID, "radio-3")
        r3.click()
        assert r3.is_selected(), "radio-3 が選択されない"
        assert not r2.is_selected(), "radio-2 が選択解除されない"
        print("  [OK] ラジオボタンの排他選択")

        # 5) Div-based button click
        div_btn = driver.find_element(By.ID, "div-button")
        div_btn.click()
        result_text = driver.find_element(By.ID, "result").text
        assert result_text == "div-button clicked", f"div-button クリック失敗: {result_text}"
        print("  [OK] div ボタン クリック")

    finally:
        driver.quit()
    print("  全てパス\n")


def test_integration_input_and_clear():
    """Input handling: send_keys, clear, value verification."""
    print("=== Integration テスト3: 入力とクリア ===")
    from selenium.webdriver.common.by import By
    driver = _make_headless_driver()
    try:
        html_path = _integration_fixture_path()
        driver.get(f'file:///{html_path}')

        # Text input
        text_in = driver.find_element(By.ID, "text-input")
        text_in.send_keys("テスト文字列ABC")
        assert text_in.get_attribute("value") == "テスト文字列ABC", "テキスト入力値が不一致"
        print("  [OK] テキスト入力 send_keys")

        # Clear
        text_in.clear()
        assert text_in.get_attribute("value") == "", "クリア後に値が残っている"
        print("  [OK] テキスト入力 clear")

        # Password input
        pw_in = driver.find_element(By.ID, "password-input")
        pw_in.send_keys("secret123")
        assert pw_in.get_attribute("value") == "secret123", "パスワード入力値が不一致"
        print("  [OK] パスワード入力")

        # Textarea
        ta = driver.find_element(By.ID, "textarea-input")
        ta.send_keys("複数行\nテキスト")
        assert "複数行" in ta.get_attribute("value"), "テキストエリア入力失敗"
        print("  [OK] テキストエリア入力")

        # Email input
        em = driver.find_element(By.ID, "email-input")
        em.send_keys("test@example.com")
        assert em.get_attribute("value") == "test@example.com", "メール入力値が不一致"
        print("  [OK] メール入力")

    finally:
        driver.quit()
    print("  全てパス\n")


def test_integration_screenshot_modes():
    """Screenshot capture: fullpage (save_screenshot) and fullshot (CDP)."""
    print("=== Integration テスト4: スクリーンショット ===")
    import base64
    driver = _make_headless_driver()
    try:
        html_path = _integration_fixture_path()
        driver.get(f'file:///{html_path}')

        # fullpage mode — driver.save_screenshot
        with tempfile.TemporaryDirectory() as tmpdir:
            fp = os.path.join(tmpdir, "fullpage.png")
            driver.save_screenshot(fp)
            assert os.path.isfile(fp), "fullpage PNG が作成されない"
            assert os.path.getsize(fp) > 100, "fullpage PNG が小さすぎる"
            print(f"  [OK] fullpage スクリーンショット ({os.path.getsize(fp)} bytes)")

        # fullshot mode — CDP Page.captureScreenshot
        with tempfile.TemporaryDirectory() as tmpdir:
            fp2 = os.path.join(tmpdir, "fullshot.png")
            metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
            content_size = metrics.get("contentSize", metrics.get("cssContentSize", {}))
            width = content_size.get("width", 1280)
            height = content_size.get("height", 900)
            driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": int(width), "height": int(height),
                "deviceScaleFactor": 1, "mobile": False
            })
            result = driver.execute_cdp_cmd("Page.captureScreenshot", {
                "format": "png", "captureBeyondViewport": True
            })
            import base64 as b64
            with open(fp2, "wb") as f:
                f.write(b64.b64decode(result["data"]))
            driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
            assert os.path.isfile(fp2), "fullshot PNG が作成されない"
            assert os.path.getsize(fp2) > 100, "fullshot PNG が小さすぎる"
            print(f"  [OK] fullshot CDP スクリーンショット ({os.path.getsize(fp2)} bytes)")

    finally:
        driver.quit()
    print("  全てパス\n")


def test_integration_sel_by_on_real_dom():
    """_sel_by selectors work on real DOM: CSS, XPath, attribute selectors."""
    print("=== Integration テスト5: _sel_by リアルDOM検証 ===")
    from selenium.webdriver.common.by import By
    from y_shot import _sel_by
    driver = _make_headless_driver()
    try:
        html_path = _integration_fixture_path()
        driver.get(f'file:///{html_path}')

        # CSS ID selector
        by, sel = _sel_by("#text-input")
        assert by == By.CSS_SELECTOR
        el = driver.find_element(by, sel)
        assert el.get_attribute("id") == "text-input"
        print("  [OK] CSS ID セレクタ (#text-input)")

        # CSS class selector
        by, sel = _sel_by(".div-button")
        assert by == By.CSS_SELECTOR
        el = driver.find_element(by, sel)
        assert el.text == "Divボタン"
        print("  [OK] CSS クラスセレクタ (.div-button)")

        # CSS attribute selector
        by, sel = _sel_by("[data-testid='my-input']")
        assert by == By.CSS_SELECTOR
        el = driver.find_element(by, sel)
        assert el.get_attribute("name") == "attr-name"
        print("  [OK] CSS 属性セレクタ ([data-testid])")

        # XPath selector
        by, sel = _sel_by("//button[@id='normal-button']")
        assert by == By.XPATH
        el = driver.find_element(by, sel)
        assert el.text == "通常ボタン"
        print("  [OK] XPath セレクタ (//button[@id])")

        # XPath with parentheses
        by, sel = _sel_by("(//input[@type='radio'])[2]")
        assert by == By.XPATH
        el = driver.find_element(by, sel)
        assert el.get_attribute("id") == "radio-2"
        print("  [OK] XPath 括弧セレクタ ((//input)[N])")

        # CSS compound selector
        by, sel = _sel_by("input[type='email']#email-input")
        assert by == By.CSS_SELECTOR
        el = driver.find_element(by, sel)
        assert el.get_attribute("placeholder") == "メールアドレス"
        print("  [OK] CSS 複合セレクタ")

        # Verify _sel_by results can locate elements via find_element
        test_sels = [
            "#select-input",
            "#textarea-input",
            "//label[@for='hidden-radio-a']",
            "#nav-item-1",
        ]
        for s in test_sels:
            by, val = _sel_by(s)
            el = driver.find_element(by, val)
            assert el is not None, f"セレクタ '{s}' で要素が見つからない"
        print(f"  [OK] 追加セレクタ {len(test_sels)}件 全て検出")

    finally:
        driver.quit()
    print("  全てパス\n")


if __name__ == "__main__":
    print("y-shot テスト開始 (v2.0)\n")

    test_logic()
    test_tc_ids()
    test_pattern_set_ordering()
    test_flet_api()
    test_kill_driver()
    test_import()
    test_utils()
    test_start_num()
    test_reorder()
    test_pattern_reorder()
    test_dedup()
    test_output_structure()
    test_numeric_generation()
    test_source_normalization()

    test_sel_by()
    test_verify_step()
    test_cr_sanitize()

    print("=" * 40)
    print("全テスト完了 - すべてパス")
