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

    assert mod.APP_VERSION == "1.8", f"バージョン不一致: {mod.APP_VERSION}"
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

    # Reproduce dedup logic
    _dedup = {}
    def is_dup(handler, old, new):
        now = _time.time()
        prev = _dedup.get(handler)
        if prev and now - prev < 0.5: return True
        _dedup[handler] = now; return False

    # 1回目は通す
    assert is_dup("pat", 1, 3) == False
    print("  [OK] 1回目は通過")

    # 即座の2回目はブロック (同じインデックスでも違うインデックスでも)
    assert is_dup("pat", 1, 3) == True
    print("  [OK] 2回目即座ブロック (同インデックス)")

    assert is_dup("pat", 1, 2) == True
    print("  [OK] 2回目即座ブロック (違うインデックス)")

    # 別ハンドラーは独立
    assert is_dup("step", 0, 1) == False
    print("  [OK] 別ハンドラーは独立")

    # 時間経過後は通す
    _dedup["pat"] = _time.time() - 1.0  # 1秒前に設定
    assert is_dup("pat", 2, 0) == False
    print("  [OK] 0.5秒後は通過")

    # 二重発火シミュレーション: 1回目は正しく移動、2回目はブロック
    pats = ["A", "B", "C", "D"]
    _dedup2 = {}
    def is_dup2(handler):
        now = _time.time()
        prev = _dedup2.get(handler)
        if prev and now - prev < 0.5: return True
        _dedup2[handler] = now; return False

    def sim_reorder(pats, old, new):
        if is_dup2("pat"): return  # blocked
        adj_new = new - 1 if new > old else new
        if old == adj_new: return
        pats.insert(adj_new, pats.pop(old))

    # Flet fires twice: move B(1) after C
    sim_reorder(pats, 1, 3)  # 1st fire: OK
    sim_reorder(pats, 1, 2)  # 2nd fire: different indices, but dedup blocks
    assert pats == ["A", "C", "B", "D"], f"Got {pats}"
    print("  [OK] 二重発火シミュレーション (2回目ブロック)")

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
    test_pattern_reorder()
    test_dedup()
    test_output_structure()
    test_numeric_generation()
    test_source_normalization()

    print("=" * 40)
    print("全テスト完了 - すべてパス")
