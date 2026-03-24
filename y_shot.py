"""
y-shot: Web Screenshot Automation Tool  v1.1 (Flet)
"""

import csv, os, sys, json, threading, time
from datetime import datetime
from urllib.parse import urlparse, urlunparse
import flet as ft

APP_NAME = "y-shot"
APP_VERSION = "1.1"
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
            tag = el.tag_name.lower()
            etype = el.get_attribute("type") or ""
            if etype == "hidden": continue
            eid = el.get_attribute("id") or ""
            ename = el.get_attribute("name") or ""
            sel = _build_selector(driver, el, tag, eid, ename)
            if sel in seen: continue
            seen.add(sel)
            hint = (el.get_attribute("placeholder") or el.get_attribute("alt") or
                    (el.text or "").strip()[:50] or (el.get_attribute("value") or "")[:30])
            results.append({"selector": sel, "tag": tag, "type": etype,
                            "name": ename, "id": eid, "hint": hint})
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
            if sel in seen: continue
            seen.add(sel)
            steps.append({"type": "入力", "selector": sel, "value": val})
        except: continue
    for el in driver.find_elements(By.CSS_SELECTOR, "select"):
        try:
            if not el.is_displayed(): continue
            sel = _build_selector(driver, el, "select", el.get_attribute("id") or "", el.get_attribute("name") or "")
            if sel in seen: continue
            seen.add(sel)
            val = el.get_attribute("value") or ""
            if val: steps.append({"type": "入力", "selector": sel, "value": val})
        except: continue
    for css_q in ["input[type='radio']:checked", "input[type='checkbox']:checked"]:
        for el in driver.find_elements(By.CSS_SELECTOR, css_q):
            try:
                sel = _build_selector(driver, el, "input", el.get_attribute("id") or "", el.get_attribute("name") or "")
                if sel in seen: continue
                seen.add(sel)
                steps.append({"type": "クリック", "selector": sel})
            except: continue
    return steps

HIGHLIGHT_JS = "(function(s){try{var p=document.getElementById('__yshot_hl');if(p)p.remove();" \
    "var e=document.querySelector(s);if(!e)return;e.scrollIntoView({block:'center',behavior:'instant'});" \
    "var r=e.getBoundingClientRect(),h=document.createElement('div');h.id='__yshot_hl';" \
    "h.style.cssText='position:fixed;border:3px solid #FF4444;background:rgba(255,68,68,0.15);" \
    "z-index:2147483647;pointer-events:none;border-radius:3px;';" \
    "h.style.top=r.top-3+'px';h.style.left=r.left-3+'px';" \
    "h.style.width=r.width+6+'px';h.style.height=r.height+6+'px';" \
    "document.body.appendChild(h);}catch(x){}})(arguments[0]);"

def build_auth_url(url, user, password):
    if not user: return url
    p = urlparse(url)
    nl = f"{user}:{password}@{p.hostname}"
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

# Step types: 見出し and コメント are display-only (skipped at execution)
STEP_TYPES = ["入力", "クリック", "待機", "スクショ", "見出し", "コメント"]
STEP_ICONS = {"入力": ft.Icons.EDIT, "クリック": ft.Icons.MOUSE,
              "待機": ft.Icons.HOURGLASS_BOTTOM, "スクショ": ft.Icons.CAMERA_ALT,
              "見出し": ft.Icons.TITLE, "コメント": ft.Icons.COMMENT}
# Types that need a selector
NEEDS_SELECTOR = {"入力", "クリック"}
# Screenshot needs selector only for element/margin mode

def step_display(step):
    t = step["type"]
    if t == "見出し": return step.get("text", "")
    if t == "コメント": return step.get("text", "")
    if t == "入力":
        v = step.get("value", "{パターン}")
        if len(v) > 25: v = v[:22] + "..."
        return f"{step.get('selector','')}  \u2190  {v}"
    if t == "クリック": return step.get("selector", "")
    if t == "待機": return f"{step.get('seconds','1.0')}秒"
    if t == "スクショ":
        m = step.get("mode", "fullpage")
        if m == "margin": return f"要素+{step.get('margin_px','200')}px  {step.get('selector','')}"
        if m == "element": return f"要素  {step.get('selector','')}"
        return "ページ全体"
    return str(step)

