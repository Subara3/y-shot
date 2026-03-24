"""
y-shot: Web Screenshot Automation Tool  v1.3 (Flet)
  - Multiple test cases, each with own steps + pattern set reference
  - Multiple named pattern sets as shared components
"""

import csv, os, sys, json, threading, time
from datetime import datetime
from urllib.parse import urlparse, urlunparse
import flet as ft

APP_NAME = "y-shot"
APP_VERSION = "1.3"
APP_AUTHOR = "Yuri Norimatsu"

# ===================================================================
# Backend
# ===================================================================

def collect_elements_python(driver):
    from selenium.webdriver.common.by import By
    results, seen = [], set()
    css = ("input, textarea, select, button, a, [role='button'], [type='submit'], "
           "[type='image'], img[onclick], [onclick], li[id], span[id], div[onclick]")
    try: elements = driver.find_elements(By.CSS_SELECTOR, css)
    except: return results
    for el in elements:
        try:
            if not el.is_displayed():
                if (el.get_attribute("type") or "") not in ("radio","checkbox"): continue
            tag = el.tag_name.lower(); etype = el.get_attribute("type") or ""
            if etype == "hidden": continue
            eid = el.get_attribute("id") or ""; ename = el.get_attribute("name") or ""
            sel = _build_selector(driver, el, tag, eid, ename)
            if sel in seen: continue; seen.add(sel)
            hint = (el.get_attribute("placeholder") or el.get_attribute("alt") or
                    (el.text or "").strip()[:50] or (el.get_attribute("value") or "")[:30])
            results.append({"selector": sel, "tag": tag, "type": etype, "name": ename, "id": eid, "hint": hint})
        except: continue
    return results

def _build_selector(driver, el, tag, eid, ename):
    from selenium.webdriver.common.by import By
    if eid: return f"#{eid}"
    if ename:
        s = f'{tag}[name="{ename}"]'
        try:
            if len(driver.find_elements(By.CSS_SELECTOR, s)) == 1: return s
        except: pass
    etype = el.get_attribute("type") or ""
    if etype and ename:
        s = f'{tag}[type="{etype}"][name="{ename}"]'
        try:
            if len(driver.find_elements(By.CSS_SELECTOR, s)) == 1: return s
        except: pass
    classes = (el.get_attribute("class") or "").strip()
    if classes:
        cs = tag + "".join(f".{c}" for c in classes.split()[:2])
        try:
            if len(driver.find_elements(By.CSS_SELECTOR, cs)) == 1: return cs
        except: pass
    try:
        idx = driver.execute_script(
            "var e=arguments[0],p=e.parentElement;if(!p)return 0;"
            "var s=[];for(var i=0;i<p.children.length;i++)if(p.children[i].tagName===e.tagName)s.push(p.children[i]);"
            "for(var j=0;j<s.length;j++)if(s[j]===e)return j+1;return 0;", el)
        if idx and idx > 0:
            pid = driver.execute_script("var p=arguments[0].parentElement;return p?(p.id||''):'';", el)
            if pid: return f"#{pid} > {tag}:nth-of-type({idx})"
    except: pass
    return tag

def capture_form_values(driver):
    from selenium.webdriver.common.by import By
    steps, seen = [], set()
    for el in driver.find_elements(By.CSS_SELECTOR, "input[type='text'],input:not([type]),textarea"):
        try:
            if not el.is_displayed(): continue
            if (el.get_attribute("type") or "text") == "hidden": continue
            val = el.get_attribute("value") or ""
            if not val.strip(): continue
            tag = el.tag_name.lower()
            sel = _build_selector(driver, el, tag, el.get_attribute("id") or "", el.get_attribute("name") or "")
            if sel in seen: continue; seen.add(sel)
            steps.append({"type": "入力", "selector": sel, "value": val})
        except: continue
    for el in driver.find_elements(By.CSS_SELECTOR, "select"):
        try:
            if not el.is_displayed(): continue
            sel = _build_selector(driver, el, "select", el.get_attribute("id") or "", el.get_attribute("name") or "")
            if sel in seen: continue; seen.add(sel)
            val = el.get_attribute("value") or ""
            if val: steps.append({"type": "入力", "selector": sel, "value": val})
        except: continue
    for css_q in ["input[type='radio']:checked", "input[type='checkbox']:checked"]:
        for el in driver.find_elements(By.CSS_SELECTOR, css_q):
            try:
                sel = _build_selector(driver, el, "input", el.get_attribute("id") or "", el.get_attribute("name") or "")
                if sel in seen: continue; seen.add(sel)
                steps.append({"type": "クリック", "selector": sel})
            except: continue
    return steps

HIGHLIGHT_JS = ("(function(s){try{var p=document.getElementById('__yshot_hl');if(p)p.remove();"
    "var e=document.querySelector(s);if(!e)return;e.scrollIntoView({block:'center',behavior:'instant'});"
    "var r=e.getBoundingClientRect(),h=document.createElement('div');h.id='__yshot_hl';"
    "h.style.cssText='position:fixed;border:3px solid #FF4444;background:rgba(255,68,68,0.15);"
    "z-index:2147483647;pointer-events:none;border-radius:3px;';"
    "h.style.top=r.top-3+'px';h.style.left=r.left-3+'px';"
    "h.style.width=r.width+6+'px';h.style.height=r.height+6+'px';"
    "document.body.appendChild(h);}catch(x){}})(arguments[0]);")

def build_auth_url(url, user, password):
    if not user: return url
    p = urlparse(url); nl = f"{user}:{password}@{p.hostname}"
    if p.port: nl += f":{p.port}"
    return urlunparse(p._replace(netloc=nl))

