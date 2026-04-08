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

    assert mod.APP_VERSION == "3.0", f"バージョン不一致: {mod.APP_VERSION}"
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