def run_selenium_job(config, steps, patterns, log_cb, done_cb):
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
        outdir = config.get("output_dir", "./screenshots"); os.makedirs(outdir, exist_ok=True)
        clip = config.get("clipboard_copy") == "1"
        pats = patterns if patterns else [{"label":"run","value":""}]
        gss = 0
        for pi, pat in enumerate(pats, 1):
            label, value = pat.get("label",f"p{pi:03d}"), pat.get("value","")
            log_cb(f"=== [{pi}/{len(pats)}] {label} ({len(value)}文字) ===")
            driver.get(base); time.sleep(0.5); sc = 0
            for si, step in enumerate(steps, 1):
                st = step["type"]
                # Skip display-only types
                if st in ("見出し", "コメント"):
                    if st == "見出し": log_cb(f"--- {step.get('text','')} ---")
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
                    fn = f"{gss:03d}_{label}_ss{sc}.png"; fp = os.path.join(outdir, fn)
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
        log_cb(f"[完了] {len(pats)} パターン -> {outdir}")
    except Exception as x: log_cb(f"[ERROR] {x}")
    finally:
        if driver: driver.quit()
        done_cb()

# ===================================================================
# Persistence
# ===================================================================
CSV_HEADER = ["label", "value"]
CONFIG_FILE = "y_shot_config.ini"
STEPS_FILE = "y_shot_steps.json"
SELECTOR_BANK_FILE = "y_shot_selectors.json"

def load_csv(path):
    if not os.path.isfile(path): return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if "label" in r]

def save_csv(path, patterns):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER); w.writeheader(); w.writerows(patterns)

def load_config():
    import configparser
    c = configparser.ConfigParser(); c.read(CONFIG_FILE, encoding="utf-8")
    return dict(c["settings"]) if "settings" in c else {}

def save_config(data):
    import configparser
    c = configparser.ConfigParser(); c["settings"] = {k: str(v) for k,v in data.items()}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f: c.write(f)

def load_steps(path=STEPS_FILE):
    if not os.path.isfile(path): return []
    with open(path, "r", encoding="utf-8") as f: return json.load(f)

def save_steps(steps, path=STEPS_FILE):
    with open(path, "w", encoding="utf-8") as f: json.dump(steps, f, ensure_ascii=False, indent=2)