def copy_image_to_clipboard(filepath):
    try:
        from PIL import Image; import io, ctypes
        img = Image.open(filepath); out = io.BytesIO()
        img.convert("RGB").save(out, "BMP"); bmp = out.getvalue()[14:]
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        u.OpenClipboard(0); u.EmptyClipboard()
        h = k.GlobalAlloc(0x0042, len(bmp)); p = k.GlobalLock(h)
        ctypes.memmove(p, bmp, len(bmp)); k.GlobalUnlock(h)
        u.SetClipboardData(8, h); u.CloseClipboard(); return True
    except: return False

STEP_TYPES = ["入力", "クリック", "待機", "スクショ", "見出し", "コメント"]
STEP_ICONS = {"入力": ft.Icons.EDIT, "クリック": ft.Icons.MOUSE,
              "待機": ft.Icons.HOURGLASS_BOTTOM, "スクショ": ft.Icons.CAMERA_ALT,
              "見出し": ft.Icons.TITLE, "コメント": ft.Icons.COMMENT}

def step_short(step):
    t = step["type"]
    if t == "見出し": return step.get("text","")
    if t == "コメント": return step.get("text","")
    if t == "入力":
        v = step.get("value","{パターン}")
        if len(v) > 20: v = v[:17]+"..."
        sel = step.get("selector","")
        if len(sel) > 20: sel = sel[:17]+"..."
        return f"{sel} \u2190 {v}"
    if t == "クリック":
        sel = step.get("selector","")
        return sel[:30]+"..." if len(sel) > 30 else sel
    if t == "待機": return f"{step.get('seconds','1.0')}秒"
    if t == "スクショ":
        m = step.get("mode","fullpage")
        if m == "fullpage": return "ページ全体"
        if m == "margin": return f"+{step.get('margin_px','200')}px"
        return "要素"
    return str(step)

step_display = step_short

def run_all_tests(config, test_cases, pattern_sets, log_cb, done_cb):
    """Run all enabled test cases sequentially."""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        log_cb("[ERROR] selenium が見つかりません。"); done_cb(); return
    driver = None
    try:
        driver = webdriver.Chrome(); driver.set_window_size(1280, 900)
        ba = config.get("basic_auth_user","").strip()
        base = build_auth_url(config["url"], ba, config.get("basic_auth_pass",""))
        if ba: log_cb("[INFO] Basic認証を設定")
        outdir = config.get("output_dir","./screenshots"); os.makedirs(outdir, exist_ok=True)
        clip = config.get("clipboard_copy") == "1"
        gss = 0

        for tc_idx, tc in enumerate(test_cases, 1):
            tc_name = tc.get("name", f"テスト{tc_idx}")
            steps = tc.get("steps", [])
            pat_name = tc.get("pattern")
            pats = pattern_sets.get(pat_name, []) if pat_name else []
            if not pats:
                pats = [{"label": "single", "value": ""}]
            log_cb(f"\n{'='*50}")
            log_cb(f"テストケース: {tc_name} ({len(pats)} パターン)")
            log_cb(f"{'='*50}")

            for pi, pat in enumerate(pats, 1):
                label, value = pat.get("label",f"p{pi:03d}"), pat.get("value","")
                log_cb(f"--- [{pi}/{len(pats)}] {label} ({len(value)}文字) ---")
                driver.get(base); time.sleep(0.5); sc = 0
                for si, step in enumerate(steps, 1):
                    st = step["type"]
                    if st in ("見出し","コメント"):
                        if st == "見出し": log_cb(f"  ## {step.get('text','')}")
                        continue
                    if st == "入力":
                        sel = step.get("selector","")
                        iv = step.get("value","{パターン}").replace("{パターン}",value).replace("{pattern}",value)
                        try:
                            e = WebDriverWait(driver,10).until(EC.presence_of_element_located((By.CSS_SELECTOR,sel)))
                            e.clear(); e.send_keys(iv); log_cb(f"  S{si} 入力: {sel}")
                        except Exception as x: log_cb(f"  S{si} [WARN] 入力失敗: {x}")
                    elif st == "クリック":
                        sel = step.get("selector","")
                        try:
                            WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.CSS_SELECTOR,sel))).click()
                            log_cb(f"  S{si} クリック: {sel}")
                        except Exception as x: log_cb(f"  S{si} [WARN] クリック失敗: {x}")
                    elif st == "待機":
                        s = float(step.get("seconds","1.0")); time.sleep(s); log_cb(f"  S{si} 待機: {s}秒")
                    elif st == "スクショ":
                        sc += 1; gss += 1; mode = step.get("mode","fullpage"); sel = step.get("selector","")
                        safe_tc = tc_name.replace(" ","_")[:20]
                        fn = f"{gss:03d}_{safe_tc}_{label}_ss{sc}.png"; fp = os.path.join(outdir, fn)
                        try:
                            if mode == "element" and sel:
                                driver.find_element(By.CSS_SELECTOR, sel).screenshot(fp)
                            elif mode == "margin" and sel:
                                mg = int(step.get("margin_px",200))
                                tgt = driver.find_element(By.CSS_SELECTOR, sel)
                                driver.execute_script("arguments[0].scrollIntoView({block:'center',behavior:'instant'});",tgt)
                                time.sleep(0.3)
                                r = driver.execute_script("var r=arguments[0].getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height};",tgt)
                                driver.save_screenshot(fp)
                                from PIL import Image; img = Image.open(fp)
                                d = driver.execute_script("return window.devicePixelRatio||1;")
                                x1,y1 = max(0,int(r["x"]*d)-mg), max(0,int(r["y"]*d)-mg)
                                x2,y2 = min(img.width,int((r["x"]+r["w"])*d)+mg), min(img.height,int((r["y"]+r["h"])*d)+mg)
                                if x2>x1 and y2>y1: img.crop((x1,y1,x2,y2)).save(fp)
                            else: driver.save_screenshot(fp)
                            log_cb(f"  S{si} スクショ: {fn}")
                            if clip: copy_image_to_clipboard(fp)
                        except Exception as x: log_cb(f"  S{si} [WARN] スクショ失敗: {x}")
        log_cb(f"\n[全完了] {len(test_cases)} テスト -> {outdir}")
    except Exception as x: log_cb(f"[ERROR] {x}")
    finally:
        if driver: driver.quit()
        done_cb()

