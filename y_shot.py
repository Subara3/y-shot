"""
y-shot: Web Screenshot Automation Tool  v0.7
  - Tab-based UI (Steps / Patterns)
  - Settings via gear dialog
  - Info dialog
  - image button detection
"""

import csv
import os
import sys
import json
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
from urllib.parse import urlparse, urlunparse

APP_NAME = "y-shot"
APP_VERSION = "0.7"
APP_AUTHOR = "Yuri Norimatsu"

# ---------------------------------------------------------------------------
# Element collection (Python-based, no fragile JS)
# ---------------------------------------------------------------------------

def collect_elements_python(driver):
    """Collect interactive elements using Selenium Python API."""
    from selenium.webdriver.common.by import By
    results = []
    seen = set()
    css = ("input, textarea, select, button, a, "
           "[role='button'], [type='submit'], [type='image'], "
           "img[onclick], img[role='button'], "
           "[onclick], li[id], span[id], div[onclick]")
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, css)
    except Exception:
        return results
    for el in elements:
        try:
            if not el.is_displayed():
                etype = el.get_attribute("type") or ""
                if etype not in ("radio", "checkbox"):
                    continue
            tag = el.tag_name.lower()
            etype = el.get_attribute("type") or ""
            if etype == "hidden":
                continue
            eid = el.get_attribute("id") or ""
            ename = el.get_attribute("name") or ""
            placeholder = el.get_attribute("placeholder") or ""
            src = el.get_attribute("src") or ""
            alt = el.get_attribute("alt") or ""
            text = (el.text or "").strip()[:50].replace("\n", " ")
            value = (el.get_attribute("value") or "")[:30]
            selector = _build_selector(driver, el, tag, eid, ename)
            if selector in seen:
                continue
            seen.add(selector)
            # hint: best available human-readable info
            hint = placeholder or alt or text or value or src[:30]
            results.append({
                "selector": selector, "tag": tag, "type": etype,
                "name": ename, "id": eid, "placeholder": placeholder,
                "text": text, "value": value, "hint": hint,
                "frame": "(main)"
            })
        except Exception:
            continue
    return results


def _build_selector(driver, el, tag, eid, ename):
    from selenium.webdriver.common.by import By
    if eid:
        return f"#{eid}"
    if ename:
        sel = f'{tag}[name="{ename}"]'
        try:
            if len(driver.find_elements(By.CSS_SELECTOR, sel)) == 1:
                return sel
        except Exception:
            pass
    etype = el.get_attribute("type") or ""
    if etype and ename:
        sel = f'{tag}[type="{etype}"][name="{ename}"]'
        try:
            if len(driver.find_elements(By.CSS_SELECTOR, sel)) == 1:
                return sel
        except Exception:
            pass
    classes = (el.get_attribute("class") or "").strip()
    if classes:
        cls_parts = classes.split()[:2]
        cls_sel = tag + "".join(f".{c}" for c in cls_parts)
        try:
            if len(driver.find_elements(By.CSS_SELECTOR, cls_sel)) == 1:
                return cls_sel
        except Exception:
            pass
    try:
        idx = driver.execute_script("""
            var el=arguments[0], p=el.parentElement;
            if(!p) return 0;
            var s=[]; for(var i=0;i<p.children.length;i++) if(p.children[i].tagName===el.tagName) s.push(p.children[i]);
            for(var j=0;j<s.length;j++) if(s[j]===el) return j+1;
            return 0;""", el)
        if idx and idx > 0:
            pid = driver.execute_script(
                "var p=arguments[0].parentElement; return p?(p.id||''):'';", el)
            if pid:
                return f"#{pid} > {tag}:nth-of-type({idx})"
            pname = driver.execute_script(
                "var p=arguments[0].parentElement; return p?(p.tagName||'').toLowerCase():'';", el)
            if pname:
                return f"{pname} > {tag}:nth-of-type({idx})"
    except Exception:
        pass
    return tag