def load_selector_bank():
    if not os.path.isfile(SELECTOR_BANK_FILE): return {}
    with open(SELECTOR_BANK_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_selector_bank(bank):
    with open(SELECTOR_BANK_FILE, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

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
    page.window.width = 1300
    page.window.height = 900
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)

    state = {
        "steps": load_steps(), "patterns": [], "csv_path": "",
        "browser_driver": None, "browser_elements": [],
        "config": load_config(), "running": False, "selected_el": -1,
        "selector_bank": load_selector_bank(),
    }
    cfg = state["config"]
    csv_p = cfg.get("csv_path", "")
    if csv_p and os.path.isfile(csv_p):
        state["csv_path"] = csv_p; state["patterns"] = load_csv(csv_p)

    # ── Helpers ──

    def log(msg):
        log_list.controls.append(ft.Text(msg, size=12, selectable=True, font_family="Consolas"))
        if len(log_list.controls) > 300: log_list.controls.pop(0)
        page.update()

    def snack(msg, color=ft.Colors.GREEN_700):
        page.overlay.append(ft.SnackBar(ft.Text(msg, color=ft.Colors.WHITE), bgcolor=color, open=True))
        page.update()

    def open_dialog(dlg):
        page.overlay.append(dlg); dlg.open = True; page.update()

    def close_dialog(dlg):
        dlg.open = False; page.update()

    def save_all():
        c = dict(state["config"])
        c["browser_url"] = browser_url.value or ""
        c["browser_wait"] = browser_wait.value or "3.0"
        if state["csv_path"]: c["csv_path"] = state["csv_path"]
        save_config(c); save_steps(state["steps"])
        save_selector_bank(state["selector_bank"])

    def close_browser():
        if state["browser_driver"]:
            try: state["browser_driver"].quit()
            except: pass
            state["browser_driver"] = None

    def get_all_selectors():
        """Get selectors from bank + current browser elements."""
        sels = []
        for url, elems in state["selector_bank"].items():
            for el in elems:
                label = f"{el['selector']}  ({el.get('hint','')[:15]})"
                sels.append(el["selector"])
        for el in state["browser_elements"]:
            if el["selector"] not in sels:
                sels.append(el["selector"])
        return sels

    # ── Steps ──

    def refresh_steps():
        step_list.controls.clear()
        for i, s in enumerate(state["steps"]):
            t = s["type"]
            icon = STEP_ICONS.get(t, ft.Icons.HELP)

            if t == "見出し":
                step_list.controls.append(ft.Container(
                    ft.Row([
                        ft.Icon(ft.Icons.TITLE, color=ft.Colors.BLUE_800, size=18),
                        ft.Text(s.get("text",""), weight=ft.FontWeight.BOLD, size=14, color=ft.Colors.BLUE_800),
                        ft.IconButton(ft.Icons.DELETE, icon_size=16, on_click=lambda e, idx=i: del_step(idx)),
                    ], alignment=ft.MainAxisAlignment.START),
                    bgcolor=ft.Colors.BLUE_50, padding=ft.padding.symmetric(6, 12),
                    border_radius=6, margin=ft.margin.only(top=8, bottom=2),
                    on_click=lambda e, idx=i: show_step_dlg(idx)))
            elif t == "コメント":
                step_list.controls.append(ft.Container(
                    ft.Row([
                        ft.Icon(ft.Icons.COMMENT, color=ft.Colors.GREY_500, size=16),
                        ft.Text(s.get("text",""), size=12, italic=True, color=ft.Colors.GREY_600),
                        ft.IconButton(ft.Icons.DELETE, icon_size=16, on_click=lambda e, idx=i: del_step(idx)),
                    ]),
                    padding=ft.padding.symmetric(4, 12),
                    on_click=lambda e, idx=i: show_step_dlg(idx)))
            else:
                step_list.controls.append(ft.ListTile(
                    leading=ft.Icon(icon, color=ft.Colors.BLUE_600, size=20),
                    title=ft.Text(step_display(s), size=13),
                    subtitle=ft.Text(t, size=11, color=ft.Colors.GREY_500),
                    on_click=lambda e, idx=i: show_step_dlg(idx),
                    trailing=ft.IconButton(ft.Icons.DELETE, icon_size=16,
                                           on_click=lambda e, idx=i: del_step(idx)),
                    dense=True))
        page.update()

    def del_step(idx):
        if 0 <= idx < len(state["steps"]):
            state["steps"].pop(idx); refresh_steps()

    def show_step_dlg(idx):
        init = state["steps"][idx] if idx is not None else {}
        t0 = init.get("type", "入力")

        type_dd = ft.Dropdown(label="種類", width=160, value=t0,
                              options=[ft.dropdown.Option(t) for t in STEP_TYPES])

        all_sels = get_all_selectors()
        sel_field = ft.Dropdown(label="セレクタ", width=450, value=init.get("selector",""),
                                options=[ft.dropdown.Option(s) for s in all_sels],
                                editable=True) if all_sels else \
                    ft.TextField(label="セレクタ", width=450, value=init.get("selector",""))

        val_field = ft.TextField(label="値 ({パターン} で代入)", width=450,
                                 value=init.get("value","{パターン}"),
                                 multiline=True, min_lines=2, max_lines=4)
        sec_field = ft.TextField(label="秒数", width=120, value=init.get("seconds","1.0"))
        mode_dd = ft.Dropdown(label="スクショ範囲", width=180, value=init.get("mode","fullpage"),
                              options=[ft.dropdown.Option(m) for m in ["fullpage","element","margin"]])
        margin_f = ft.TextField(label="マージン(px)", width=120, value=init.get("margin_px","200"))
        text_f = ft.TextField(label="テキスト", width=450, value=init.get("text",""),
                              multiline=True, min_lines=1, max_lines=3)

        # Dynamic visibility
        def update_fields(e=None):
            t = type_dd.value
            sel_field.visible = t in ("入力", "クリック") or (t == "スクショ" and mode_dd.value in ("element","margin"))
            val_field.visible = (t == "入力")
            sec_field.visible = (t == "待機")
            mode_dd.visible = (t == "スクショ")
            margin_f.visible = (t == "スクショ" and mode_dd.value == "margin")
            text_f.visible = t in ("見出し", "コメント")
            page.update()

        type_dd.on_change = update_fields
        mode_dd.on_change = update_fields

        def on_ok(e):
            t = type_dd.value; step = {"type": t}
            if t in ("見出し", "コメント"):
                step["text"] = text_f.value
            elif t in ("入力", "クリック"):
                s = sel_field.value if hasattr(sel_field, 'value') else ""
                if not s: snack("セレクタを入力してください", ft.Colors.RED_600); return
                step["selector"] = s
                if t == "入力": step["value"] = val_field.value
            elif t == "待機":
                try: step["seconds"] = str(float(sec_field.value))
                except: snack("秒数を正しく入力", ft.Colors.RED_600); return
            elif t == "スクショ":
                step["mode"] = mode_dd.value
                s = sel_field.value if hasattr(sel_field, 'value') else ""
                if mode_dd.value in ("element","margin") and not s:
                    snack("element/marginではセレクタが必要です", ft.Colors.RED_600); return
                if s: step["selector"] = s
                if mode_dd.value == "margin":
                    try: step["margin_px"] = str(int(margin_f.value))
                    except: snack("マージンは整数で", ft.Colors.RED_600); return
            if idx is not None: state["steps"][idx] = step
            else: state["steps"].append(step)
            refresh_steps(); close_dialog(dlg)

        content = ft.Column([type_dd, text_f, sel_field, val_field, sec_field, mode_dd, margin_f],
                            tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, width=500, height=400)
        dlg = ft.AlertDialog(
            title=ft.Text("ステップ編集" if idx is not None else "ステップ追加"),
            content=content,
            actions=[ft.TextButton("OK", on_click=on_ok),
                     ft.TextButton("キャンセル", on_click=lambda e: close_dialog(dlg))])
        open_dialog(dlg)
        update_fields()  # Set initial visibility

    # ── Element browser ──

    def load_page_click(e):
        url = browser_url.value
        if not url: snack("URLを入力してください", ft.Colors.RED_600); return
        load_btn.disabled = True; el_status.value = "読込中..."; page.update()
        page.run_thread(do_load_page, url)

    def do_load_page(url):
        try:
            from selenium import webdriver
            if state["browser_driver"] is None:
                state["browser_driver"] = webdriver.Chrome()
                state["browser_driver"].set_window_size(1280, 900)
            ba = state["config"].get("basic_auth_user","").strip()
            load_url = build_auth_url(url, ba, state["config"].get("basic_auth_pass","")) if ba else url
            state["browser_driver"].get(load_url)
            try: wait = float(browser_wait.value)
            except: wait = 3.0
            time.sleep(wait)
            log(f"[DEBUG] title: {state['browser_driver'].title}")
            elems = collect_elements_python(state["browser_driver"])
            state["browser_elements"] = list(elems)
            # Save to selector bank
            clean_url = url.split("?")[0]  # Strip query params for key
            state["selector_bank"][clean_url] = elems
            update_el_table(elems, url)
            update_url_history(url)
        except Exception as ex:
            state["browser_driver"] = None; log(f"[ERROR] {ex}")
        finally:
            load_btn.disabled = False; page.update()

    def update_el_table(elems, url):
        el_table.rows.clear()
        for i, el in enumerate(elems):
            el_table.rows.append(ft.DataRow(
                cells=[ft.DataCell(ft.Text(el["tag"], size=12)),
                       ft.DataCell(ft.Text(el.get("type",""), size=12)),
                       ft.DataCell(ft.Text(el.get("id") or el.get("name",""), size=12)),
                       ft.DataCell(ft.Text(el.get("hint","")[:30], size=12)),
                       ft.DataCell(ft.Text(el["selector"], size=11, color=ft.Colors.GREY_600))],
                on_select_change=lambda e, idx=i: on_el_click(idx)))
        el_status.value = f"{len(elems)} 個の要素を検出"
        log(f"[要素ブラウザ] {url} -> {len(elems)} 要素")
        page.update()

    def update_url_history(url):
        """Add URL to dropdown options if not already present."""
        existing = [o.key for o in browser_url_dd.options]
        if url not in existing:
            browser_url_dd.options.append(ft.dropdown.Option(url))
        # Also add all bank URLs
        for burl in state["selector_bank"]:
            if burl not in existing:
                browser_url_dd.options.append(ft.dropdown.Option(burl))
        page.update()

    def on_url_history_select(e):
        browser_url.value = browser_url_dd.value
        page.update()

    def load_bank_url(e):
        """Load selectors from bank without opening browser."""
        url = browser_url_dd.value or browser_url.value
        if not url: return
        clean = url.split("?")[0]
        if clean in state["selector_bank"]:
            elems = state["selector_bank"][clean]
            state["browser_elements"] = list(elems)
            update_el_table(elems, url)
            snack(f"バンクから {len(elems)} 要素を読込")
        else:
            snack("このURLのセレクタは保存されていません", ft.Colors.ORANGE_600)

    def on_el_click(idx):
        state["selected_el"] = idx
        if idx < len(state["browser_elements"]) and state["browser_driver"]:
            sel = state["browser_elements"][idx]["selector"]
            try: state["browser_driver"].execute_script(HIGHLIGHT_JS, sel)
            except: pass

    def quick_add(stype):
        idx = state["selected_el"]
        if idx < 0 or idx >= len(state["browser_elements"]):
            snack("要素一覧の行をクリックしてから押してください", ft.Colors.ORANGE_600); return
        sel = state["browser_elements"][idx]["selector"]
        step = {"type": stype, "selector": sel}
        if stype == "入力": step["value"] = "{パターン}"
        state["steps"].append(step); refresh_steps()
        snack(f"{stype}ステップを追加: {sel}")

    def capture_form_click(e):
        if not state["browser_driver"]:
            snack("先にページを読み込んでください", ft.Colors.ORANGE_600); return
        try:
            fs = capture_form_values(state["browser_driver"])
            if not fs: snack("入力済みフォーム値がありません", ft.Colors.ORANGE_600); return
            state["steps"].extend(fs); refresh_steps()
            snack(f"フォーム値から {len(fs)} 件のステップを追加")
        except Exception as ex: log(f"[ERROR] {ex}")

    def close_browser_click(e):
        close_browser(); el_table.rows.clear(); state["browser_elements"].clear()
        el_status.value = "ブラウザを閉じました"; page.update()

    def sync_url_click(e):
        browser_url.value = state["config"].get("url",""); page.update()

    # ── Patterns ──

    def refresh_patterns():
        pat_table.rows.clear()
        for i, p in enumerate(state["patterns"]):
            v = p["value"]; d = v if len(v) <= 45 else v[:42] + "..."
            pat_table.rows.append(ft.DataRow(
                cells=[ft.DataCell(ft.Text(p["label"], size=12)),
                       ft.DataCell(ft.Text(d, size=12)),
                       ft.DataCell(ft.Text(str(len(v)), size=12))],
                on_select_change=lambda e, idx=i: show_pattern_dlg(idx)))
        page.update()

    def show_pattern_dlg(idx):
        init = state["patterns"][idx] if idx is not None else {}
        lf = ft.TextField(label="ラベル", width=400, value=init.get("label",""))
        vf = ft.TextField(label="入力値", width=400, value=init.get("value",""),
                          multiline=True, min_lines=4, max_lines=8)
        def on_ok(e):
            if not lf.value: snack("ラベルを入力してください", ft.Colors.RED_600); return
            p = {"label": lf.value, "value": vf.value}
            if idx is not None: state["patterns"][idx] = p
            else: state["patterns"].append(p)
            refresh_patterns(); close_dialog(dlg)
        dlg = ft.AlertDialog(title=ft.Text("パターン編集" if idx is not None else "パターン追加"),
            content=ft.Column([lf, vf], tight=True, spacing=10, width=450),
            actions=[ft.TextButton("OK", on_click=on_ok),
                     ft.TextButton("キャンセル", on_click=lambda e: close_dialog(dlg))])
        open_dialog(dlg)

    def load_template(e):
        td = get_templates_dir()
        if not td: snack("templates フォルダが見つかりません", ft.Colors.RED_600); return
        csvs = sorted([f for f in os.listdir(td) if f.lower().endswith(".csv")])
        if not csvs: snack("テンプレートCSVがありません", ft.Colors.RED_600); return
        def on_sel(name):
            loaded = load_csv(os.path.join(td, name))
            state["patterns"].extend(loaded); refresh_patterns()
            snack(f"{os.path.splitext(name)[0]}: {len(loaded)} 件追加"); close_dialog(dlg)
        cards = [ft.Card(ft.Container(ft.Column([
            ft.Text(os.path.splitext(f)[0], weight=ft.FontWeight.BOLD, size=14),
            ft.Text(f"{len(load_csv(os.path.join(td,f)))} パターン", size=12, color=ft.Colors.GREY_600)],
            spacing=4), padding=16, on_click=lambda e, fn=f: on_sel(fn)), elevation=2) for f in csvs]
        dlg = ft.AlertDialog(title=ft.Text("テンプレート選択"),
            content=ft.Column(cards, spacing=8, scroll=ft.ScrollMode.AUTO, width=400, height=350),
            actions=[ft.TextButton("閉じる", on_click=lambda e: close_dialog(dlg))])
        open_dialog(dlg)

    def gen_input_check(e):
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
            state["patterns"].extend(ps); refresh_patterns()
            snack(f"入力チェック用 {len(ps)} 件追加"); close_dialog(dlg)
        dlg = ft.AlertDialog(title=ft.Text("入力チェック用パターン"),
            content=ft.Column([mf, ft.Text("未入力/スペース/全角半角/記号/絵文字/4バイト文字 + 境界値",
                size=12, color=ft.Colors.GREY_600)], tight=True, spacing=10, width=380),
            actions=[ft.TextButton("追加", on_click=on_ok),
                     ft.TextButton("閉じる", on_click=lambda e: close_dialog(dlg))])
        open_dialog(dlg)

    def gen_nchar(e):
        cf = ft.TextField(label="繰り返す文字", value="あ", width=80)
        nf = ft.TextField(label="文字数リスト", value="1\n50\n100\n255\n256", multiline=True, min_lines=5)
        def on_ok(e):
            ch = cf.value or "あ"
            for l in nf.value.strip().splitlines():
                if l.strip().isdigit(): state["patterns"].append({"label":f"nchar_{l.strip()}","value":ch*int(l.strip())})
            refresh_patterns(); snack("N文字パターンを追加"); close_dialog(dlg)
        dlg = ft.AlertDialog(title=ft.Text("N文字パターン生成"),
            content=ft.Column([cf, nf], tight=True, spacing=10, width=300),
            actions=[ft.TextButton("生成", on_click=on_ok),
                     ft.TextButton("閉じる", on_click=lambda e: close_dialog(dlg))])
        open_dialog(dlg)

    # ── Settings / Info ──

    def show_settings(e):
        c = state["config"]
        uf = ft.TextField(label="対象URL", value=c.get("url",""), width=450)
        auf = ft.TextField(label="Basic認証ID", value=c.get("basic_auth_user",""), width=210)
        apf = ft.TextField(label="パスワード", value=c.get("basic_auth_pass",""), password=True, width=210)
        of = ft.TextField(label="出力フォルダ", value=c.get("output_dir","./screenshots"), width=450)
        cc = ft.Checkbox(label="スクショをクリップボードにコピー", value=c.get("clipboard_copy")=="1")
        def on_ok(e):
            state["config"].update({"url":uf.value,"basic_auth_user":auf.value,
                "basic_auth_pass":apf.value,"output_dir":of.value,
                "clipboard_copy":"1" if cc.value else "0"})
            save_config(state["config"]); snack("設定を保存しました"); close_dialog(dlg)
        dlg = ft.AlertDialog(title=ft.Text(f"{APP_NAME} - 設定"),
            content=ft.Column([uf, ft.Row([auf, apf], spacing=10), of, cc],
                tight=True, spacing=12, width=500, scroll=ft.ScrollMode.AUTO),
            actions=[ft.TextButton("OK", on_click=on_ok),
                     ft.TextButton("キャンセル", on_click=lambda e: close_dialog(dlg))])
        open_dialog(dlg)

    def show_info(e):
        dlg = ft.AlertDialog(title=ft.Text(f"{APP_NAME} について"),
            content=ft.Column([ft.Text(f"{APP_NAME}  v{APP_VERSION}", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Web Screenshot Automation Tool", size=14), ft.Divider(),
                ft.Text(f"Developed by {APP_AUTHOR}", size=13)], tight=True, spacing=8, width=320),
            actions=[ft.TextButton("閉じる", on_click=lambda e: close_dialog(dlg))])
        open_dialog(dlg)

    # ── Run ──

    def run_click(e):
        c = state["config"]
        if not c.get("url"): snack("設定からURLを入力してください", ft.Colors.RED_600); return
        if not state["steps"]: snack("ステップが0件です", ft.Colors.RED_600); return
        close_browser(); state["running"] = True
        run_btn.disabled = True; progress.visible = True
        nav_bar.selected_index = 0; switch_tab(0); page.update(); save_all()
        def on_done():
            state["running"] = False; run_btn.disabled = False; progress.visible = False; page.update()
        page.run_thread(run_selenium_job, dict(c), list(state["steps"]),
                        list(state["patterns"]), lambda m: log(m), on_done)

    # ── Tab switch ──

    def switch_tab(idx):
        step_content.visible = (idx == 0); pat_content.visible = (idx == 1); page.update()

    def on_nav_change(e):
        switch_tab(e.control.selected_index)

    # ── Build controls ──

    browser_url = ft.TextField(label="URL", expand=True, dense=True, value=cfg.get("browser_url",""))
    browser_url_dd = ft.Dropdown(label="履歴", width=250,
                                  options=[ft.dropdown.Option(u) for u in state["selector_bank"].keys()],
                                  on_change=on_url_history_select, dense=True)
    browser_wait = ft.TextField(label="待機(秒)", width=70, dense=True, value=cfg.get("browser_wait","3.0"))
    load_btn = ft.ElevatedButton("ページ読込", icon=ft.Icons.REFRESH, on_click=load_page_click)
    el_status = ft.Text("ページ未読込", size=12, color=ft.Colors.GREY_500)
    el_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("タグ",size=12)), ft.DataColumn(ft.Text("type",size=12)),
                 ft.DataColumn(ft.Text("id/name",size=12)), ft.DataColumn(ft.Text("ヒント",size=12)),
                 ft.DataColumn(ft.Text("セレクタ",size=12))],
        rows=[], column_spacing=10, data_row_min_height=30, heading_row_height=34)

    step_list = ft.ListView(spacing=1, auto_scroll=False, expand=True)
    log_list = ft.ListView(spacing=1, auto_scroll=True, height=160)
    pat_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("ラベル",size=12)), ft.DataColumn(ft.Text("入力値",size=12)),
                 ft.DataColumn(ft.Text("文字数",size=12), numeric=True)],
        rows=[], column_spacing=20, data_row_min_height=30)
    progress = ft.ProgressBar(visible=False)
    run_btn = ft.ElevatedButton("実行", icon=ft.Icons.PLAY_ARROW, bgcolor=ft.Colors.BLUE_600,
                                color=ft.Colors.WHITE, on_click=run_click, height=44)

    # ── Layout: Step tab ──

    step_content = ft.Row([
        ft.Column([
            ft.Container(ft.Column([
                ft.Row([ft.Text("ステップ", weight=ft.FontWeight.BOLD, size=15),
                        ft.Row([
                            ft.IconButton(ft.Icons.ADD, tooltip="ステップ追加",
                                          on_click=lambda e: show_step_dlg(None)),
                            ft.IconButton(ft.Icons.TITLE, tooltip="見出し追加",
                                          on_click=lambda e: (state["steps"].append({"type":"見出し","text":"セクション"}), refresh_steps())),
                            ft.IconButton(ft.Icons.COMMENT, tooltip="コメント追加",
                                          on_click=lambda e: (state["steps"].append({"type":"コメント","text":"メモ"}), refresh_steps())),
                        ], spacing=0)],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text("パターンごとに繰り返し実行。タップで編集。", size=11, color=ft.Colors.GREY_500),
                step_list], spacing=6),
                padding=12, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=8, expand=True),
            ft.Container(ft.Column([ft.Text("ログ", weight=ft.FontWeight.BOLD, size=13), log_list]),
                padding=10, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=8)
        ], expand=3, spacing=8),

        ft.Container(ft.Column([
            ft.Text("要素ブラウザ", weight=ft.FontWeight.BOLD, size=15),
            ft.Row([browser_url, browser_wait], spacing=8),
            ft.Row([browser_url_dd,
                    ft.OutlinedButton("バンクから読込", icon=ft.Icons.DOWNLOAD, on_click=load_bank_url)], spacing=8),
            ft.Row([load_btn,
                    ft.OutlinedButton("閉じる", on_click=close_browser_click),
                    ft.TextButton("<- 設定URL", on_click=sync_url_click)], spacing=4, wrap=True),
            el_status,
            ft.Container(ft.Column([el_table], scroll=ft.ScrollMode.AUTO),
                height=300, border=ft.border.all(1, ft.Colors.GREY_200), border_radius=4),
            ft.Row([ft.ElevatedButton("+ 入力", icon=ft.Icons.EDIT, on_click=lambda e: quick_add("入力")),
                    ft.ElevatedButton("+ クリック", icon=ft.Icons.MOUSE, on_click=lambda e: quick_add("クリック")),
                    ft.ElevatedButton("フォーム値取得", icon=ft.Icons.SAVE, on_click=capture_form_click)], spacing=6)
        ], spacing=6), padding=12, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=8, expand=2)
    ], spacing=10, expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

    # ── Layout: Pattern tab ──

    pat_content = ft.Column([
        ft.Row([ft.ElevatedButton("追加", icon=ft.Icons.ADD, on_click=lambda e: show_pattern_dlg(None)),
                ft.ElevatedButton("テンプレート", icon=ft.Icons.FOLDER_OPEN, on_click=load_template),
                ft.ElevatedButton("入力チェック用", icon=ft.Icons.CHECKLIST, on_click=gen_input_check),
                ft.ElevatedButton("N文字生成", icon=ft.Icons.TEXT_FIELDS, on_click=gen_nchar),
                ft.OutlinedButton("全削除", on_click=lambda e: (state["patterns"].clear(), refresh_patterns()))],
               spacing=6, wrap=True),
        ft.Container(ft.Column([pat_table], scroll=ft.ScrollMode.AUTO),
            expand=True, border=ft.border.all(1, ft.Colors.GREY_200), border_radius=4)
    ], spacing=10, expand=True, visible=False)

    nav_bar = ft.NavigationBar(
        destinations=[ft.NavigationBarDestination(icon=ft.Icons.LIST_ALT, label="ステップ"),
                      ft.NavigationBarDestination(icon=ft.Icons.DATASET, label="テストパターン登録")],
        selected_index=0, on_change=on_nav_change)

    page.appbar = ft.AppBar(
        title=ft.Text(APP_NAME, weight=ft.FontWeight.BOLD), center_title=False,
        bgcolor=ft.Colors.BLUE_50,
        actions=[ft.IconButton(ft.Icons.SETTINGS, tooltip="設定", on_click=show_settings),
                 ft.IconButton(ft.Icons.INFO_OUTLINE, tooltip="情報", on_click=show_info)])

    page.add(ft.Column([
        ft.Stack([step_content, pat_content], expand=True),
        progress, ft.Row([run_btn], alignment=ft.MainAxisAlignment.END)
    ], expand=True, spacing=6))
    page.navigation_bar = nav_bar

    refresh_steps(); refresh_patterns()
    # Load bank URLs into dropdown
    for u in state["selector_bank"]:
        browser_url_dd.options.append(ft.dropdown.Option(u))

    page.on_close = lambda e: (save_all(), close_browser())

if __name__ == "__main__":
    ft.run(main)