# ===================================================================
# Persistence
# ===================================================================
CSV_HEADER = ["label", "value"]
CONFIG_FILE = "y_shot_config.ini"
TESTS_FILE = "y_shot_tests.json"
PATTERNS_FILE = "y_shot_patterns.json"
SELECTOR_BANK_FILE = "y_shot_selectors.json"

def load_csv(path):
    if not os.path.isfile(path): return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if "label" in r]
def save_csv(path, patterns):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER); w.writeheader(); w.writerows(patterns)
def load_config():
    import configparser; c = configparser.ConfigParser(); c.read(CONFIG_FILE, encoding="utf-8")
    return dict(c["settings"]) if "settings" in c else {}
def save_config(data):
    import configparser; c = configparser.ConfigParser()
    c["settings"] = {k: str(v) for k,v in data.items()}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f: c.write(f)
def load_tests():
    if not os.path.isfile(TESTS_FILE): return []
    with open(TESTS_FILE, "r", encoding="utf-8") as f: return json.load(f)
def save_tests(tests):
    with open(TESTS_FILE, "w", encoding="utf-8") as f: json.dump(tests, f, ensure_ascii=False, indent=2)
def load_pattern_sets():
    if not os.path.isfile(PATTERNS_FILE): return {}
    with open(PATTERNS_FILE, "r", encoding="utf-8") as f: return json.load(f)
def save_pattern_sets(ps):
    with open(PATTERNS_FILE, "w", encoding="utf-8") as f: json.dump(ps, f, ensure_ascii=False, indent=2)
def load_selector_bank():
    if not os.path.isfile(SELECTOR_BANK_FILE): return {}
    with open(SELECTOR_BANK_FILE, "r", encoding="utf-8") as f: return json.load(f)
def save_selector_bank(bank):
    with open(SELECTOR_BANK_FILE, "w", encoding="utf-8") as f: json.dump(bank, f, ensure_ascii=False, indent=2)
def get_templates_dir():
    for d in [os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"),
              os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "templates")]:
        if os.path.isdir(d): return d
    return None

# ===================================================================
# Flet UI
# ===================================================================