HIGHLIGHT_JS = """
(function(selector, frameName) {
    function removeOld(doc) {
        try { var p=doc.getElementById('__yshot_hl'); if(p) p.remove();
              var l=doc.getElementById('__yshot_hl_label'); if(l) l.remove(); } catch(e) {}
    }
    removeOld(document);
    try {
        var doc=document;
        var el=doc.querySelector(selector);
        if(!el) return 'not_found';
        el.scrollIntoView({block:'center',behavior:'instant'});
        var r=el.getBoundingClientRect();
        var hl=doc.createElement('div'); hl.id='__yshot_hl';
        hl.style.cssText='position:fixed;border:3px solid #FF4444;background:rgba(255,68,68,0.15);z-index:2147483647;pointer-events:none;border-radius:3px;';
        hl.style.top=r.top-3+'px'; hl.style.left=r.left-3+'px';
        hl.style.width=r.width+6+'px'; hl.style.height=r.height+6+'px';
        doc.body.appendChild(hl);
        var lbl=doc.createElement('div'); lbl.id='__yshot_hl_label'; lbl.textContent=selector;
        lbl.style.cssText='position:fixed;z-index:2147483647;background:#FF4444;color:#fff;font:bold 11px monospace;padding:2px 6px;border-radius:2px;pointer-events:none;white-space:nowrap;max-width:400px;overflow:hidden;text-overflow:ellipsis;';
        var lt=r.top-22; if(lt<0) lt=r.bottom+4;
        lbl.style.top=lt+'px'; lbl.style.left=r.left+'px';
        doc.body.appendChild(lbl);
        return 'ok';
    } catch(e) { return 'error:'+e.message; }
})(arguments[0], arguments[1]);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_auth_url(url, user, password):
    if not user:
        return url
    parsed = urlparse(url)
    netloc = f"{user}:{password}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def copy_image_to_clipboard(filepath):
    """Copy a PNG image to the Windows clipboard."""
    try:
        from PIL import Image
        import io
        img = Image.open(filepath)
        # Convert to BMP for clipboard (Windows)
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        bmp_data = output.getvalue()[14:]  # strip BMP file header

        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_DIB = 8

        user32.OpenClipboard(0)
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(0x0042, len(bmp_data))  # GMEM_MOVEABLE | GMEM_ZEROINIT
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, bmp_data, len(bmp_data))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_DIB, h)
        user32.CloseClipboard()
        return True
    except Exception:
        return False


STEP_TYPES = ["入力", "クリック", "待機", "スクショ"]


def step_display(step):
    t = step["type"]
    if t == "入力":
        sel = step.get("selector", "")
        val = step.get("value", "{パターン}")
        if len(val) > 30:
            val = val[:27] + "..."
        return f"[入力] {sel}  <- {val}"
    elif t == "クリック":
        return f"[クリック] {step.get('selector', '')}"
    elif t == "待機":
        return f"[待機] {step.get('seconds', '1.0')}秒"
    elif t == "スクショ":
        mode = step.get("mode", "fullpage")
        if mode == "margin":
            px = step.get("margin_px", "200")
            return f"[スクショ] 要素+{px}px  {step.get('selector', '')}"
        elif mode == "rect":
            rx = step.get("rect_x", "0")
            ry = step.get("rect_y", "0")
            rw = step.get("rect_w", "0")
            rh = step.get("rect_h", "0")
            sy = step.get("scroll_y", "0")
            return f"[スクショ] 座標({rx},{ry} {rw}x{rh}) scroll={sy}"
        return f"[スクショ] {mode}"
    return str(step)


# ---------------------------------------------------------------------------
# Selenium job runner
# ---------------------------------------------------------------------------

def run_selenium_job(config, steps, patterns, log_callback, done_callback):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        log_callback("[ERROR] selenium が見つかりません。")
        done_callback()
        return

    opts = Options()
    if config.get("headless"):
        opts.add_argument("--headless=new")

    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.set_window_size(int(config.get("window_w", 1280)),
                               int(config.get("window_h", 900)))
        ba_user = config.get("basic_auth_user", "").strip()
        ba_pass = config.get("basic_auth_pass", "")
        base_url = build_auth_url(config["url"], ba_user, ba_pass)
        if ba_user:
            log_callback("[INFO] Basic認証をURL埋込で設定")

        output_dir = config.get("output_dir", "./screenshots")
        os.makedirs(output_dir, exist_ok=True)

        total = len(patterns) if patterns else 1
        pattern_list = patterns if patterns else [{"label": "run", "value": ""}]
        global_ss_num = 0  # Global sequential number across all patterns
        clipboard = config.get("clipboard_copy") == "1"
        if clipboard:
            log_callback("[INFO] スクショをクリップボードにコピーします")

        for p_idx, pat in enumerate(pattern_list, start=1):
            label = pat.get("label", f"pattern_{p_idx:03d}")
            value = pat.get("value", "")
            log_callback(f"=== [{p_idx}/{total}] {label} ({len(value)}文字) ===")
            driver.get(base_url)
            time.sleep(0.5)
            ss_count = 0

            for s_idx, step in enumerate(steps, start=1):
                stype = step["type"]
                if stype == "入力":
                    sel = step.get("selector", "")
                    input_val = step.get("value", "{パターン}")
                    input_val = input_val.replace("{パターン}", value).replace("{pattern}", value)
                    try:
                        el = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                        el.clear()
                        el.send_keys(input_val)
                        log_callback(f"  S{s_idx} 入力: {sel} <- ({len(input_val)}文字)")
                    except Exception as ex:
                        log_callback(f"  S{s_idx} [WARN] 入力失敗: {ex}")
                elif stype == "クリック":
                    sel = step.get("selector", "")
                    try:
                        btn = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                        btn.click()
                        log_callback(f"  S{s_idx} クリック: {sel}")
                    except Exception as ex:
                        log_callback(f"  S{s_idx} [WARN] クリック失敗: {ex}")
                elif stype == "待機":
                    sec = float(step.get("seconds", "1.0"))
                    time.sleep(sec)
                    log_callback(f"  S{s_idx} 待機: {sec}秒")
                elif stype == "スクショ":
                    ss_count += 1
                    global_ss_num += 1
                    mode = step.get("mode", "fullpage")
                    sel = step.get("selector", "")
                    fn = f"{global_ss_num:03d}_{label}_ss{ss_count}.png"
                    fp = os.path.join(output_dir, fn)
                    try:
                        if mode == "element" and sel:
                            driver.find_element(By.CSS_SELECTOR, sel).screenshot(fp)
                        elif mode == "margin" and sel:
                            margin = int(step.get("margin_px", 200))
                            driver.save_screenshot(fp)
                            target = driver.find_element(By.CSS_SELECTOR, sel)
                            loc = target.location
                            size = target.size
                            from PIL import Image
                            img = Image.open(fp)
                            dpr = driver.execute_script("return window.devicePixelRatio || 1;")
                            x1 = max(0, int(loc["x"] * dpr) - margin)
                            y1 = max(0, int(loc["y"] * dpr) - margin)
                            x2 = min(img.width, int((loc["x"] + size["width"]) * dpr) + margin)
                            y2 = min(img.height, int((loc["y"] + size["height"]) * dpr) + margin)
                            cropped = img.crop((x1, y1, x2, y2))
                            cropped.save(fp)
                            log_callback(f"  S{s_idx} スクショ(margin {margin}px): {fn}")
                        elif mode == "rect":
                            scroll_y = int(step.get("scroll_y", 0))
                            driver.execute_script(f"window.scrollTo(0, {scroll_y});")
                            time.sleep(0.3)
                            driver.save_screenshot(fp)
                            from PIL import Image
                            img = Image.open(fp)
                            dpr = driver.execute_script("return window.devicePixelRatio || 1;")
                            rx = int(int(step.get("rect_x", 0)) * dpr)
                            ry = int(int(step.get("rect_y", 0)) * dpr)
                            rw = int(int(step.get("rect_w", 800)) * dpr)
                            rh = int(int(step.get("rect_h", 600)) * dpr)
                            rx = max(0, min(rx, img.width))
                            ry = max(0, min(ry, img.height))
                            x2 = min(img.width, rx + rw)
                            y2 = min(img.height, ry + rh)
                            cropped = img.crop((rx, ry, x2, y2))
                            cropped.save(fp)
                            log_callback(f"  S{s_idx} スクショ(rect scroll={scroll_y}): {fn}")
                        else:
                            driver.save_screenshot(fp)
                            log_callback(f"  S{s_idx} スクショ: {fn}")
                        # Clipboard copy
                        if clipboard:
                            if copy_image_to_clipboard(fp):
                                log_callback(f"  -> クリップボードにコピー済み")
                            else:
                                log_callback(f"  -> [WARN] クリップボードコピー失敗")
                    except Exception as ex:
                        log_callback(f"  S{s_idx} [WARN] スクショ失敗: {ex}")

        log_callback(f"[完了] {total} パターン x {len(steps)} ステップ -> {output_dir}")
    except Exception as ex:
        log_callback(f"[ERROR] {ex}")
    finally:
        if driver:
            driver.quit()
        done_callback()


# ---------------------------------------------------------------------------
# CSV / Config / Steps persistence
# ---------------------------------------------------------------------------
CSV_HEADER = ["label", "value"]


def load_csv(path):
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.DictReader(f) if "label" in row]


def save_csv(path, patterns):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(patterns)


CONFIG_FILE = "y_shot_config.ini"
STEPS_FILE = "y_shot_steps.json"


def load_config():
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE, encoding="utf-8")
    return dict(cfg["settings"]) if "settings" in cfg else {}


def save_config(data):
    import configparser
    cfg = configparser.ConfigParser()
    cfg["settings"] = {k: str(v) for k, v in data.items()}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


def load_steps(path=STEPS_FILE):
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_steps(steps, path=STEPS_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(steps, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class YShotApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  - Web Screenshot Tool")
        self.geometry("1100x750")
        self.resizable(True, True)
        self.steps = []
        self.patterns = []
        self.csv_path = ""
        self.running = False
        self.browser_driver = None
        self.browser_elements = []

        self._build_ui()
        self._load_all()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        self._save_all()
        self._close_browser()
        self.destroy()

    def _close_browser(self):
        if self.browser_driver:
            try:
                self.browser_driver.quit()
            except Exception:
                pass
            self.browser_driver = None

    # ================================================================
    # UI Build
    # ================================================================

    def _build_ui(self):
        pad = dict(padx=6, pady=3)

        # ── Top bar: gear + info ──
        topbar = ttk.Frame(self)
        topbar.pack(fill="x", padx=8, pady=(6, 2))

        ttk.Label(topbar, text=APP_NAME, font=("", 13, "bold")).pack(side="left")

        # Info button
        info_btn = ttk.Button(topbar, text="\u2139", width=3, command=self._show_info)
        info_btn.pack(side="right", padx=2)

        # Gear button
        gear_btn = ttk.Button(topbar, text="\u2699", width=3, command=self._show_settings)
        gear_btn.pack(side="right", padx=2)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8)

        # ── Notebook (tabs) ──
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)

        # Tab 1: Steps + Element Browser + Log
        tab_step = ttk.Frame(self.notebook)
        self.notebook.add(tab_step, text=" ステップ ")

        # Tab 2: Patterns
        tab_pat = ttk.Frame(self.notebook)
        self.notebook.add(tab_pat, text=" テストパターン登録 ")

        # ── Build Tab 1 ──
        self._build_step_tab(tab_step, pad)

        # ── Build Tab 2 ──
        self._build_pattern_tab(tab_pat, pad)

        # ── Bottom bar (always visible) ──
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=8, pady=(2, 6))
        self.run_btn = ttk.Button(bottom, text="実行", command=self._run)
        self.run_btn.pack(side="right", padx=4)

    # ---- Tab 1: Steps ----

    def _build_step_tab(self, parent, pad):
        pw = ttk.PanedWindow(parent, orient="horizontal")
        pw.pack(fill="both", expand=True)

        left = ttk.Frame(pw)
        right = ttk.Frame(pw)
        pw.add(left, weight=3)
        pw.add(right, weight=2)

        # Steps list
        stf = ttk.LabelFrame(left, text="ステップ (パターンごとに繰り返し実行)")
        stf.pack(fill="both", expand=True, **pad)

        stb = ttk.Frame(stf)
        stb.pack(fill="x", **pad)
        for txt, cmd in [("追加", self._add_step), ("編集", self._edit_step),
                         ("削除", self._delete_step)]:
            ttk.Button(stb, text=txt, command=cmd).pack(side="left", padx=2)
        ttk.Separator(stb, orient="vertical").pack(side="left", fill="y", padx=6)
        for txt, cmd in [("上へ", self._move_step_up), ("下へ", self._move_step_down)]:
            ttk.Button(stb, text=txt, command=cmd).pack(side="left", padx=2)
        ttk.Separator(stb, orient="vertical").pack(side="left", fill="y", padx=6)
        for txt, cmd in [("読込", self._load_steps_file), ("保存", self._save_steps_file)]:
            ttk.Button(stb, text=txt, command=cmd).pack(side="left", padx=2)
        ttk.Separator(stb, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(stb, text="プリセット: 入力チェック", command=self._preset_input_check).pack(
            side="left", padx=2)

        self.step_listbox = tk.Listbox(stf, height=10, font=("Consolas", 10))
        self.step_listbox.pack(fill="both", expand=True, **pad)
        self.step_listbox.bind("<Double-Button-1>", lambda e: self._edit_step())

        # Log (below steps)
        lf = ttk.LabelFrame(left, text="ログ")
        lf.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(lf, height=8, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, **pad)

        # Element browser (right)
        self._build_element_browser(right, pad)

    # ---- Element browser ----

    def _build_element_browser(self, parent, pad):
        eb = ttk.LabelFrame(parent, text="要素ブラウザ")
        eb.pack(fill="both", expand=True, **pad)

        uf = ttk.Frame(eb)
        uf.pack(fill="x", **pad)
        ttk.Label(uf, text="URL:").pack(side="left")
        self.browser_url_var = tk.StringVar()
        ttk.Entry(uf, textvariable=self.browser_url_var, width=28).pack(
            side="left", fill="x", expand=True, padx=4)

        bf = ttk.Frame(eb)
        bf.pack(fill="x", padx=6, pady=2)
        self.load_btn = ttk.Button(bf, text="ページ読込", command=self._load_page)
        self.load_btn.pack(side="left", padx=2)
        self.rescan_btn = ttk.Button(bf, text="再スキャン", command=self._rescan_page)
        self.rescan_btn.pack(side="left", padx=2)
        ttk.Button(bf, text="閉じる", command=self._close_browser_btn).pack(side="left", padx=2)
        ttk.Separator(bf, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(bf, text="<- 設定URLを使う", command=self._sync_url).pack(side="left", padx=2)

        wf = ttk.Frame(eb)
        wf.pack(fill="x", padx=6, pady=2)
        ttk.Label(wf, text="読込待機(秒):").pack(side="left")
        self.browser_wait_var = tk.StringVar(value="3.0")
        ttk.Entry(wf, textvariable=self.browser_wait_var, width=6).pack(side="left", padx=4)

        ff = ttk.Frame(eb)
        ff.pack(fill="x", **pad)
        ttk.Label(ff, text="フィルタ:").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *a: self._filter_elements())
        ttk.Entry(ff, textvariable=self.filter_var, width=14).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Label(ff, text="種別:").pack(side="left", padx=(6, 0))
        self.type_filter_var = tk.StringVar(value="全て")
        cb = ttk.Combobox(ff, textvariable=self.type_filter_var,
                          values=["全て", "input", "textarea", "select", "button", "a", "img", "li", "span", "div", "その他"],
                          width=8, state="readonly")
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self._filter_elements())

        # Treeview
        tree_frame = ttk.Frame(eb)
        tree_frame.pack(fill="both", expand=True, **pad)

        el_cols = ("tag", "type_attr", "id_name", "hint", "selector")
        self.el_tree = ttk.Treeview(tree_frame, columns=el_cols, show="headings", height=10)
        self.el_tree.heading("tag", text="タグ")
        self.el_tree.heading("type_attr", text="type")
        self.el_tree.heading("id_name", text="id/name")
        self.el_tree.heading("hint", text="ヒント")
        self.el_tree.heading("selector", text="セレクタ")
        self.el_tree.column("tag", width=50)
        self.el_tree.column("type_attr", width=55)
        self.el_tree.column("id_name", width=75)
        self.el_tree.column("hint", width=90)
        self.el_tree.column("selector", width=130)

        el_sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.el_tree.yview)
        self.el_tree.configure(yscrollcommand=el_sb.set)
        self.el_tree.pack(side="left", fill="both", expand=True)
        el_sb.pack(side="right", fill="y")

        self.el_tree.bind("<<TreeviewSelect>>", self._on_element_select)

        self.el_status_var = tk.StringVar(value="ページ未読込")
        ttk.Label(eb, textvariable=self.el_status_var, foreground="gray").pack(anchor="w", padx=8)

        qa = ttk.LabelFrame(eb, text="選択中の要素からステップ追加")
        qa.pack(fill="x", **pad)
        ttk.Button(qa, text="+ 入力ステップ",
                   command=lambda: self._quick_add_step("入力")).pack(side="left", padx=3, pady=2)
        ttk.Button(qa, text="+ クリックステップ",
                   command=lambda: self._quick_add_step("クリック")).pack(side="left", padx=3, pady=2)

    # ---- Tab 2: Patterns ----

    def _build_pattern_tab(self, parent, pad):
        tb = ttk.Frame(parent)
        tb.pack(fill="x", **pad)
        for txt, cmd in [("追加", self._add_pattern), ("編集", self._edit_pattern),
                         ("削除", self._delete_pattern)]:
            ttk.Button(tb, text=txt, command=cmd).pack(side="left", padx=2)
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(tb, text="テンプレート", command=self._load_template).pack(side="left", padx=2)
        ttk.Button(tb, text="N文字生成", command=self._generate_nchar).pack(side="left", padx=2)
        ttk.Button(tb, text="境界値生成", command=self._preset_input_patterns).pack(side="left", padx=2)
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=6)
        for txt, cmd in [("CSV読込", self._load_csv), ("CSV保存", self._save_csv)]:
            ttk.Button(tb, text=txt, command=cmd).pack(side="left", padx=2)
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(tb, text="全削除", command=self._clear_patterns).pack(side="left", padx=2)

        cols = ("label", "value", "length")
        self.tree = ttk.Treeview(parent, columns=cols, show="headings", height=16)
        self.tree.heading("label", text="ラベル")
        self.tree.heading("value", text="入力値")
        self.tree.heading("length", text="文字数")
        self.tree.column("label", width=140)
        self.tree.column("value", width=450)
        self.tree.column("length", width=60, anchor="center")
        tree_sb = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_sb.set)
        self.tree.pack(side="left", fill="both", expand=True, **pad)
        tree_sb.pack(side="right", fill="y")

    # ================================================================
    # Settings dialog
    # ================================================================

    def _show_settings(self):
        dlg = _SettingsDialog(self, self._get_config())
        if dlg.result:
            self._apply_config(dlg.result)
            self._log("[INFO] 設定を更新しました")

    # ================================================================
    # Info dialog
    # ================================================================

    def _show_info(self):
        info = (f"{APP_NAME}  v{APP_VERSION}\n\n"
                f"Web Screenshot Automation Tool\n\n"
                f"Developed by {APP_AUTHOR}")
        messagebox.showinfo(f"{APP_NAME} について", info)

    # ================================================================
    # Step management
    # ================================================================

    def _refresh_step_list(self):
        self.step_listbox.delete(0, tk.END)
        for i, s in enumerate(self.steps, 1):
            self.step_listbox.insert(tk.END, f" {i}. {step_display(s)}")

    def _get_selector_choices(self):
        """Get selector list from browser elements for combobox."""
        choices = []
        for el in self.browser_elements:
            sel = el.get("selector", "")
            hint = el.get("hint", "")
            tag = el.get("tag", "")
            if sel:
                display = f"{sel}  ({tag} {hint[:20]})" if hint else f"{sel}  ({tag})"
                choices.append((sel, display))
        return choices

    def _add_step(self):
        dlg = _StepDialog(self, title="ステップ追加",
                          selector_choices=self._get_selector_choices())
        if dlg.result:
            self.steps.append(dlg.result)
            self._refresh_step_list()

    def _edit_step(self):
        sel = self.step_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        dlg = _StepDialog(self, title="ステップ編集", initial=self.steps[idx],
                          selector_choices=self._get_selector_choices())
        if dlg.result:
            self.steps[idx] = dlg.result
            self._refresh_step_list()

    def _preset_input_check(self):
        """Insert preset steps for input validation testing."""
        choices = self._get_selector_choices()
        dlg = _PresetInputCheckDialog(self, choices)
        if dlg.result:
            self.steps.extend(dlg.result)
            self._refresh_step_list()
            self._log(f"[プリセット] 入力チェック {len(dlg.result)} ステップ追加")

    def _delete_step(self):
        sel = self.step_listbox.curselection()
        if not sel:
            return
        self.steps.pop(sel[0])
        self._refresh_step_list()

    def _move_step_up(self):
        sel = self.step_listbox.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        self.steps[i - 1], self.steps[i] = self.steps[i], self.steps[i - 1]
        self._refresh_step_list()
        self.step_listbox.selection_set(i - 1)

    def _move_step_down(self):
        sel = self.step_listbox.curselection()
        if not sel or sel[0] >= len(self.steps) - 1:
            return
        i = sel[0]
        self.steps[i + 1], self.steps[i] = self.steps[i], self.steps[i + 1]
        self._refresh_step_list()
        self.step_listbox.selection_set(i + 1)

    def _load_steps_file(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self.steps = load_steps(path)
            self._refresh_step_list()
            self._log(f"ステップ読込: {path} ({len(self.steps)} 件)")

    def _save_steps_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            save_steps(self.steps, path)
            self._log(f"ステップ保存: {path}")

    def _quick_add_step(self, stype):
        sel = self.el_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "右の一覧から要素を選択してください。")
            return
        idx = int(sel[0])
        if idx >= len(self.browser_elements):
            return
        selector = self.browser_elements[idx].get("selector", "")
        if stype == "入力":
            step = {"type": "入力", "selector": selector, "value": "{パターン}"}
        else:
            step = {"type": "クリック", "selector": selector}
        self.steps.append(step)
        self._refresh_step_list()
        hint = self.browser_elements[idx].get("id") or self.browser_elements[idx].get("name", "")
        self._log(f"[ステップ追加] {stype}: {hint} : {selector}")

    # ================================================================
    # Element browser
    # ================================================================

    def _sync_url(self):
        cfg = self._get_config()
        url = cfg.get("url", "").strip()
        if url:
            self.browser_url_var.set(url)

    def _load_page(self):
        url = self.browser_url_var.get().strip()
        if not url:
            messagebox.showwarning(APP_NAME, "URLを入力してください。")
            return
        self.load_btn.configure(state="disabled")
        self.rescan_btn.configure(state="disabled")
        self.el_status_var.set("読込中...")
        cfg = self._get_config()
        ba_user = cfg.get("basic_auth_user", "").strip()
        ba_pass = cfg.get("basic_auth_pass", "")
        wait = self.browser_wait_var.get()
        threading.Thread(target=self._load_page_thread,
                         args=(url, ba_user, ba_pass, wait, False), daemon=True).start()

    def _rescan_page(self):
        if not self.browser_driver:
            messagebox.showinfo(APP_NAME, "先にページを読み込んでください。")
            return
        self.rescan_btn.configure(state="disabled")
        self.el_status_var.set("再スキャン中...")
        threading.Thread(target=self._load_page_thread,
                         args=(None, None, None, "0.5", True), daemon=True).start()

    def _load_page_thread(self, url, ba_user, ba_pass, wait_str, rescan_only):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except ImportError:
            self.after(0, lambda: self._log("[ERROR] selenium が見つかりません。"))
            self.after(0, self._enable_browser_buttons)
            return
        try:
            if not rescan_only:
                if self.browser_driver is None:
                    self.browser_driver = webdriver.Chrome()
                    self.browser_driver.set_window_size(1280, 900)
                load_url = build_auth_url(url, ba_user, ba_pass) if ba_user else url
                if ba_user:
                    self.after(0, lambda: self._log("[INFO] Basic認証をURL埋込で設定"))
                self.browser_driver.get(load_url)

            try:
                wait_sec = float(wait_str)
            except ValueError:
                wait_sec = 3.0
            time.sleep(wait_sec)

            # Debug
            debug_lines = []
            try:
                debug_lines.append(f"[DEBUG] title: {self.browser_driver.title}")
            except Exception as ex:
                debug_lines.append(f"[DEBUG] title失敗: {ex}")
            try:
                counts = self.browser_driver.execute_script(
                    "return [document.querySelectorAll('*').length,"
                    " document.querySelectorAll('input').length,"
                    " document.querySelectorAll('form').length];")
                debug_lines.append(f"[DEBUG] 全要素: {counts[0]}, input: {counts[1]}, form: {counts[2]}")
            except Exception as ex:
                debug_lines.append(f"[DEBUG] カウント失敗: {ex}")

            snapshot = list(debug_lines)
            self.after(0, lambda lines=snapshot: [self._log(l) for l in lines])

            elements = collect_elements_python(self.browser_driver)
            display_url = url or self.browser_driver.current_url
            el_snapshot = list(elements)

            def update_ui(elems=el_snapshot, durl=display_url):
                self.browser_elements = elems
                self._enable_browser_buttons()
                self._populate_element_tree(elems)
                self.el_status_var.set(f"{len(elems)} 個の要素を検出")
                self._log(f"[要素ブラウザ] {durl} -> {len(elems)} 要素")
            self.after(0, update_ui)

        except Exception as e:
            err_msg = str(e)
            if not rescan_only:
                self.browser_driver = None
            def on_err(msg=err_msg):
                self._enable_browser_buttons()
                self.el_status_var.set("読込失敗")
                self._log(f"[ERROR] ページ読込: {msg}")
            self.after(0, on_err)

    def _enable_browser_buttons(self):
        self.load_btn.configure(state="normal")
        self.rescan_btn.configure(state="normal")

    def _populate_element_tree(self, elements):
        self.el_tree.delete(*self.el_tree.get_children())
        for i, el in enumerate(elements):
            try:
                tag = el.get("tag", "")
                type_attr = el.get("type", "")
                id_name = el.get("id") or el.get("name", "")
                hint = el.get("hint", "")
                if len(hint) > 35:
                    hint = hint[:32] + "..."
                selector = el.get("selector", "")
                self.el_tree.insert("", "end", iid=str(i),
                                    values=(tag, type_attr, id_name, hint, selector))
            except Exception as ex:
                self._log(f"[WARN] 要素{i}表示失敗: {ex}")

    def _filter_elements(self):
        text_filter = self.filter_var.get().lower()
        type_filter = self.type_filter_var.get()
        self.el_tree.delete(*self.el_tree.get_children())
        if not self.browser_elements:
            return
        for i, el in enumerate(self.browser_elements):
            try:
                tag = el.get("tag", "")
                type_attr = el.get("type", "")
                id_name = el.get("id") or el.get("name", "")
                hint = el.get("hint", "")
                if len(hint) > 35:
                    hint = hint[:32] + "..."
                selector = el.get("selector", "")
                if type_filter != "全て":
                    if type_filter == "その他":
                        if tag in ("input", "textarea", "select", "button", "a", "img", "li", "span", "div"):
                            continue
                    elif tag != type_filter:
                        continue
                if text_filter:
                    if text_filter not in f"{tag} {type_attr} {id_name} {hint} {selector}".lower():
                        continue
                self.el_tree.insert("", "end", iid=str(i),
                                    values=(tag, type_attr, id_name, hint, selector))
            except Exception:
                pass

    def _on_element_select(self, event):
        sel = self.el_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.browser_elements):
            return
        el = self.browser_elements[idx]
        selector = el.get("selector", "")
        frame = el.get("frame", "(main)")
        if self.browser_driver and selector:
            def do_hl():
                try:
                    self.browser_driver.execute_script(HIGHLIGHT_JS, selector, frame)
                except Exception:
                    pass
            threading.Thread(target=do_hl, daemon=True).start()

    def _close_browser_btn(self):
        self._close_browser()
        self.el_tree.delete(*self.el_tree.get_children())
        self.browser_elements = []
        self.el_status_var.set("ブラウザを閉じました")

    # ================================================================
    # Pattern management
    # ================================================================

    def _add_pattern(self):
        dlg = _PatternDialog(self, title="パターン追加")
        if dlg.result:
            self.patterns.append(dlg.result)
            self._refresh_tree()

    def _edit_pattern(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        dlg = _PatternDialog(self, title="パターン編集", initial=self.patterns[idx])
        if dlg.result:
            self.patterns[idx] = dlg.result
            self._refresh_tree()

    def _delete_pattern(self):
        sel = self.tree.selection()
        if not sel:
            return
        self.patterns.pop(self.tree.index(sel[0]))
        self._refresh_tree()

    def _clear_patterns(self):
        if self.patterns and messagebox.askyesno(APP_NAME, f"{len(self.patterns)} 件を全て削除しますか？"):
            self.patterns.clear()
            self._refresh_tree()

    def _generate_nchar(self):
        dlg = _NCharDialog(self)
        if dlg.result:
            self.patterns.extend(dlg.result)
            self._refresh_tree()
            self._log(f"N文字パターン {len(dlg.result)} 件追加")

    def _load_template(self):
        """テンプレートフォルダからCSVを選んで読み込む。"""
        # templates/ フォルダを探す（exeでもスクリプトでも動くように）
        base = os.path.dirname(os.path.abspath(__file__))
        tpl_dir = os.path.join(base, "templates")
        if not os.path.isdir(tpl_dir):
            # exe化時は実行ファイルの隣
            tpl_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "templates")
        if not os.path.isdir(tpl_dir):
            messagebox.showinfo(APP_NAME,
                                "templates フォルダが見つかりません。\n"
                                "実行ファイルと同じ場所に templates/ フォルダを作成し、\n"
                                "CSVファイルを入れてください。")
            return

        csvs = sorted([f for f in os.listdir(tpl_dir) if f.lower().endswith(".csv")])
        if not csvs:
            messagebox.showinfo(APP_NAME, "templates フォルダにCSVファイルがありません。")
            return

        dlg = _TemplateDialog(self, csvs)
        if dlg.result:
            path = os.path.join(tpl_dir, dlg.result)
            loaded = load_csv(path)
            if dlg.mode == "replace":
                self.patterns = loaded
            else:
                self.patterns.extend(loaded)
            self._refresh_tree()
            self._log(f"テンプレート読込: {dlg.result} ({len(loaded)} 件)")

    def _preset_input_patterns(self):
        """入力チェック用の標準パターンセットを一括追加。"""
        dlg = _InputCheckPatternDialog(self)
        if dlg.result:
            self.patterns.extend(dlg.result)
            self._refresh_tree()
            self._log(f"入力チェック用パターン {len(dlg.result)} 件追加")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for p in self.patterns:
            v = p["value"]
            d = v if len(v) <= 50 else v[:47] + "..."
            self.tree.insert("", "end", values=(p["label"], d, len(v)))

    def _load_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if path:
            self.csv_path = path
            self.patterns = load_csv(path)
            self._refresh_tree()
            self._log(f"CSV読込: {path} ({len(self.patterns)} 件)")

    def _save_csv(self):
        path = self.csv_path or filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            self.csv_path = path
            save_csv(path, self.patterns)
            self._log(f"CSV保存: {path}")

    # ================================================================
    # Log / Config / Run
    # ================================================================

    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _thread_log(self, msg):
        self.after(0, self._log, msg)

    def _get_config(self):
        """Read config from INI file (source of truth)."""
        return load_config()

    def _apply_config(self, data):
        """Save config dict to INI file."""
        if self.csv_path:
            data["csv_path"] = self.csv_path
        save_config(data)

    def _save_all(self):
        cfg = self._get_config()
        cfg["browser_url"] = self.browser_url_var.get()
        cfg["browser_wait"] = self.browser_wait_var.get()
        if self.csv_path:
            cfg["csv_path"] = self.csv_path
        save_config(cfg)
        save_steps(self.steps)

    def _load_all(self):
        data = load_config()
        self.browser_url_var.set(data.get("browser_url", ""))
        self.browser_wait_var.set(data.get("browser_wait", "3.0"))
        csv_p = data.get("csv_path", "")
        if csv_p and os.path.isfile(csv_p):
            self.csv_path = csv_p
            self.patterns = load_csv(csv_p)
            self._refresh_tree()
        self.steps = load_steps()
        self._refresh_step_list()

    def _run(self):
        if self.running:
            return
        config = self._get_config()
        if not config.get("url"):
            messagebox.showwarning(APP_NAME, "設定 (歯車) から対象URLを入力してください。")
            return
        if not self.steps:
            messagebox.showwarning(APP_NAME, "ステップが0件です。")
            return

        self._close_browser()
        self.running = True
        self.run_btn.configure(state="disabled")
        self._save_all()

        # Switch to step tab to show log
        self.notebook.select(0)

        def on_done():
            self.after(0, lambda: self.run_btn.configure(state="normal"))
            self.running = False

        threading.Thread(target=run_selenium_job,
                         args=(config, list(self.steps), list(self.patterns),
                               self._thread_log, on_done),
                         daemon=True).start()


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class _SettingsDialog(tk.Toplevel):
    """Settings dialog (gear button)."""
    def __init__(self, parent, current):
        super().__init__(parent)
        self.title(f"{APP_NAME} - 設定")
        self.result = None
        self.grab_set()
        self.resizable(False, False)
        pad = dict(padx=10, pady=5)

        fields = [
            ("対象URL:", "url"),
            ("Basic認証ID:", "basic_auth_user"),
            ("Basic認証パスワード:", "basic_auth_pass"),
            ("出力フォルダ:", "output_dir"),
        ]
        self.vars = {}
        for i, (label, key) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="e", **pad)
            v = tk.StringVar(value=current.get(key, ""))
            show = "*" if "pass" in key else ""
            e = ttk.Entry(self, textvariable=v, width=45, show=show)
            e.grid(row=i, column=1, sticky="ew", **pad)
            self.vars[key] = v

        # Default for output_dir
        if not self.vars["output_dir"].get():
            self.vars["output_dir"].set("./screenshots")

        # Browse button for output folder
        r = len(fields) - 1
        ttk.Button(self, text="参照...", command=self._browse).grid(row=r, column=2, **pad)

        # Clipboard option
        r_cb = len(fields)
        self.clipboard_var = tk.BooleanVar(value=current.get("clipboard_copy") == "1")
        ttk.Checkbutton(self, text="スクショをクリップボードにコピー",
                        variable=self.clipboard_var).grid(
            row=r_cb, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 4))

        # Buttons
        bf = ttk.Frame(self)
        bf.grid(row=r_cb + 1, column=0, columnspan=3, pady=10)
        ttk.Button(bf, text="OK", command=self._ok).pack(side="left", padx=6)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side="left", padx=6)

        self.columnconfigure(1, weight=1)
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window()

    def _browse(self):
        d = filedialog.askdirectory()
        if d:
            self.vars["output_dir"].set(d)

    def _ok(self):
        self.result = {k: v.get() for k, v in self.vars.items()}
        self.result["clipboard_copy"] = "1" if self.clipboard_var.get() else "0"
        self.destroy()


class _StepDialog(tk.Toplevel):
    def __init__(self, parent, title="ステップ", initial=None, selector_choices=None):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self.grab_set()
        self.resizable(False, False)
        pad = dict(padx=8, pady=4)
        init = initial or {}
        self._selector_choices = selector_choices or []
        sel_values = [c[0] for c in self._selector_choices]
        sel_display = [c[1] for c in self._selector_choices]

        # Row 0: Type
        ttk.Label(self, text="種類:").grid(row=0, column=0, sticky="e", **pad)
        self.type_var = tk.StringVar(value=init.get("type", "入力"))
        self.type_combo = ttk.Combobox(self, textvariable=self.type_var, values=STEP_TYPES,
                                       width=12, state="readonly")
        self.type_combo.grid(row=0, column=1, sticky="w", **pad)
        self.type_combo.bind("<<ComboboxSelected>>", self._on_type_change)

        # Row 1: Selector (combobox)
        ttk.Label(self, text="セレクタ:").grid(row=1, column=0, sticky="e", **pad)
        self.sel_var = tk.StringVar(value=init.get("selector", ""))
        self.sel_combo = ttk.Combobox(self, textvariable=self.sel_var, values=sel_values, width=40)
        self.sel_combo.grid(row=1, column=1, **pad)
        # Show display text while browsing but store actual selector
        if sel_display:
            self.sel_combo.bind("<<ComboboxSelected>>", self._on_sel_selected)
            self._sel_display_map = dict(zip(sel_display, sel_values))

        # Row 2: Value
        ttk.Label(self, text="値:").grid(row=2, column=0, sticky="e", **pad)
        self.val_var = tk.StringVar(value=init.get("value", "{パターン}"))
        self.val_entry = ttk.Entry(self, textvariable=self.val_var, width=40)
        self.val_entry.grid(row=2, column=1, **pad)

        # Row 3: Seconds
        ttk.Label(self, text="秒数:").grid(row=3, column=0, sticky="e", **pad)
        self.sec_var = tk.StringVar(value=init.get("seconds", "1.0"))
        self.sec_entry = ttk.Entry(self, textvariable=self.sec_var, width=10)
        self.sec_entry.grid(row=3, column=1, sticky="w", **pad)

        # Row 4: Screenshot mode
        ttk.Label(self, text="スクショ範囲:").grid(row=4, column=0, sticky="e", **pad)
        self.mode_var = tk.StringVar(value=init.get("mode", "fullpage"))
        self.mode_combo = ttk.Combobox(self, textvariable=self.mode_var,
                                       values=["fullpage", "element", "margin", "rect"],
                                       width=12, state="readonly")
        self.mode_combo.grid(row=4, column=1, sticky="w", **pad)
        self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_change)

        # Row 5: Margin
        ttk.Label(self, text="マージン(px):").grid(row=5, column=0, sticky="e", **pad)
        self.margin_var = tk.StringVar(value=init.get("margin_px", "200"))
        self.margin_entry = ttk.Entry(self, textvariable=self.margin_var, width=10)
        self.margin_entry.grid(row=5, column=1, sticky="w", **pad)

        # Row 6: Rect fields
        rect_frame = ttk.LabelFrame(self, text="座標指定 (px)")
        rect_frame.grid(row=6, column=0, columnspan=2, sticky="ew", **pad)
        self.rect_frame = rect_frame

        rf_pad = dict(padx=4, pady=2)
        ttk.Label(rect_frame, text="scroll Y:").grid(row=0, column=0, sticky="e", **rf_pad)
        self.scroll_y_var = tk.StringVar(value=init.get("scroll_y", "0"))
        self.scroll_y_entry = ttk.Entry(rect_frame, textvariable=self.scroll_y_var, width=8)
        self.scroll_y_entry.grid(row=0, column=1, sticky="w", **rf_pad)

        ttk.Label(rect_frame, text="X:").grid(row=0, column=2, sticky="e", **rf_pad)
        self.rect_x_var = tk.StringVar(value=init.get("rect_x", "0"))
        self.rect_x_entry = ttk.Entry(rect_frame, textvariable=self.rect_x_var, width=6)
        self.rect_x_entry.grid(row=0, column=3, sticky="w", **rf_pad)

        ttk.Label(rect_frame, text="Y:").grid(row=0, column=4, sticky="e", **rf_pad)
        self.rect_y_var = tk.StringVar(value=init.get("rect_y", "0"))
        self.rect_y_entry = ttk.Entry(rect_frame, textvariable=self.rect_y_var, width=6)
        self.rect_y_entry.grid(row=0, column=5, sticky="w", **rf_pad)

        ttk.Label(rect_frame, text="幅:").grid(row=1, column=0, sticky="e", **rf_pad)
        self.rect_w_var = tk.StringVar(value=init.get("rect_w", "800"))
        self.rect_w_entry = ttk.Entry(rect_frame, textvariable=self.rect_w_var, width=6)
        self.rect_w_entry.grid(row=1, column=1, sticky="w", **rf_pad)

        ttk.Label(rect_frame, text="高さ:").grid(row=1, column=2, sticky="e", **rf_pad)
        self.rect_h_var = tk.StringVar(value=init.get("rect_h", "600"))
        self.rect_h_entry = ttk.Entry(rect_frame, textvariable=self.rect_h_var, width=6)
        self.rect_h_entry.grid(row=1, column=3, sticky="w", **rf_pad)

        # Row 7: Hint
        self.hint_var = tk.StringVar()
        ttk.Label(self, textvariable=self.hint_var, foreground="gray").grid(
            row=7, column=0, columnspan=2, sticky="w", padx=8)

        # Row 8: Buttons
        bf = ttk.Frame(self)
        bf.grid(row=8, column=0, columnspan=2, pady=8)
        ttk.Button(bf, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side="left", padx=4)

        self.bind("<Escape>", lambda e: self.destroy())
        self._on_type_change()
        self.wait_window()

    def _on_sel_selected(self, event=None):
        """If user picks from display list, resolve to actual selector."""
        cur = self.sel_combo.get()
        if hasattr(self, '_sel_display_map') and cur in self._sel_display_map:
            self.sel_var.set(self._sel_display_map[cur])

    def _on_type_change(self, event=None):
        t = self.type_var.get()
        self.sel_combo.configure(state="normal" if t in ("入力", "クリック", "スクショ") else "disabled")
        self.val_entry.configure(state="normal" if t == "入力" else "disabled")
        self.sec_entry.configure(state="normal" if t == "待機" else "disabled")
        self.mode_combo.configure(state="readonly" if t == "スクショ" else "disabled")
        self._update_ss_fields()
        hints = {"入力": "値に {パターン} でパターン値が入ります",
                 "スクショ": "fullpage=全体 / element=要素 / margin=要素+余白 / rect=座標指定"}
        self.hint_var.set(hints.get(t, ""))

    def _on_mode_change(self, event=None):
        self._update_ss_fields()

    def _update_ss_fields(self):
        t = self.type_var.get()
        mode = self.mode_var.get()
        is_ss = (t == "スクショ")
        is_margin = is_ss and mode == "margin"
        is_rect = is_ss and mode == "rect"
        self.margin_entry.configure(state="normal" if is_margin else "disabled")
        for w in [self.scroll_y_entry, self.rect_x_entry, self.rect_y_entry,
                  self.rect_w_entry, self.rect_h_entry]:
            w.configure(state="normal" if is_rect else "disabled")
        if is_rect:
            self.hint_var.set("scroll Y: ページ内スクロール位置、X/Y/幅/高さ: ビューポート内の矩形")
        elif is_margin:
            self.hint_var.set("セレクタで対象要素を指定してください")

    def _ok(self):
        t = self.type_var.get()
        step = {"type": t}
        if t in ("入力", "クリック"):
            sel = self.sel_var.get().strip()
            if not sel:
                messagebox.showwarning(APP_NAME, "セレクタを入力してください。")
                return
            step["selector"] = sel
            if t == "入力":
                step["value"] = self.val_var.get()
        elif t == "待機":
            try:
                step["seconds"] = str(float(self.sec_var.get()))
            except ValueError:
                messagebox.showwarning(APP_NAME, "秒数を正しく入力してください。")
                return
        elif t == "スクショ":
            mode = self.mode_var.get()
            step["mode"] = mode
            sel = self.sel_var.get().strip()
            if mode in ("element", "margin") and not sel:
                messagebox.showwarning(APP_NAME, "element/marginモードではセレクタが必要です。")
                return
            if sel:
                step["selector"] = sel
            if mode == "margin":
                try:
                    step["margin_px"] = str(int(self.margin_var.get()))
                except ValueError:
                    messagebox.showwarning(APP_NAME, "マージンを整数で入力してください。")
                    return
            elif mode == "rect":
                try:
                    step["scroll_y"] = str(int(self.scroll_y_var.get()))
                    step["rect_x"] = str(int(self.rect_x_var.get()))
                    step["rect_y"] = str(int(self.rect_y_var.get()))
                    step["rect_w"] = str(int(self.rect_w_var.get()))
                    step["rect_h"] = str(int(self.rect_h_var.get()))
                except ValueError:
                    messagebox.showwarning(APP_NAME, "座標は整数で入力してください。")
                    return
        self.result = step
        self.destroy()


class _PresetInputCheckDialog(tk.Toplevel):
    """Preset dialog for input validation testing."""
    def __init__(self, parent, selector_choices):
        super().__init__(parent)
        self.title("プリセット: 入力チェック")
        self.result = None
        self.grab_set()
        self.resizable(False, False)
        pad = dict(padx=8, pady=4)
        sel_values = [c[0] for c in selector_choices]

        ttk.Label(self, text="入力対象:").grid(row=0, column=0, sticky="e", **pad)
        self.input_var = tk.StringVar()
        ttk.Combobox(self, textvariable=self.input_var, values=sel_values, width=40).grid(
            row=0, column=1, **pad)

        ttk.Label(self, text="送信ボタン:").grid(row=1, column=0, sticky="e", **pad)
        self.submit_var = tk.StringVar()
        ttk.Combobox(self, textvariable=self.submit_var, values=sel_values, width=40).grid(
            row=1, column=1, **pad)

        ttk.Label(self, text="入力後スクショ\nマージン 左右/上下:").grid(row=2, column=0, sticky="e", **pad)
        mf = ttk.Frame(self)
        mf.grid(row=2, column=1, sticky="w", **pad)
        self.margin_lr_var = tk.StringVar(value="100")
        self.margin_tb_var = tk.StringVar(value="200")
        ttk.Entry(mf, textvariable=self.margin_lr_var, width=6).pack(side="left")
        ttk.Label(mf, text=" / ").pack(side="left")
        ttk.Entry(mf, textvariable=self.margin_tb_var, width=6).pack(side="left")
        ttk.Label(mf, text=" px").pack(side="left")

        ttk.Label(self, text="待機(秒):").grid(row=3, column=0, sticky="e", **pad)
        self.wait_var = tk.StringVar(value="1.0")
        ttk.Entry(self, textvariable=self.wait_var, width=8).grid(
            row=3, column=1, sticky="w", **pad)

        ttk.Label(self, text="").grid(row=4, column=0)  # spacer
        ttk.Label(self, text="生成されるステップ:", foreground="gray").grid(
            row=5, column=0, columnspan=2, sticky="w", padx=8)
        ttk.Label(self, text="1. 入力 {パターン}\n2. 待機\n3. スクショ(margin) 入力周辺\n"
                             "4. クリック 送信ボタン\n5. 待機\n6. スクショ(fullpage) 結果画面",
                  foreground="gray", justify="left").grid(
            row=6, column=0, columnspan=2, sticky="w", padx=16)

        bf = ttk.Frame(self)
        bf.grid(row=7, column=0, columnspan=2, pady=10)
        ttk.Button(bf, text="追加", command=self._ok).pack(side="left", padx=4)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side="left", padx=4)

        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window()

    def _ok(self):
        input_sel = self.input_var.get().strip()
        submit_sel = self.submit_var.get().strip()
        if not input_sel:
            messagebox.showwarning(APP_NAME, "入力対象を選択してください。")
            return
        if not submit_sel:
            messagebox.showwarning(APP_NAME, "送信ボタンを選択してください。")
            return
        try:
            wait = str(float(self.wait_var.get()))
            margin_lr = int(self.margin_lr_var.get())
            margin_tb = int(self.margin_tb_var.get())
        except ValueError:
            messagebox.showwarning(APP_NAME, "数値を正しく入力してください。")
            return
        # Use average of lr and tb as margin (margin mode is uniform)
        avg_margin = str(max(margin_lr, margin_tb))
        self.result = [
            {"type": "入力", "selector": input_sel, "value": "{パターン}"},
            {"type": "待機", "seconds": wait},
            {"type": "スクショ", "mode": "margin", "selector": input_sel, "margin_px": avg_margin},
            {"type": "クリック", "selector": submit_sel},
            {"type": "待機", "seconds": wait},
            {"type": "スクショ", "mode": "fullpage"},
        ]
        self.destroy()


class _PatternDialog(tk.Toplevel):
    def __init__(self, parent, title="パターン", initial=None):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self.grab_set()
        self.resizable(False, False)
        pad = dict(padx=8, pady=4)

        ttk.Label(self, text="ラベル:").grid(row=0, column=0, sticky="e", **pad)
        self.label_var = tk.StringVar(value=(initial or {}).get("label", ""))
        ttk.Entry(self, textvariable=self.label_var, width=30).grid(row=0, column=1, **pad)

        ttk.Label(self, text="入力値:").grid(row=1, column=0, sticky="ne", **pad)
        self.value_text = tk.Text(self, width=40, height=4, wrap="word")
        self.value_text.grid(row=1, column=1, **pad)
        if initial:
            self.value_text.insert("1.0", initial.get("value", ""))

        self.count_label = ttk.Label(self, text="0 文字")
        self.count_label.grid(row=2, column=1, sticky="e", padx=8)
        self.value_text.bind("<KeyRelease>", self._update_count)
        self._update_count()

        bf = ttk.Frame(self)
        bf.grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(bf, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side="left", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window()

    def _update_count(self, event=None):
        self.count_label.configure(text=f"{len(self.value_text.get('1.0', 'end-1c'))} 文字")

    def _ok(self):
        label = self.label_var.get().strip()
        if not label:
            messagebox.showwarning(APP_NAME, "ラベルを入力してください。")
            return
        self.result = {"label": label, "value": self.value_text.get("1.0", "end-1c")}
        self.destroy()


class _NCharDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("N文字パターン生成")
        self.result = None
        self.grab_set()
        self.resizable(False, False)
        pad = dict(padx=8, pady=4)

        ttk.Label(self, text="繰り返す文字:").grid(row=0, column=0, sticky="e", **pad)
        self.char_var = tk.StringVar(value="あ")
        ttk.Entry(self, textvariable=self.char_var, width=8).grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(self, text="ラベル接頭辞:").grid(row=1, column=0, sticky="e", **pad)
        self.prefix_var = tk.StringVar(value="nchar")
        ttk.Entry(self, textvariable=self.prefix_var, width=16).grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(self, text="文字数リスト:").grid(row=2, column=0, sticky="ne", **pad)
        df = ttk.Frame(self)
        df.grid(row=2, column=1, sticky="w", **pad)
        self.counts_text = tk.Text(df, width=30, height=6, wrap="word")
        self.counts_text.pack()
        self.counts_text.insert("1.0", "1\n10\n50\n100\n255\n256\n1000")
        ttk.Label(df, text="(1行に1つの数字)", foreground="gray").pack(anchor="w")

        pf = ttk.LabelFrame(self, text="プリセット")
        pf.grid(row=3, column=0, columnspan=2, **pad, sticky="ew")
        for txt, vals in [("VARCHAR境界値", "1\n50\n100\n254\n255\n256\n500"),
                          ("TEXT系", "1\n100\n1000\n2000\n4000\n5000\n10000"),
                          ("名前欄など", "0\n1\n5\n10\n20\n30\n50")]:
            ttk.Button(pf, text=txt, command=lambda v=vals: self._set_preset(v)).pack(
                side="left", padx=4, pady=2)

        bf = ttk.Frame(self)
        bf.grid(row=4, column=0, columnspan=2, pady=8)
        ttk.Button(bf, text="生成", command=self._ok).pack(side="left", padx=4)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side="left", padx=4)
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window()

    def _set_preset(self, text):
        self.counts_text.delete("1.0", "end")
        self.counts_text.insert("1.0", text)

    def _ok(self):
        char = self.char_var.get()
        if not char:
            messagebox.showwarning(APP_NAME, "繰り返す文字を入力してください。")
            return
        prefix = self.prefix_var.get().strip() or "nchar"
        counts = [int(l.strip()) for l in self.counts_text.get("1.0", "end-1c").strip().splitlines()
                  if l.strip().isdigit()]
        if not counts:
            messagebox.showwarning(APP_NAME, "文字数を1つ以上入力してください。")
            return
        self.result = [{"label": f"{prefix}_{n}", "value": char * n} for n in counts]
        self.destroy()


class _TemplateDialog(tk.Toplevel):
    """テンプレートCSV選択ダイアログ。"""
    def __init__(self, parent, csv_files):
        super().__init__(parent)
        self.title(f"{APP_NAME} - テンプレート読込")
        self.result = None
        self.mode = "append"  # "append" or "replace"
        self.grab_set()
        self.resizable(False, False)
        pad = dict(padx=8, pady=4)

        ttk.Label(self, text="テンプレートを選択:", font=("", 10)).pack(**pad)

        # Listbox
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, **pad)
        self.listbox = tk.Listbox(frame, height=min(len(csv_files), 12), width=40,
                                  font=("", 10))
        for f in csv_files:
            name = os.path.splitext(f)[0]
            self.listbox.insert(tk.END, f"  {name}")
        self.listbox.pack(side="left", fill="both", expand=True)
        self._csv_files = csv_files

        if len(csv_files) > 0:
            self.listbox.selection_set(0)

        self.listbox.bind("<Double-Button-1>", lambda e: self._ok("append"))

        # Mode
        self.mode_var = tk.StringVar(value="append")
        mf = ttk.Frame(self)
        mf.pack(**pad)
        ttk.Radiobutton(mf, text="既存パターンに追加", variable=self.mode_var,
                        value="append").pack(side="left", padx=8)
        ttk.Radiobutton(mf, text="既存パターンを置換", variable=self.mode_var,
                        value="replace").pack(side="left", padx=8)

        # Buttons
        bf = ttk.Frame(self)
        bf.pack(pady=8)
        ttk.Button(bf, text="読込", command=lambda: self._ok(None)).pack(side="left", padx=4)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side="left", padx=4)

        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window()

    def _ok(self, force_mode):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo(APP_NAME, "テンプレートを選択してください。")
            return
        self.result = self._csv_files[sel[0]]
        self.mode = force_mode or self.mode_var.get()
        self.destroy()


class _InputCheckPatternDialog(tk.Toplevel):
    """入力チェック用パターンセット生成ダイアログ。"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("入力チェック用パターン生成")
        self.result = None
        self.grab_set()
        self.resizable(False, False)
        pad = dict(padx=8, pady=4)

        ttk.Label(self, text="最大文字数:").grid(row=0, column=0, sticky="e", **pad)
        self.maxlen_var = tk.StringVar(value="")
        ttk.Entry(self, textvariable=self.maxlen_var, width=10).grid(
            row=0, column=1, sticky="w", **pad)
        ttk.Label(self, text="(空欄なら境界値テストなし)", foreground="gray").grid(
            row=0, column=2, sticky="w", **pad)

        ttk.Label(self, text="境界値の文字:").grid(row=1, column=0, sticky="e", **pad)
        self.fill_char_var = tk.StringVar(value="あ")
        ttk.Entry(self, textvariable=self.fill_char_var, width=6).grid(
            row=1, column=1, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=6)

        # Preview
        ttk.Label(self, text="生成されるパターン:", font=("", 9, "bold")).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=8)

        preview = (
            "  - 未入力 (0文字)\n"
            "  - 全角スペースのみ\n"
            "  - 半角スペースのみ\n"
            "  - 全角スペース含む\n"
            "  - 半角スペース含む\n"
            "  - 全角英字 (ＡＢＣＤＥ)\n"
            "  - 半角英字 (ABCDE)\n"
            "  - 全角記号 (©)\n"
            "  - 半角記号 (!@#$%)\n"
            "  - 絵文字含む (\U0001f990)\n"
            "  - 4バイト文字 (\U00020BB7)\n"
            "  - 全角数値 (１２３４５)\n"
            "  - 半角数値 (12345)\n"
            "  + 最大文字数を指定すると:\n"
            "    最大-1文字 / 最大文字 / 最大+1文字"
        )
        ttk.Label(self, text=preview, justify="left", foreground="gray").grid(
            row=4, column=0, columnspan=3, sticky="w", padx=16, pady=(0, 4))

        bf = ttk.Frame(self)
        bf.grid(row=5, column=0, columnspan=3, pady=10)
        ttk.Button(bf, text="追加", command=self._ok).pack(side="left", padx=4)
        ttk.Button(bf, text="キャンセル", command=self.destroy).pack(side="left", padx=4)

        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_window()

    def _ok(self):
        fill = self.fill_char_var.get() or "あ"

        patterns = [
            {"label": "未入力",             "value": ""},
            {"label": "全角スペースのみ",   "value": "\u3000"},
            {"label": "半角スペースのみ",   "value": " "},
            {"label": "全角スペース含む",   "value": "テスト\u3000入力"},
            {"label": "半角スペース含む",   "value": "テスト 入力"},
            {"label": "全角英字",           "value": "ＡＢＣＤＥ"},
            {"label": "半角英字",           "value": "ABCDE"},
            {"label": "全角記号",           "value": "\u00A9"},
            {"label": "半角記号",           "value": "!@#$%"},
            {"label": "絵文字含む",         "value": "テスト\U0001f990入力"},
            {"label": "4バイト文字",        "value": "\U00020BB7野屋"},
            {"label": "全角数値",           "value": "１２３４５"},
            {"label": "半角数値",           "value": "12345"},
        ]

        # 境界値テスト（最大文字数が指定された場合）
        maxlen_str = self.maxlen_var.get().strip()
        if maxlen_str:
            try:
                maxlen = int(maxlen_str)
                if maxlen > 0:
                    if maxlen - 1 > 0:
                        patterns.append({
                            "label": f"最大-1({maxlen - 1}文字)",
                            "value": fill * (maxlen - 1)
                        })
                    patterns.append({
                        "label": f"最大({maxlen}文字)",
                        "value": fill * maxlen
                    })
                    patterns.append({
                        "label": f"最大+1({maxlen + 1}文字)",
                        "value": fill * (maxlen + 1)
                    })
            except ValueError:
                messagebox.showwarning(APP_NAME, "最大文字数を整数で入力してください。")
                return

        self.result = patterns
        self.destroy()


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = YShotApp()
    app.mainloop()