def main(page: ft.Page):
    page.title = f"{APP_NAME} - Web Screenshot Tool"
    page.window.width = 1300; page.window.height = 900
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)

    state = {
        "tests": load_tests(),            # [{name, pattern, steps}, ...]
        "pattern_sets": load_pattern_sets(),  # {name: [{label, value}, ...]}
        "config": load_config(),
        "selector_bank": load_selector_bank(),
        "browser_driver": None, "browser_elements": [],
        "selected_test": 0, "selected_pat_set": None, "selected_el": -1,
        "collapsed": set(),
    }
    cfg = state["config"]

    # ── Helpers ──
    def log(msg):
        log_list.controls.append(ft.Text(msg, size=11, selectable=True, font_family="Consolas"))
        if len(log_list.controls) > 400: log_list.controls.pop(0)
        page.update()
    def snack(msg, color=ft.Colors.GREEN_700):
        page.overlay.append(ft.SnackBar(ft.Text(msg, color=ft.Colors.WHITE), bgcolor=color, open=True))
        page.update()
    def open_dlg(d):
        page.overlay.append(d); d.open = True; page.update()
    def close_dlg(d):
        d.open = False; page.update()
    def save_all():
        c = dict(state["config"])
        c["browser_url"] = browser_url.value or ""
        c["browser_wait"] = browser_wait.value or "3.0"
        save_config(c); save_tests(state["tests"])
        save_pattern_sets(state["pattern_sets"]); save_selector_bank(state["selector_bank"])
    def close_browser():
        if state["browser_driver"]:
            try: state["browser_driver"].quit()
            except: pass
            state["browser_driver"] = None
    def get_all_selectors():
        sels = set()
        for elems in state["selector_bank"].values():
            for el in elems: sels.add(el["selector"])
        for el in state["browser_elements"]: sels.add(el["selector"])
        return sorted(sels)
    def cur_test():
        idx = state["selected_test"]
        if 0 <= idx < len(state["tests"]): return state["tests"][idx]
        return None
    def pat_set_names():
        return sorted(state["pattern_sets"].keys())

    # ================================================================
    # Tab 1: Test Cases
    # ================================================================

    def refresh_test_list():
        test_list.controls.clear()
        for i, tc in enumerate(state["tests"]):
            selected = (i == state["selected_test"])
            pat = tc.get("pattern","")
            n_steps = len([s for s in tc.get("steps",[]) if s["type"] not in ("見出し","コメント")])
            n_pats = len(state["pattern_sets"].get(pat,[])) if pat else 0
            subtitle = f"{n_steps}ステップ"
            if pat: subtitle += f" × {pat}({n_pats}件)"
            test_list.controls.append(ft.Container(
                ft.Row([
                    ft.Column([
                        ft.Text(tc.get("name",""), weight=ft.FontWeight.BOLD, size=13,
                                color=ft.Colors.BLUE_800 if selected else ft.Colors.BLACK),
                        ft.Text(subtitle, size=10, color=ft.Colors.GREY_500),
                    ], spacing=2, expand=True),
                    ft.IconButton(ft.Icons.DELETE, icon_size=16, icon_color=ft.Colors.RED_400,
                                  on_click=lambda e, idx=i: del_test(idx)),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.BLUE_50 if selected else None,
                padding=ft.Padding(12, 8, 8, 8), border_radius=6,
                border=ft.Border.all(2, ft.Colors.BLUE_300) if selected else ft.Border.all(1, ft.Colors.GREY_200),
                on_click=lambda e, idx=i: select_test(idx),
            ))
        page.update()

    def select_test(idx):
        state["selected_test"] = idx
        state["collapsed"] = set()
        refresh_test_list(); refresh_steps()

    def add_test(e):
        state["tests"].append({"name": f"テスト{len(state['tests'])+1}", "pattern": None, "steps": []})
        state["selected_test"] = len(state["tests"]) - 1
        refresh_test_list(); refresh_steps()

    def del_test(idx):
        if 0 <= idx < len(state["tests"]):
            state["tests"].pop(idx)
            if state["selected_test"] >= len(state["tests"]):
                state["selected_test"] = max(0, len(state["tests"])-1)
            refresh_test_list(); refresh_steps()

    def edit_test_name(e):
        tc = cur_test()
        if not tc: return
        nf = ft.TextField(label="テスト名", value=tc["name"], width=350)
        pat_opts = [ft.dropdown.Option("なし")] + [ft.dropdown.Option(n) for n in pat_set_names()]
        pf = ft.Dropdown(label="パターンセット", width=350, value=tc.get("pattern") or "なし", options=pat_opts)
        def on_ok(e):
            tc["name"] = nf.value
            tc["pattern"] = None if pf.value == "なし" else pf.value
            refresh_test_list(); refresh_steps(); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("テストケース設定"),
            content=ft.Column([nf, pf], tight=True, spacing=10, width=400),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    # ── Steps ──

    def refresh_steps():
        step_reorder.controls.clear()
        tc = cur_test()
        if not tc:
            tc_header.value = "テストケースを選択してください"
            tc_pattern_label.value = ""
            page.update(); return
        tc_header.value = tc.get("name","")
        pat = tc.get("pattern")
        tc_pattern_label.value = f"パターン: {pat} ({len(state['pattern_sets'].get(pat,[]))}件)" if pat else "パターン: なし (1回実行)"

        collapsed = state["collapsed"]
        hidden = False
        for i, s in enumerate(tc.get("steps",[])):
            t = s["type"]; key = str(i)
            if t == "見出し":
                sid = i; is_c = sid in collapsed; hidden = is_c
                ic = ft.Icons.EXPAND_LESS if not is_c else ft.Icons.EXPAND_MORE
                step_reorder.controls.append(ft.Container(ft.Row([
                    ft.Icon(ft.Icons.DRAG_HANDLE, size=14, color=ft.Colors.GREY_400),
                    ft.Icon(ft.Icons.TITLE, color=ft.Colors.BLUE_800, size=16),
                    ft.Text(s.get("text",""), weight=ft.FontWeight.BOLD, size=13, color=ft.Colors.BLUE_800, expand=True),
                    ft.IconButton(ic, icon_size=16, on_click=lambda e, sid=sid: toggle_sec(sid)),
                    ft.IconButton(ft.Icons.EDIT, icon_size=14, on_click=lambda e, idx=i: show_step_dlg(idx)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=14, on_click=lambda e, idx=i: del_step(idx)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=ft.Colors.BLUE_50, padding=ft.Padding(8,4,8,4), border_radius=4, key=key, height=36))
            elif t == "コメント":
                if hidden: continue
                step_reorder.controls.append(ft.Container(ft.Row([
                    ft.Icon(ft.Icons.DRAG_HANDLE, size=14, color=ft.Colors.GREY_400),
                    ft.Icon(ft.Icons.COMMENT, color=ft.Colors.GREY_400, size=14),
                    ft.Text(s.get("text",""), size=11, italic=True, color=ft.Colors.GREY_500, expand=True),
                    ft.IconButton(ft.Icons.EDIT, icon_size=14, on_click=lambda e, idx=i: show_step_dlg(idx)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=14, on_click=lambda e, idx=i: del_step(idx)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(8,2,8,2), key=key, height=28))
            else:
                if hidden: continue
                step_reorder.controls.append(ft.Container(ft.Row([
                    ft.Icon(ft.Icons.DRAG_HANDLE, size=14, color=ft.Colors.GREY_400),
                    ft.Icon(STEP_ICONS.get(t, ft.Icons.HELP), color=ft.Colors.BLUE_600, size=16),
                    ft.Text(t, size=11, color=ft.Colors.GREY_500, width=40),
                    ft.Text(step_short(s), size=12, expand=True),
                    ft.IconButton(ft.Icons.EDIT, icon_size=14, on_click=lambda e, idx=i: show_step_dlg(idx)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=14, on_click=lambda e, idx=i: del_step(idx)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(8,2,8,2), key=key, height=30))
        page.update()

    def on_reorder(e):
        tc = cur_test()
        if not tc: return
        steps = tc["steps"]; vis = _get_vis(steps)
        old, new = e.old_index, e.new_index
        if old < len(vis) and new <= len(vis):
            ao = vis[old]; an = vis[new] if new < len(vis) else len(steps)
            item = steps.pop(ao)
            if an > ao: an -= 1
            steps.insert(an, item); refresh_steps()

    def _get_vis(steps):
        vis, hidden = [], False
        for i, s in enumerate(steps):
            if s["type"] == "見出し": hidden = i in state["collapsed"]; vis.append(i)
            elif not hidden: vis.append(i)
        return vis

    def toggle_sec(sid):
        state["collapsed"].symmetric_difference_update({sid}); refresh_steps()

    def del_step(idx):
        tc = cur_test()
        if tc and 0 <= idx < len(tc["steps"]):
            tc["steps"].pop(idx)
            state["collapsed"] = {c if c < idx else c-1 for c in state["collapsed"] if c != idx}
            refresh_steps()

    def show_step_dlg(idx):
        tc = cur_test()
        if not tc: return
        init = tc["steps"][idx] if idx is not None else {}
        t0 = init.get("type","入力")
        type_dd = ft.Dropdown(label="種類", width=160, value=t0, options=[ft.dropdown.Option(t) for t in STEP_TYPES])
        all_sels = get_all_selectors()
        sel_field = ft.Dropdown(label="セレクタ", width=450, value=init.get("selector",""),
            options=[ft.dropdown.Option(s) for s in all_sels], editable=True) if all_sels else \
            ft.TextField(label="セレクタ", width=450, value=init.get("selector",""))
        val_field = ft.TextField(label="値 ({パターン} で代入)", width=450, value=init.get("value","{パターン}"),
            multiline=True, min_lines=2, max_lines=4)
        sec_field = ft.TextField(label="秒数", width=120, value=init.get("seconds","1.0"))
        mode_dd = ft.Dropdown(label="スクショ範囲", width=180, value=init.get("mode","fullpage"),
            options=[ft.dropdown.Option(m) for m in ["fullpage","element","margin"]])
        margin_f = ft.TextField(label="マージン(px)", width=120, value=init.get("margin_px","200"))
        text_f = ft.TextField(label="テキスト", width=450, value=init.get("text",""), multiline=True, min_lines=1, max_lines=3)
        def upd(e=None):
            t = type_dd.value
            sel_field.visible = t in ("入力","クリック") or (t=="スクショ" and mode_dd.value in ("element","margin"))
            val_field.visible = (t=="入力"); sec_field.visible = (t=="待機"); mode_dd.visible = (t=="スクショ")
            margin_f.visible = (t=="スクショ" and mode_dd.value=="margin"); text_f.visible = t in ("見出し","コメント")
            page.update()
        type_dd.on_select = upd; mode_dd.on_select = upd
        def on_ok(e):
            t = type_dd.value; step = {"type": t}
            if t in ("見出し","コメント"): step["text"] = text_f.value
            elif t in ("入力","クリック"):
                s = sel_field.value if hasattr(sel_field,'value') else ""
                if not s: snack("セレクタを入力", ft.Colors.RED_600); return
                step["selector"] = s
                if t == "入力": step["value"] = val_field.value
            elif t == "待機":
                try: step["seconds"] = str(float(sec_field.value))
                except: snack("秒数を正しく", ft.Colors.RED_600); return
            elif t == "スクショ":
                step["mode"] = mode_dd.value
                s = sel_field.value if hasattr(sel_field,'value') else ""
                if mode_dd.value in ("element","margin") and not s: snack("セレクタ必要", ft.Colors.RED_600); return
                if s: step["selector"] = s
                if mode_dd.value == "margin":
                    try: step["margin_px"] = str(int(margin_f.value))
                    except: snack("整数で", ft.Colors.RED_600); return
            if idx is not None: tc["steps"][idx] = step
            else: tc["steps"].append(step)
            refresh_steps(); refresh_test_list(); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("ステップ編集" if idx is not None else "ステップ追加"),
            content=ft.Column([type_dd, text_f, sel_field, val_field, sec_field, mode_dd, margin_f],
                tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, width=500, height=400),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg); upd()

    # ── Element browser ──
    def load_page_click(e):
        url = browser_url.value
        if not url: snack("URL入力", ft.Colors.RED_600); return
        load_btn.disabled = True; el_status.value = "読込中..."; page.update()
        page.run_thread(do_load_page, url)
    def do_load_page(url):
        try:
            from selenium import webdriver
            if state["browser_driver"] is None:
                state["browser_driver"] = webdriver.Chrome(); state["browser_driver"].set_window_size(1280,900)
            ba = state["config"].get("basic_auth_user","").strip()
            lu = build_auth_url(url, ba, state["config"].get("basic_auth_pass","")) if ba else url
            state["browser_driver"].get(lu)
            try: w = float(browser_wait.value)
            except: w = 3.0
            time.sleep(w); log(f"[DEBUG] {state['browser_driver'].title}")
            elems = collect_elements_python(state["browser_driver"])
            state["browser_elements"] = list(elems)
            state["selector_bank"][url.split("?")[0]] = elems
            update_el_table(elems, url); update_url_dd()
        except Exception as x: state["browser_driver"] = None; log(f"[ERROR] {x}")
        finally: load_btn.disabled = False; page.update()
    def update_el_table(elems, url):
        el_table.rows.clear()
        for i, el in enumerate(elems):
            el_table.rows.append(ft.DataRow(
                cells=[ft.DataCell(ft.Text(el["tag"],size=11)), ft.DataCell(ft.Text(el.get("type",""),size=11)),
                       ft.DataCell(ft.Text(el.get("id") or el.get("name",""),size=11)),
                       ft.DataCell(ft.Text(el.get("hint","")[:20],size=11)),
                       ft.DataCell(ft.Text(el["selector"],size=10,color=ft.Colors.GREY_600))],
                on_select_change=lambda e, idx=i: on_el_click(idx)))
        el_status.value = f"{len(elems)} 要素"; log(f"[要素] {url} -> {len(elems)}"); page.update()
    def update_url_dd():
        ex = {o.key for o in browser_url_dd.options}
        for u in state["selector_bank"]:
            if u not in ex: browser_url_dd.options.append(ft.dropdown.Option(u))
        page.update()
    def on_url_dd_sel(e): browser_url.value = browser_url_dd.value; page.update()
    def load_bank(e):
        url = browser_url_dd.value or browser_url.value
        if not url: return
        clean = url.split("?")[0]
        if clean in state["selector_bank"]:
            elems = state["selector_bank"][clean]; state["browser_elements"] = list(elems)
            update_el_table(elems, url); snack(f"バンク {len(elems)} 要素")
        else: snack("未保存URL", ft.Colors.ORANGE_600)
    def on_el_click(idx):
        state["selected_el"] = idx
        if idx < len(state["browser_elements"]) and state["browser_driver"]:
            try: state["browser_driver"].execute_script(HIGHLIGHT_JS, state["browser_elements"][idx]["selector"])
            except: pass
    def quick_add(stype):
        tc = cur_test()
        if not tc: snack("テストケースを選択", ft.Colors.ORANGE_600); return
        idx = state["selected_el"]
        if idx < 0 or idx >= len(state["browser_elements"]): snack("要素をクリック", ft.Colors.ORANGE_600); return
        sel = state["browser_elements"][idx]["selector"]
        step = {"type": stype, "selector": sel}
        if stype == "入力": step["value"] = "{パターン}"
        tc["steps"].append(step); refresh_steps(); refresh_test_list(); snack(f"{stype}: {sel}")
    def capture_form(e):
        tc = cur_test()
        if not tc: return
        if not state["browser_driver"]: snack("ページ読込必要", ft.Colors.ORANGE_600); return
        try:
            fs = capture_form_values(state["browser_driver"])
            if not fs: snack("フォーム値なし", ft.Colors.ORANGE_600); return
            tc["steps"].extend(fs); refresh_steps(); refresh_test_list(); snack(f"フォーム値 {len(fs)} 件")
        except Exception as x: log(f"[ERROR] {x}")
    def close_br(e):
        close_browser(); el_table.rows.clear(); state["browser_elements"].clear()
        el_status.value = "閉じた"; page.update()
    def sync_url(e): browser_url.value = state["config"].get("url",""); page.update()

    # ================================================================
    # Tab 2: Pattern Sets
    # ================================================================

    def refresh_pat_set_list():
        pat_set_list.controls.clear()
        for name in sorted(state["pattern_sets"].keys()):
            pats = state["pattern_sets"][name]
            selected = (state["selected_pat_set"] == name)
            pat_set_list.controls.append(ft.Container(
                ft.Row([
                    ft.Column([
                        ft.Text(name, weight=ft.FontWeight.BOLD, size=13,
                                color=ft.Colors.BLUE_800 if selected else ft.Colors.BLACK),
                        ft.Text(f"{len(pats)} パターン", size=10, color=ft.Colors.GREY_500),
                    ], spacing=2, expand=True),
                    ft.IconButton(ft.Icons.DELETE, icon_size=16, icon_color=ft.Colors.RED_400,
                                  on_click=lambda e, n=name: del_pat_set(n)),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.BLUE_50 if selected else None,
                padding=ft.Padding(12, 8, 8, 8), border_radius=6,
                border=ft.Border.all(2, ft.Colors.BLUE_300) if selected else ft.Border.all(1, ft.Colors.GREY_200),
                on_click=lambda e, n=name: select_pat_set(n),
            ))
        page.update()

    def select_pat_set(name):
        state["selected_pat_set"] = name; refresh_pat_set_list(); refresh_pats()

    def add_pat_set(e):
        nf = ft.TextField(label="パターンセット名", width=300)
        def on_ok(e):
            n = nf.value.strip()
            if not n: snack("名前入力", ft.Colors.RED_600); return
            if n in state["pattern_sets"]: snack("既に存在", ft.Colors.RED_600); return
            state["pattern_sets"][n] = []; state["selected_pat_set"] = n
            refresh_pat_set_list(); refresh_pats(); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("パターンセット追加"),
            content=nf, actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def del_pat_set(name):
        if name in state["pattern_sets"]:
            del state["pattern_sets"][name]
            if state["selected_pat_set"] == name: state["selected_pat_set"] = None
            refresh_pat_set_list(); refresh_pats()

    def refresh_pats():
        pat_items.controls.clear()
        name = state["selected_pat_set"]
        if not name or name not in state["pattern_sets"]:
            pat_header.value = "パターンセットを選択"; page.update(); return
        pats = state["pattern_sets"][name]
        pat_header.value = f"{name} ({len(pats)} 件)"
        for i, p in enumerate(pats):
            v = p["value"]; d = v if len(v) <= 55 else v[:52]+"..."
            pat_items.controls.append(ft.Container(ft.Row([
                ft.Column([
                    ft.Text(p["label"], weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.BLUE_800),
                    ft.Text(d, size=11, color=ft.Colors.GREY_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=1, expand=True),
                ft.Text(f"{len(v)}", size=10, color=ft.Colors.GREY_400, width=40),
                ft.IconButton(ft.Icons.EDIT, icon_size=14, on_click=lambda e, idx=i: edit_pat(idx)),
                ft.IconButton(ft.Icons.DELETE, icon_size=14, icon_color=ft.Colors.RED_400,
                              on_click=lambda e, idx=i: del_pat(idx)),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                padding=ft.Padding(10, 6, 6, 6), border=ft.Border.all(1, ft.Colors.GREY_200), border_radius=4))
        page.update()

    def add_pat(e):
        name = state["selected_pat_set"]
        if not name: return
        edit_pat(None)

    def edit_pat(idx):
        name = state["selected_pat_set"]
        if not name: return
        pats = state["pattern_sets"][name]
        init = pats[idx] if idx is not None else {}
        lf = ft.TextField(label="ラベル", width=400, value=init.get("label",""))
        vf = ft.TextField(label="入力値", width=400, value=init.get("value",""), multiline=True, min_lines=3, max_lines=6)
        def on_ok(e):
            if not lf.value: snack("ラベル入力", ft.Colors.RED_600); return
            p = {"label": lf.value, "value": vf.value}
            if idx is not None: pats[idx] = p
            else: pats.append(p)
            refresh_pats(); refresh_pat_set_list(); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("パターン"),
            content=ft.Column([lf, vf], tight=True, spacing=10, width=450),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def del_pat(idx):
        name = state["selected_pat_set"]
        if name and name in state["pattern_sets"]:
            state["pattern_sets"][name].pop(idx); refresh_pats(); refresh_pat_set_list()

    def load_template(e):
        td = get_templates_dir()
        if not td: snack("templatesなし", ft.Colors.RED_600); return
        name = state["selected_pat_set"]
        if not name: snack("パターンセットを選択", ft.Colors.ORANGE_600); return
        csvs = sorted([f for f in os.listdir(td) if f.lower().endswith(".csv")])
        if not csvs: snack("CSVなし", ft.Colors.RED_600); return
        def on_sel(fn):
            loaded = load_csv(os.path.join(td, fn))
            state["pattern_sets"][name].extend(loaded)
            refresh_pats(); refresh_pat_set_list(); snack(f"{len(loaded)} 件追加"); close_dlg(dlg)
        cards = [ft.Card(ft.Container(ft.Column([
            ft.Text(os.path.splitext(f)[0], weight=ft.FontWeight.BOLD, size=13),
            ft.Text(f"{len(load_csv(os.path.join(td,f)))} 件", size=11, color=ft.Colors.GREY_600)],
            spacing=2), padding=12, on_click=lambda e, fn=f: on_sel(fn)), elevation=2) for f in csvs]
        dlg = ft.AlertDialog(title=ft.Text("テンプレート"),
            content=ft.Column(cards, spacing=6, scroll=ft.ScrollMode.AUTO, width=380, height=300),
            actions=[ft.TextButton("閉じる", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def gen_input_check(e):
        name = state["selected_pat_set"]
        if not name: snack("パターンセットを選択", ft.Colors.ORANGE_600); return
        mf = ft.TextField(label="最大文字数 (空欄可)", width=140)
        def on_ok(e):
            ps = [{"label":"未入力","value":""},{"label":"全角スペースのみ","value":"\u3000"},
                  {"label":"半角スペースのみ","value":" "},{"label":"全角スペース含む","value":"テスト\u3000入力"},
                  {"label":"半角スペース含む","value":"テスト 入力"},{"label":"全角英字","value":"ＡＢＣＤＥ"},
                  {"label":"半角英字","value":"ABCDE"},{"label":"全角記号","value":"\u00A9"},
                  {"label":"半角記号","value":"!@#$%"},{"label":"絵文字含む","value":"テスト\U0001f990入力"},
                  {"label":"4バイト文字","value":"\U00020BB7野屋"},{"label":"全角数値","value":"１２３４５"},
                  {"label":"半角数値","value":"12345"}]
            ml = mf.value.strip()
            if ml and ml.isdigit():
                n = int(ml)
                if n > 1: ps.append({"label":f"最大-1({n-1}文字)","value":"あ"*(n-1)})
                ps.append({"label":f"最大({n}文字)","value":"あ"*n})
                ps.append({"label":f"最大+1({n+1}文字)","value":"あ"*(n+1)})
            state["pattern_sets"][name].extend(ps); refresh_pats(); refresh_pat_set_list()
            snack(f"{len(ps)} 件追加"); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("入力チェック用"),
            content=ft.Column([mf, ft.Text("未入力/スペース/全角半角/記号/絵文字/4バイト + 境界値",
                size=11, color=ft.Colors.GREY_600)], tight=True, spacing=10, width=350),
            actions=[ft.TextButton("追加", on_click=on_ok), ft.TextButton("閉じる", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    # ── Settings / Info / Run ──
    def show_settings(e):
        c = state["config"]
        uf = ft.TextField(label="対象URL", value=c.get("url",""), width=450)
        auf = ft.TextField(label="Basic認証ID", value=c.get("basic_auth_user",""), width=210)
        apf = ft.TextField(label="パスワード", value=c.get("basic_auth_pass",""), password=True, width=210)
        of = ft.TextField(label="出力フォルダ", value=c.get("output_dir","./screenshots"), width=450)
        cc = ft.Checkbox(label="クリップボードコピー", value=c.get("clipboard_copy")=="1")
        def on_ok(e):
            state["config"].update({"url":uf.value,"basic_auth_user":auf.value,
                "basic_auth_pass":apf.value,"output_dir":of.value,
                "clipboard_copy":"1" if cc.value else "0"})
            save_config(state["config"]); snack("設定保存"); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("設定"),
            content=ft.Column([uf, ft.Row([auf, apf], spacing=10), of, cc], tight=True, spacing=12, width=500),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def show_info(e):
        dlg = ft.AlertDialog(title=ft.Text("情報"),
            content=ft.Column([ft.Text(f"{APP_NAME}  v{APP_VERSION}", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Web Screenshot Automation Tool"), ft.Divider(),
                ft.Text(f"Developed by {APP_AUTHOR}")], tight=True, spacing=8, width=300),
            actions=[ft.TextButton("閉じる", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def run_click(e):
        c = state["config"]
        if not c.get("url"): snack("URL未設定", ft.Colors.RED_600); return
        if not state["tests"]: snack("テストケース0件", ft.Colors.RED_600); return
        close_browser(); run_btn.disabled = True; progress.visible = True
        nav_bar.selected_index = 0; switch_tab(0); page.update(); save_all()
        def on_done():
            run_btn.disabled = False; progress.visible = False; page.update()
        page.run_thread(run_all_tests, dict(c), list(state["tests"]),
                        dict(state["pattern_sets"]), lambda m: log(m), on_done)

    def switch_tab(idx):
        tc_content.visible = (idx == 0); ps_content.visible = (idx == 1); page.update()
    def on_nav(e): switch_tab(e.control.selected_index)

    # ── Build controls ──
    browser_url = ft.TextField(label="URL", expand=True, dense=True, value=cfg.get("browser_url",""))
    browser_url_dd = ft.Dropdown(label="履歴", width=200, dense=True,
        options=[ft.dropdown.Option(u) for u in state["selector_bank"].keys()], on_select=on_url_dd_sel)
    browser_wait = ft.TextField(label="秒", width=55, dense=True, value=cfg.get("browser_wait","3.0"))
    load_btn = ft.Button("読込", icon=ft.Icons.REFRESH, on_click=load_page_click)
    el_status = ft.Text("未読込", size=11, color=ft.Colors.GREY_500)
    el_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("タグ",size=11)), ft.DataColumn(ft.Text("type",size=11)),
                 ft.DataColumn(ft.Text("id/name",size=11)), ft.DataColumn(ft.Text("ヒント",size=11)),
                 ft.DataColumn(ft.Text("セレクタ",size=11))],
        rows=[], column_spacing=8, data_row_min_height=28, heading_row_height=30)

    test_list = ft.ListView(spacing=4, expand=True)
    step_reorder = ft.ReorderableListView(controls=[], on_reorder=on_reorder, spacing=1, expand=True)
    log_list = ft.ListView(spacing=1, auto_scroll=True, height=130)
    tc_header = ft.Text("", weight=ft.FontWeight.BOLD, size=15)
    tc_pattern_label = ft.Text("", size=11, color=ft.Colors.GREY_600)

    pat_set_list = ft.ListView(spacing=4, expand=True)
    pat_items = ft.ListView(spacing=3, expand=True)
    pat_header = ft.Text("", weight=ft.FontWeight.BOLD, size=15)

    progress = ft.ProgressBar(visible=False)
    run_btn = ft.Button("全テスト実行", icon=ft.Icons.PLAY_ARROW, bgcolor=ft.Colors.BLUE_600,
                        color=ft.Colors.WHITE, on_click=run_click, height=42)

    # ── Layout: Tab 1 (Tests) ──
    tc_content = ft.Row([
        # Left: test case list
        ft.Container(ft.Column([
            ft.Row([ft.Text("テストケース", weight=ft.FontWeight.BOLD, size=14),
                    ft.IconButton(ft.Icons.ADD, tooltip="追加", icon_size=18, on_click=add_test)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            test_list,
        ], spacing=4), width=220, padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),

        # Center: selected test steps
        ft.Column([
            ft.Container(ft.Column([
                ft.Row([tc_header, ft.IconButton(ft.Icons.EDIT, icon_size=16, tooltip="テスト設定", on_click=edit_test_name)],
                       alignment=ft.MainAxisAlignment.START),
                tc_pattern_label,
                ft.Row([ft.IconButton(ft.Icons.ADD, tooltip="ステップ追加", icon_size=18,
                            on_click=lambda e: show_step_dlg(None)),
                        ft.IconButton(ft.Icons.TITLE, tooltip="見出し", icon_size=18,
                            on_click=lambda e: (cur_test() and cur_test()["steps"].append({"type":"見出し","text":"セクション"}), refresh_steps())),
                        ft.IconButton(ft.Icons.COMMENT, tooltip="コメント", icon_size=18,
                            on_click=lambda e: (cur_test() and cur_test()["steps"].append({"type":"コメント","text":""}), refresh_steps())),
                ], spacing=0),
                step_reorder,
            ], spacing=4), padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8, expand=True),
            ft.Container(ft.Column([ft.Text("ログ", size=12, weight=ft.FontWeight.BOLD), log_list]),
                padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),
        ], expand=3, spacing=6),

        # Right: element browser
        ft.Container(ft.Column([
            ft.Text("要素ブラウザ", weight=ft.FontWeight.BOLD, size=13),
            ft.Row([browser_url, browser_wait], spacing=4),
            ft.Row([browser_url_dd, ft.OutlinedButton("バンク", on_click=load_bank)], spacing=4),
            ft.Row([load_btn, ft.OutlinedButton("閉じる", on_click=close_br), ft.TextButton("設定URL", on_click=sync_url)],
                   spacing=4, wrap=True),
            el_status,
            ft.Container(ft.Column([el_table], scroll=ft.ScrollMode.AUTO),
                height=240, border=ft.Border.all(1, ft.Colors.GREY_200), border_radius=4),
            ft.Row([ft.Button("入力", icon=ft.Icons.EDIT, on_click=lambda e: quick_add("入力")),
                    ft.Button("クリック", icon=ft.Icons.MOUSE, on_click=lambda e: quick_add("クリック")),
                    ft.Button("フォーム値", icon=ft.Icons.SAVE, on_click=capture_form)], spacing=4),
        ], spacing=4), width=340, padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),
    ], spacing=8, expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

    # ── Layout: Tab 2 (Pattern Sets) ──
    ps_content = ft.Row([
        # Left: pattern set list
        ft.Container(ft.Column([
            ft.Row([ft.Text("パターンセット", weight=ft.FontWeight.BOLD, size=14),
                    ft.IconButton(ft.Icons.ADD, tooltip="追加", icon_size=18, on_click=add_pat_set)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            pat_set_list,
        ], spacing=4), width=220, padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),

        # Right: selected set patterns
        ft.Column([
            ft.Row([pat_header,
                    ft.Row([ft.Button("追加", icon=ft.Icons.ADD, on_click=add_pat),
                            ft.Button("テンプレート", icon=ft.Icons.FOLDER_OPEN, on_click=load_template),
                            ft.Button("入力チェック", icon=ft.Icons.CHECKLIST, on_click=gen_input_check)],
                           spacing=4)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Container(pat_items, expand=True, padding=ft.Padding(4,4,4,4),
                border=ft.Border.all(1, ft.Colors.GREY_200), border_radius=6),
        ], expand=True, spacing=6),
    ], spacing=8, expand=True, visible=False, vertical_alignment=ft.CrossAxisAlignment.START)

    nav_bar = ft.NavigationBar(
        destinations=[ft.NavigationBarDestination(icon=ft.Icons.LIST_ALT, label="テストケース"),
                      ft.NavigationBarDestination(icon=ft.Icons.DATASET, label="パターンセット")],
        selected_index=0, on_change=on_nav)

    page.appbar = ft.AppBar(title=ft.Text(APP_NAME, weight=ft.FontWeight.BOLD), center_title=False,
        bgcolor=ft.Colors.BLUE_50,
        actions=[ft.IconButton(ft.Icons.SETTINGS, tooltip="設定", on_click=show_settings),
                 ft.IconButton(ft.Icons.INFO_OUTLINE, tooltip="情報", on_click=show_info)])

    page.add(ft.Column([ft.Stack([tc_content, ps_content], expand=True),
        progress, ft.Row([run_btn], alignment=ft.MainAxisAlignment.END)], expand=True, spacing=4))
    page.navigation_bar = nav_bar

    refresh_test_list(); refresh_steps(); refresh_pat_set_list(); refresh_pats()
    page.on_close = lambda e: (save_all(), close_browser())

if __name__ == "__main__":
    ft.run(main)
