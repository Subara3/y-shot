"""
y-shot: Web Screenshot Automation Tool  v1.7 (Flet)
  - Multiple test cases, each with own steps + pattern set reference
  - v1.5: highlight fix, abort, tel capture, input check fix
  - v1.6: popup menu, reorder fix, pattern count sync, modal dialogs
  - v1.7: dropdown page selector, 1-column test list, start_number per page,
           pattern numbering in filenames/UI/Excel, manual number override,
           fullshot (CDP full-page capture)
"""

import csv, os, sys, json, threading, time, logging, traceback, copy
from datetime import datetime
from urllib.parse import urlparse, urlunparse
import flet as ft

APP_NAME = "y-shot"
APP_VERSION = "1.8"
APP_AUTHOR = "Yuri Norimatsu"

# ── File logger (log/YYYYMMDD.log, append) ──
def _setup_file_logger():
    _log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, 'frozen', False)
                            else os.path.dirname(sys.executable), "log")
    os.makedirs(_log_dir, exist_ok=True)
    _log_file = os.path.join(_log_dir, datetime.now().strftime("%Y%m%d") + ".log")
    logger = logging.getLogger("y-shot")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(_log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(fh)
    return logger
_flog = _setup_file_logger()

import re
def _safe_filename(s, max_len=30):
    """Remove characters unsafe for filenames and truncate."""
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', s).strip().strip('.')
    return s[:max_len] if s else '_'

def _has_non_bmp(s):
    """Check if string contains characters outside the Basic Multilingual Plane (e.g. emoji, 𠮷)."""
    return any(ord(c) > 0xFFFF for c in s)

# ===================================================================
# Backend
# ===================================================================

def collect_elements_python(driver, include_hidden=False):
    from selenium.webdriver.common.by import By
    results, seen = [], set()
    css = ("input, textarea, select, button, a, [role='button'], [type='submit'], "
           "[type='image'], img[onclick], [onclick], li[id], span[id], div[onclick]")
    try: elements = driver.find_elements(By.CSS_SELECTOR, css)
    except Exception: return results
    for el in elements:
        try:
            visible = el.is_displayed()
            if not visible:
                if (el.get_attribute("type") or "") not in ("radio","checkbox"):
                    if not include_hidden:
                        continue
            tag = el.tag_name.lower(); etype = el.get_attribute("type") or ""
            if etype == "hidden": continue
            eid = el.get_attribute("id") or ""; ename = el.get_attribute("name") or ""
            sel = _build_selector(driver, el, tag, eid, ename)
            if sel in seen: continue; seen.add(sel)
            hint = (el.get_attribute("placeholder") or el.get_attribute("alt") or
                    (el.text or "").strip()[:50] or (el.get_attribute("value") or "")[:30])
            results.append({"selector": sel, "tag": tag, "type": etype, "name": ename, "id": eid, "hint": hint, "visible": visible})
        except Exception: continue
    return results

def _css_escape_attr(val):
    return val.replace('\\', '\\\\').replace('"', '\\"')

def _is_safe_class(cls):
    if not cls: return False
    if cls[0].isdigit(): return False
    return all(c.isalnum() or c in '-_' for c in cls)

def _build_selector(driver, el, tag, eid, ename):
    from selenium.webdriver.common.by import By
    if eid:
        if eid[0].isdigit() or not all(c.isalnum() or c in '-_' for c in eid):
            return f'[id="{_css_escape_attr(eid)}"]'
        return f"#{eid}"
    if ename:
        safe_name = _css_escape_attr(ename)
        s = f'{tag}[name="{safe_name}"]'
        try:
            if len(driver.find_elements(By.CSS_SELECTOR, s)) == 1: return s
        except Exception: pass
    etype = el.get_attribute("type") or ""
    if etype and ename:
        safe_name = _css_escape_attr(ename)
        s = f'{tag}[type="{etype}"][name="{safe_name}"]'
        try:
            if len(driver.find_elements(By.CSS_SELECTOR, s)) == 1: return s
        except Exception: pass
    classes = (el.get_attribute("class") or "").strip()
    if classes:
        safe_classes = [c for c in classes.split()[:3] if _is_safe_class(c)]
        if safe_classes:
            cs = tag + "".join(f".{c}" for c in safe_classes[:2])
            try:
                if len(driver.find_elements(By.CSS_SELECTOR, cs)) == 1: return cs
            except Exception: pass
    try:
        idx = driver.execute_script(
            "var e=arguments[0],p=e.parentElement;if(!p)return 0;"
            "var s=[];for(var i=0;i<p.children.length;i++)if(p.children[i].tagName===e.tagName)s.push(p.children[i]);"
            "for(var j=0;j<s.length;j++)if(s[j]===e)return j+1;return 0;", el)
        if idx and idx > 0:
            pid = driver.execute_script("var p=arguments[0].parentElement;return p?(p.id||''):'';", el)
            if pid:
                if pid[0].isdigit() or not all(c.isalnum() or c in '-_' for c in pid):
                    return f'[id="{_css_escape_attr(pid)}"] > {tag}:nth-of-type({idx})'
                return f"#{pid} > {tag}:nth-of-type({idx})"
    except Exception: pass
    return tag

def capture_form_values(driver):
    from selenium.webdriver.common.by import By
    steps, seen = [], set()
    text_css = ("input[type='text'],input[type='tel'],input[type='email'],"
                "input[type='number'],input[type='url'],input[type='search'],"
                "input[type='password'],input[type='date'],input[type='time'],"
                "input[type='datetime-local'],input[type='month'],input[type='week'],"
                "input[type='color'],input[type='range'],"
                "input:not([type]),textarea")
    for el in driver.find_elements(By.CSS_SELECTOR, text_css):
        try:
            if not el.is_displayed(): continue
            if (el.get_attribute("type") or "text") == "hidden": continue
            val = el.get_attribute("value") or ""
            if not val.strip(): continue
            tag = el.tag_name.lower()
            sel = _build_selector(driver, el, tag, el.get_attribute("id") or "", el.get_attribute("name") or "")
            if sel in seen: continue; seen.add(sel)
            steps.append({"type": "入力", "selector": sel, "value": val})
        except Exception: continue
    for el in driver.find_elements(By.CSS_SELECTOR, "select"):
        try:
            if not el.is_displayed(): continue
            sel = _build_selector(driver, el, "select", el.get_attribute("id") or "", el.get_attribute("name") or "")
            if sel in seen: continue; seen.add(sel)
            val = el.get_attribute("value") or ""
            if val: steps.append({"type": "選択", "selector": sel, "value": val})
        except Exception: continue
    for css_q in ["input[type='radio']:checked", "input[type='checkbox']:checked"]:
        for el in driver.find_elements(By.CSS_SELECTOR, css_q):
            try:
                eid = el.get_attribute("id") or ""
                ename = el.get_attribute("name") or ""
                sel = _build_selector(driver, el, "input", eid, ename)
                if sel in ("input",) or sel in seen: continue
                seen.add(sel)
                steps.append({"type": "クリック", "selector": sel})
            except Exception: continue
    return steps

def collect_element_options(driver, el_info):
    from selenium.webdriver.common.by import By
    tag = el_info.get("tag", "")
    etype = el_info.get("type", "").lower()
    sel = el_info.get("selector", "")
    if tag == "select":
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            options = el.find_elements(By.TAG_NAME, "option")
            result = []
            for opt in options:
                val = opt.get_attribute("value") or ""
                text = opt.text.strip() or val
                if val or text:
                    result.append({"label": text, "value": val})
            return "選択", result
        except Exception:
            return None, []
    elif etype == "radio":
        try:
            name = el_info.get("name", "") or driver.find_element(By.CSS_SELECTOR, sel).get_attribute("name") or ""
            if not name: return None, []
            safe_name = _css_escape_attr(name)
            radios = driver.find_elements(By.CSS_SELECTOR, f'input[type="radio"][name="{safe_name}"]')
            result = []
            for r in radios:
                val = r.get_attribute("value") or ""
                rid = r.get_attribute("id") or ""
                label_text = ""
                if rid:
                    try:
                        lbl = driver.find_element(By.CSS_SELECTOR, f'label[for="{_css_escape_attr(rid)}"]')
                        label_text = lbl.text.strip()
                    except Exception: pass
                if not label_text:
                    label_text = val or f"radio_{len(result)+1}"
                radio_sel = f'input[type="radio"][name="{safe_name}"][value="{_css_escape_attr(val)}"]'
                result.append({"label": label_text, "value": radio_sel})
            return "クリック", result
        except Exception:
            return None, []
    return None, []

HIGHLIGHT_JS = ("(function(s){try{"
    "var p=document.getElementById('__yshot_hl');if(p)p.remove();"
    "if(window.__yshot_scroll_rm){window.removeEventListener('scroll',window.__yshot_scroll_rm,true);}"
    "var e=document.querySelector(s);if(!e)return;"
    "e.scrollIntoView({block:'center',behavior:'instant'});"
    "var r=e.getBoundingClientRect(),h=document.createElement('div');h.id='__yshot_hl';"
    "h.style.cssText='position:fixed;border:3px solid #FF4444;background:rgba(255,68,68,0.15);"
    "z-index:2147483647;pointer-events:none;border-radius:3px;';"
    "h.style.top=r.top-3+'px';h.style.left=r.left-3+'px';"
    "h.style.width=r.width+6+'px';h.style.height=r.height+6+'px';"
    "document.body.appendChild(h);"
    "setTimeout(function(){"
    "window.__yshot_scroll_rm=function(){"
    "var x=document.getElementById('__yshot_hl');if(x)x.remove();"
    "window.removeEventListener('scroll',window.__yshot_scroll_rm,true);};"
    "window.addEventListener('scroll',window.__yshot_scroll_rm,true);"
    "},600);"
    "}catch(x){}})(arguments[0]);")

JS_SET_VALUE = (
    "(function(el,val){"
    "var proto=el.tagName==='TEXTAREA'"
    "?window.HTMLTextAreaElement.prototype"
    ":window.HTMLInputElement.prototype;"
    "var setter=Object.getOwnPropertyDescriptor(proto,'value');"
    "if(setter&&setter.set){setter.set.call(el,val);}else{el.value=val;}"
    "el.dispatchEvent(new Event('input',{bubbles:true}));"
    "el.dispatchEvent(new Event('change',{bubbles:true}));"
    "})(arguments[0],arguments[1]);"
)

def kill_driver(drv, timeout=5):
    if drv is None:
        return
    pid = None
    try:
        svc = getattr(drv, 'service', None)
        proc = getattr(svc, 'process', None) if svc else None
        if proc: pid = proc.pid
    except Exception: pass
    try: drv.quit()
    except Exception: pass
    if pid:
        import subprocess as _sp
        try:
            if proc:
                proc.wait(timeout=2)
                return
        except Exception: pass
        try:
            if sys.platform == 'win32':
                _sp.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True, timeout=5)
            else:
                import signal as _sig
                os.killpg(os.getpgid(pid), _sig.SIGKILL)
        except Exception:
            try:
                if proc: proc.kill()
            except Exception: pass

def build_auth_url(url, user, password):
    if not user: return url
    p = urlparse(url); nl = f"{user}:{password}@{p.hostname}"
    if p.port: nl += f":{p.port}"
    return urlunparse(p._replace(netloc=nl))

STEP_TYPES = ["入力", "クリック", "選択", "待機", "スクショ", "戻る", "ナビゲーション", "見出し", "コメント"]
STEP_ICONS = {"入力": ft.Icons.EDIT, "クリック": ft.Icons.MOUSE,
              "選択": ft.Icons.ARROW_DROP_DOWN_CIRCLE,
              "待機": ft.Icons.HOURGLASS_BOTTOM, "スクショ": ft.Icons.CAMERA_ALT,
              "戻る": ft.Icons.ARROW_BACK, "ナビゲーション": ft.Icons.OPEN_IN_BROWSER,
              "見出し": ft.Icons.TITLE, "コメント": ft.Icons.COMMENT}
INPUT_MODES = [("overwrite", "上書き"), ("append", "追記"), ("clear", "クリアのみ")]

def step_short(step):
    t = step["type"]
    if t == "見出し": return step.get("text","")
    if t == "コメント": return step.get("text","")
    if t == "入力":
        v = step.get("value","{パターン}")
        if len(v) > 20: v = v[:17]+"..."
        sel = step.get("selector","")
        if len(sel) > 20: sel = sel[:17]+"..."
        mode_label = {"append": "[追記]", "clear": "[クリア]"}.get(step.get("input_mode",""), "")
        return f"{sel} \u2190 {v} {mode_label}".strip()
    if t == "クリック":
        sel = step.get("selector","")
        if sel == "{パターン}": return "{パターン} (全パターン)"
        return sel[:30]+"..." if len(sel) > 30 else sel
    if t == "選択":
        sel = step.get("selector","")
        if len(sel) > 20: sel = sel[:17]+"..."
        v = step.get("value","")
        if len(v) > 15: v = v[:12]+"..."
        return f"{sel} \u2190 [{v}]"
    if t == "戻る": return f"ブラウザバック +{step.get('seconds','1.0')}秒"
    if t == "ナビゲーション":
        url = step.get("url","")
        return url[:40]+"..." if len(url) > 40 else url
    if t == "待機": return f"{step.get('seconds','1.0')}秒"
    if t == "スクショ":
        m = step.get("mode","fullpage")
        if m == "fullpage": return "表示範囲"
        if m == "fullshot": return "ページ全体(縦長)"
        if m == "margin": return f"要素+{step.get('margin_px','200')}px"
        return "要素のみ"
    return str(step)

step_display = step_short

# Pre-compiled regexes for _normalize_source (avoid re-compiling on every screenshot)
_NS_PATTERNS = None
def _get_ns_patterns():
    global _NS_PATTERNS
    if _NS_PATTERNS is None:
        _NS_PATTERNS = [
            (re.compile(r'(<input[^>]*name=["\'](?:_token|csrf_token|csrfmiddlewaretoken|__RequestVerificationToken|authenticity_token|nonce)["\'][^>]*value=["\'])[^"\']*(["\'])', re.IGNORECASE), r'\1__NORMALIZED__\2'),
            (re.compile(r'(<meta[^>]*name=["\'](?:csrf-token|_token)["\'][^>]*content=["\'])[^"\']*(["\'])', re.IGNORECASE), r'\1__NORMALIZED__\2'),
            (re.compile(r'(<input[^>]*name=["\'](?:PHPSESSID|session_id|_session|jsessionid)["\'][^>]*value=["\'])[^"\']*(["\'])', re.IGNORECASE), r'\1__NORMALIZED__\2'),
            (re.compile(r'\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2}'), '__DATETIME__'),
            (re.compile(r'\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}'), '__DATETIME__'),
            (re.compile(r'(?<=["\'\s=])\d{10,13}(?=["\'\s&;])'), '__TIMESTAMP__'),
            (re.compile(r'(nonce=["\'])[A-Za-z0-9+/=]+(["\'])'), r'\1__NONCE__\2'),
            (re.compile(r'(\?(?:v|t|_|ver|version|cache|cb)=)[^"\'&\s]+'), r'\1__CACHE__'),
        ]
    return _NS_PATTERNS

def _normalize_source(html):
    """Normalize HTML source for diff comparison.
    Removes volatile values that change between runs (timestamps, CSRF tokens, etc.)."""
    for pattern, repl in _get_ns_patterns():
        html = pattern.sub(repl, html)
    return html

def _generate_report(outdir, log_cb):
    """Generate an HTML report. Walks subdirectories for PNGs."""
    try:
        all_pngs = []  # (relative_path, display_name)
        for root, dirs, files in os.walk(outdir):
            dirs[:] = [d for d in sorted(dirs) if not d.startswith("_")]
            for fn in sorted(files):
                if fn.lower().endswith(".png"):
                    rel = os.path.relpath(os.path.join(root, fn), outdir).replace("\\", "/")
                    all_pngs.append(rel)
        if not all_pngs: return
        html = ['<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">',
                '<title>y-shot レポート</title>',
                '<style>body{font-family:sans-serif;max-width:1200px;margin:0 auto;padding:20px;background:#f8f9fa}',
                'h1{color:#333}h2{color:#555;margin-top:32px;border-bottom:2px solid #ddd;padding-bottom:4px}',
                '.card{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.1);margin:16px 0;padding:16px}',
                '.card img{max-width:100%;border:1px solid #ddd;border-radius:4px}',
                '.card .name{font-weight:bold;color:#555;margin-bottom:8px;font-size:14px}</style></head><body>',
                f'<h1>y-shot レポート</h1><p>{os.path.basename(outdir)} — {len(all_pngs)} 枚</p>']
        cur_dir = None
        for rel in all_pngs:
            d = os.path.dirname(rel)
            if d != cur_dir:
                cur_dir = d
                if d: html.append(f'<h2>{d}</h2>')
            html.append(f'<div class="card"><div class="name">{rel}</div><img src="{rel}" loading="lazy"></div>')
        html.append('</body></html>')
        rp = os.path.join(outdir, "report.html")
        with open(rp, "w", encoding="utf-8") as f: f.write("\n".join(html))
        log_cb(f"[レポート] {rp}")
    except Exception as x:
        log_cb(f"[WARN] レポート生成失敗: {x}")

def _generate_excel_report(outdir, log_cb, pages=None, test_cases=None, run_label=""):
    """Generate Excel report. Walks subdirectories; one sheet per subfolder."""
    try:
        from openpyxl import Workbook
        from openpyxl.drawing.image import Image as XlImage
        from PIL import Image as PILImage
    except ImportError:
        log_cb("[WARN] Excel出力には openpyxl と Pillow が必要です"); return
    try:
        # Collect all PNGs with full paths, grouped by subfolder
        all_pngs = []  # (full_path, display_name, subfolder_name)
        for root, dirs, files in os.walk(outdir):
            dirs[:] = [d for d in sorted(dirs) if not d.startswith("_")]
            for fn in sorted(files):
                if fn.lower().endswith(".png"):
                    fp = os.path.join(root, fn)
                    rel = os.path.relpath(fp, outdir).replace("\\", "/")
                    subdir = os.path.basename(root) if root != outdir else ""
                    all_pngs.append((fp, rel, subdir))
        if not all_pngs: return
        wb = Workbook()
        MAX_IMG_WIDTH = 800

        def _write_sheet(ws, png_list):
            ws.column_dimensions["A"].width = 60; ws.column_dimensions["B"].width = 5
            current_row = 1
            for fp, display, _ in png_list:
                cell = ws.cell(row=current_row, column=1, value=display)
                cell.font = cell.font.copy(bold=True, size=11)
                ws.row_dimensions[current_row].height = 20; current_row += 1
                pil_img = PILImage.open(fp)
                orig_w, orig_h = pil_img.size
                scale = min(1.0, MAX_IMG_WIDTH / orig_w) if orig_w > 0 else 1.0
                xl_img = XlImage(fp)
                xl_img.width = int(orig_w * scale); xl_img.height = int(orig_h * scale)
                ws.add_image(xl_img, f"A{current_row}")
                current_row += max(1, int(orig_h * scale) // 15 + 2)

        # Group by subfolder
        groups = {}
        for item in all_pngs:
            key = item[2] or "root"
            groups.setdefault(key, []).append(item)

        if len(groups) > 1 or (len(groups) == 1 and "root" not in groups):
            first_sheet = True
            for folder_name, pngs in groups.items():
                sheet_name = folder_name[:31] if folder_name != "root" else "エビデンス"
                # Avoid duplicate sheet names (Excel limitation)
                _base, _n = sheet_name, 2
                while sheet_name in [s.title for s in wb.worksheets]:
                    sheet_name = f"{_base[:28]}({_n})"; _n += 1
                if first_sheet:
                    ws = wb.active; ws.title = sheet_name; first_sheet = False
                else:
                    ws = wb.create_sheet(title=sheet_name)
                _write_sheet(ws, pngs)
        else:
            ws = wb.active; ws.title = "エビデンス"
            _write_sheet(ws, all_pngs)

        xp = os.path.join(outdir, "evidence.xlsx")
        wb.save(xp); log_cb(f"[Excel] {xp}")
    except Exception as x:
        log_cb(f"[WARN] Excel生成失敗: {x}")

def run_all_tests(config, test_cases, pattern_sets, log_cb, done_cb, stop_event=None, progress_cb=None, driver_ref=None, pages=None, run_label=""):
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import Select as SeleniumSelect
        from selenium.webdriver.common.keys import Keys
    except ImportError:
        log_cb("[ERROR] selenium が見つかりません。"); done_cb(); return
    import base64 as _b64
    try:
        from PIL import Image as _PILImage
    except ImportError:
        _PILImage = None
    driver = None
    outdir = None
    try:
        opts = webdriver.ChromeOptions()
        if config.get("headless") == "1":
            opts.add_argument("--headless=new")
            log_cb("[INFO] ヘッドレスモード")
        driver = webdriver.Chrome(options=opts); driver.set_window_size(1280, 900)
        if driver_ref is not None: driver_ref.append(driver)
        ba = config.get("basic_auth_user","").strip()
        if ba: log_cb("[INFO] Basic認証を設定")
        # Build page URL lookup: page_id -> url
        _page_urls = {}
        for pg in (pages or []):
            pu = pg.get("url", "").strip()
            if pu: _page_urls[pg["_id"]] = pu
        def _resolve_url(tc):
            """Resolve start URL: test URL > page URL."""
            tc_url = tc.get("url", "").strip()
            if tc_url: return tc_url
            return _page_urls.get(tc.get("page_id", ""), "")
        outdir_base = config.get("output_dir", os.path.join(get_app_dir(), "screenshots"))
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        outdir = os.path.join(outdir_base, ts)
        os.makedirs(outdir, exist_ok=True)
        gss = 0
        total_pats = 0
        for tc in test_cases:
            pn = tc.get("pattern")
            total_pats += len(pattern_sets.get(pn, [])) if pn else 1
        done_pats = 0

        # Build page lookup and create per-page subfolders
        page_dirs = {}  # page_id -> directory path
        save_source = config.get("save_source") == "1"
        source_dirs = {}  # page_id -> _source subdirectory path
        source_root = os.path.join(outdir, "_source")
        if save_source:
            os.makedirs(source_root, exist_ok=True)
        if pages:
            for pg in pages:
                pg_num = pg.get("number", "0")
                pg_name = _safe_filename(pg.get("name", ""), 30)
                pg_dir = os.path.join(outdir, f"{pg_num}_{pg_name}")
                os.makedirs(pg_dir, exist_ok=True)
                page_dirs[pg["_id"]] = pg_dir
                if save_source:
                    src_dir = os.path.join(source_root, f"{pg_num}_{pg_name}")
                    os.makedirs(src_dir, exist_ok=True)
                    source_dirs[pg["_id"]] = src_dir

        for tc_idx, tc in enumerate(test_cases, 1):
            if stop_event and stop_event.is_set():
                log_cb("[中断] ユーザーにより中断されました"); break
            tc_name = tc.get("name", f"テスト{tc_idx}")
            tc_number = tc.get("number", "")
            steps = tc.get("steps", [])
            pat_name = tc.get("pattern")
            pats = pattern_sets.get(pat_name, []) if pat_name else []
            if not pats:
                pats = [{"label": "single", "value": ""}]
            # Determine output directory: page subfolder or root
            tc_pid = tc.get("page_id")
            tc_outdir = page_dirs.get(tc_pid, outdir)
            log_cb(f"\n{'='*50}")
            log_cb(f"テストケース: {tc_number} {tc_name} ({len(pats)} パターン)")
            log_cb(f"{'='*50}")

            for pi, pat in enumerate(pats, 1):
                if stop_event and stop_event.is_set():
                    log_cb("[中断] ユーザーにより中断されました"); break
                label, value = pat.get("label",f"p{pi:03d}"), pat.get("value","")
                log_cb(f"--- [{pi}/{len(pats)}] {label} ({len(value)}文字) ---")
                tc_start_url = _resolve_url(tc)
                if not tc_start_url:
                    log_cb(f"  [WARN] URL未設定 - スキップ"); continue
                tc_base = build_auth_url(tc_start_url, ba, config.get("basic_auth_pass","")) if ba else tc_start_url
                driver.get(tc_base)
                try: WebDriverWait(driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")
                except Exception: pass
                sc = 0
                for si, step in enumerate(steps, 1):
                    if stop_event and stop_event.is_set(): break
                    st = step["type"]
                    if st in ("見出し","コメント"):
                        if st == "見出し": log_cb(f"  ## {step.get('text','')}")
                        continue
                    if st == "入力":
                        sel = step.get("selector","")
                        iv = step.get("value","{パターン}").replace("{パターン}",value).replace("{pattern}",value)
                        input_mode = step.get("input_mode", "overwrite")
                        try:
                            e = WebDriverWait(driver,10).until(EC.presence_of_element_located((By.CSS_SELECTOR,sel)))
                            etype = (e.get_attribute("type") or "").lower()
                            if input_mode == "clear":
                                # Clear only — no new value
                                if etype in ("date","time","datetime-local","month","week","color"):
                                    driver.execute_script("arguments[0].value='';arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", e)
                                else:
                                    e.clear()
                                log_cb(f"  S{si} クリア: {sel}")
                            elif input_mode == "append":
                                # Append to existing value (click end, then type)
                                e.click()
                                e.send_keys(Keys.END)
                                e.send_keys(iv)
                                log_cb(f"  S{si} 追記: {sel}")
                            else:
                                # Overwrite (default)
                                if etype in ("date","time","datetime-local","month","week","color") or _has_non_bmp(iv):
                                    driver.execute_script("arguments[0].focus();arguments[0].value='';", e)
                                    driver.execute_script(JS_SET_VALUE, e, iv)
                                else:
                                    e.clear(); e.send_keys(iv)
                                log_cb(f"  S{si} 入力: {sel}")
                        except Exception as x: log_cb(f"  S{si} [WARN] 入力失敗: {x}")
                    elif st == "クリック":
                        sel = step.get("selector","").replace("{パターン}",value).replace("{pattern}",value)
                        try:
                            WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.CSS_SELECTOR,sel))).click()
                            log_cb(f"  S{si} クリック: {sel}")
                        except Exception as x: log_cb(f"  S{si} [WARN] クリック失敗: {x}")
                    elif st == "選択":
                        sel = step.get("selector","")
                        sv = step.get("value","").replace("{パターン}",value).replace("{pattern}",value)
                        try:
                            el = WebDriverWait(driver,10).until(EC.presence_of_element_located((By.CSS_SELECTOR,sel)))
                            dd = SeleniumSelect(el)
                            try: dd.select_by_value(sv)
                            except Exception: dd.select_by_visible_text(sv)
                            log_cb(f"  S{si} 選択: {sel} -> {sv}")
                        except Exception as x: log_cb(f"  S{si} [WARN] 選択失敗: {x}")
                    elif st == "戻る":
                        try:
                            driver.back()
                            s = float(step.get("seconds","1.0")); time.sleep(s)
                            log_cb(f"  S{si} 戻る (+{s}秒)")
                        except Exception as x: log_cb(f"  S{si} [WARN] 戻る失敗: {x}")
                    elif st == "ナビゲーション":
                        nav_url = step.get("url","").replace("{パターン}",value).replace("{pattern}",value)
                        try:
                            if ba: nav_url = build_auth_url(nav_url, ba, config.get("basic_auth_pass",""))
                            driver.get(nav_url)
                            try: WebDriverWait(driver, 15).until(lambda d: d.execute_script("return document.readyState") == "complete")
                            except Exception: pass
                            log_cb(f"  S{si} ナビ: {nav_url[:60]}")
                        except Exception as x: log_cb(f"  S{si} [WARN] ナビゲーション失敗: {x}")
                    elif st == "待機":
                        s = float(step.get("seconds","1.0")); time.sleep(s); log_cb(f"  S{si} 待機: {s}秒")
                    elif st == "スクショ":
                        sc += 1; gss += 1; mode = step.get("mode","fullpage"); sel = step.get("selector","")
                        safe_tc = _safe_filename(tc_name, 20)
                        safe_label = _safe_filename(label, 30)
                        safe_number = _safe_filename(tc_number, 10) if tc_number else ""
                        num_prefix = f"{safe_number}_" if safe_number else ""
                        fn = f"{gss:03d}_{num_prefix}{safe_tc}_p{pi:02d}_{safe_label}_ss{sc}.png"
                        fp = os.path.join(tc_outdir, fn)
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
                                img = _PILImage.open(fp)
                                d = driver.execute_script("return window.devicePixelRatio||1;")
                                x1,y1 = max(0,int(r["x"]*d)-mg), max(0,int(r["y"]*d)-mg)
                                x2,y2 = min(img.width,int((r["x"]+r["w"])*d)+mg), min(img.height,int((r["y"]+r["h"])*d)+mg)
                                if x2>x1 and y2>y1: img.crop((x1,y1,x2,y2)).save(fp)
                            elif mode == "fullshot":
                                # CDP full-page screenshot (captures entire scrollable page)
                                try:
                                    metrics = driver.execute_cdp_cmd('Page.getLayoutMetrics', {})
                                    # Chrome 120+: cssContentSize, older: contentSize
                                    cs = metrics.get('cssContentSize') or metrics.get('contentSize', {})
                                    cw = cs.get('width', 1280)
                                    ch = cs.get('height', 900)
                                    _flog.debug(f"fullshot: {cw}x{ch} (keys={list(metrics.keys())})")
                                    result = driver.execute_cdp_cmd('Page.captureScreenshot', {
                                        'format': 'png',
                                        'captureBeyondViewport': True,
                                        'clip': {'x': 0, 'y': 0, 'width': cw, 'height': ch, 'scale': 1}
                                    })
                                    with open(fp, 'wb') as _f:
                                        _f.write(_b64.b64decode(result['data']))
                                except Exception as cdp_err:
                                    _flog.error(f"CDP fullshot failed: {cdp_err}, falling back to resize method")
                                    # Fallback: resize window to full page height
                                    try:
                                        total_h = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);")
                                        total_w = driver.execute_script("return Math.max(document.body.scrollWidth, document.documentElement.scrollWidth);")
                                        driver.set_window_size(max(total_w, 1280), min(total_h, 16384))
                                        time.sleep(0.5)
                                        driver.save_screenshot(fp)
                                    finally:
                                        driver.set_window_size(1280, 900)
                            else: driver.save_screenshot(fp)
                            rel_dir = os.path.basename(tc_outdir) if tc_outdir != outdir else ""
                            log_cb(f"  S{si} スクショ: {rel_dir + '/' if rel_dir else ''}{fn}")
                            if save_source:
                                try:
                                    src_dir = source_dirs.get(tc_pid, source_root)
                                    src_base = fn.replace(".png", "")
                                    raw = driver.page_source or ""
                                    with open(os.path.join(src_dir, f"{src_base}_raw.html"), "w", encoding="utf-8") as sf:
                                        sf.write(_normalize_source(raw))
                                    dom = driver.execute_script("return document.documentElement.outerHTML;") or ""
                                    with open(os.path.join(src_dir, f"{src_base}_dom.html"), "w", encoding="utf-8") as sf:
                                        sf.write(_normalize_source(dom))
                                except Exception as sx:
                                    _flog.debug(f"Source save failed: {sx}")
                        except Exception as x: log_cb(f"  S{si} [WARN] スクショ失敗: {x}")
                done_pats += 1
                if progress_cb and total_pats > 0:
                    progress_cb(done_pats, total_pats)

        if stop_event and stop_event.is_set():
            log_cb(f"\n[中断完了] -> {outdir}")
        else:
            log_cb(f"\n[全完了] {len(test_cases)} テスト -> {outdir}")
        _generate_report(outdir, log_cb)
        _generate_excel_report(outdir, log_cb, pages=pages, test_cases=test_cases, run_label=run_label)
    except Exception as x:
        log_cb(f"[ERROR] {x}"); outdir = None
    finally:
        if driver:
            kill_driver(driver)
            if driver_ref is not None:
                try: driver_ref.remove(driver)
                except ValueError: pass
        done_cb(outdir)

# ===================================================================
# Path helpers
# ===================================================================

def get_app_dir():
    if getattr(sys, 'frozen', False): return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_bundle_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'): return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def _data_path(filename):
    return os.path.join(get_app_dir(), filename)

# ===================================================================
# Persistence
# ===================================================================
CSV_HEADER = ["label", "value"]
CONFIG_FILE = "y_shot_config.ini"
TESTS_FILE = "y_shot_tests.json"
PATTERNS_FILE = "y_shot_patterns.json"
SELECTOR_BANK_FILE = "y_shot_selectors.json"
PAGES_FILE = "y_shot_pages.json"

def load_csv(path):
    if not os.path.isfile(path): return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if "label" in r]
def save_csv(path, patterns):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER); w.writeheader(); w.writerows(patterns)
def load_config():
    import configparser; c = configparser.ConfigParser(); c.read(_data_path(CONFIG_FILE), encoding="utf-8")
    return dict(c["settings"]) if "settings" in c else {}
def save_config(data):
    import configparser; c = configparser.ConfigParser()
    c["settings"] = {k: str(v) for k,v in data.items()}
    with open(_data_path(CONFIG_FILE), "w", encoding="utf-8") as f: c.write(f)
def load_tests():
    p = _data_path(TESTS_FILE)
    if not os.path.isfile(p): return []
    with open(p, "r", encoding="utf-8") as f: return json.load(f)
def save_tests(tests):
    with open(_data_path(TESTS_FILE), "w", encoding="utf-8") as f: json.dump(tests, f, ensure_ascii=False, indent=2)
def load_pattern_sets():
    p = _data_path(PATTERNS_FILE)
    if not os.path.isfile(p): return {}
    with open(p, "r", encoding="utf-8") as f: return json.load(f)
def save_pattern_sets(ps):
    with open(_data_path(PATTERNS_FILE), "w", encoding="utf-8") as f: json.dump(ps, f, ensure_ascii=False, indent=2)
def load_selector_bank():
    p = _data_path(SELECTOR_BANK_FILE)
    if not os.path.isfile(p): return {}
    with open(p, "r", encoding="utf-8") as f: return json.load(f)
def save_selector_bank(bank):
    with open(_data_path(SELECTOR_BANK_FILE), "w", encoding="utf-8") as f: json.dump(bank, f, ensure_ascii=False, indent=2)
def load_pages():
    p = _data_path(PAGES_FILE)
    if not os.path.isfile(p): return []
    with open(p, "r", encoding="utf-8") as f: return json.load(f)
def save_pages(pages):
    with open(_data_path(PAGES_FILE), "w", encoding="utf-8") as f: json.dump(pages, f, ensure_ascii=False, indent=2)
def get_templates_dir():
    user_dir = os.path.join(get_app_dir(), "templates")
    bundle_dir = os.path.join(get_bundle_dir(), "templates")
    if not os.path.isdir(user_dir):
        os.makedirs(user_dir, exist_ok=True)
        if os.path.isdir(bundle_dir) and bundle_dir != user_dir:
            import shutil
            for f in os.listdir(bundle_dir):
                if f.lower().endswith(".csv"):
                    src = os.path.join(bundle_dir, f)
                    dst = os.path.join(user_dir, f)
                    if not os.path.exists(dst): shutil.copy2(src, dst)
    return user_dir if os.path.isdir(user_dir) else None

# ===================================================================
# Flet UI
# ===================================================================

def main(page: ft.Page):
    # Log Flet version for diagnostics
    _flog.info(f"Flet version: {ft.__version__}")
    try:
        _main_inner(page)
    except Exception as _fatal:
        tb = traceback.format_exc()
        _flog.error(f"FATAL in main: {_fatal}\n{tb}")
        # Show error in page if possible
        try:
            page.clean()
            page.add(ft.Column([
                ft.Text(f"{APP_NAME} 起動エラー", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_600),
                ft.Text(str(_fatal), size=14, selectable=True),
                ft.Text("詳細はlog/フォルダを確認してください", size=12, color=ft.Colors.GREY_600),
                ft.Text(tb, size=10, selectable=True, font_family="Consolas"),
            ], scroll=ft.ScrollMode.AUTO, expand=True))
            page.update()
        except Exception:
            pass
        raise

def _main_inner(page: ft.Page):
    page.title = f"{APP_NAME} - Web Screenshot Tool"
    page.window.width = 1500; page.window.height = 900
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)

    def _safe_load(loader, default, name):
        try:
            return loader()
        except Exception as x:
            _flog.error(f"Failed to load {name}: {x}")
            return default

    state = {
        "tests": _safe_load(load_tests, [], "tests"),
        "pattern_sets": _safe_load(load_pattern_sets, {}, "pattern_sets"),
        "config": _safe_load(load_config, {}, "config"),
        "selector_bank": _safe_load(load_selector_bank, {}, "selector_bank"),
        "pages": _safe_load(load_pages, [], "pages"),
        "browser_driver": None, "browser_elements": [],
        "selected_test": -1, "selected_pat_set": None, "selected_el": -1,
        "selected_page": None,
        "collapsed": set(),
        "stop_event": None, "test_drivers": [],
        "_tc_id_counter": 0, "_page_id_counter": 0,
    }
    _max_id = 0
    for tc in state["tests"]:
        if "_id" in tc:
            try: _max_id = max(_max_id, int(tc["_id"].split("_", 1)[1]))
            except (ValueError, IndexError): pass
        else:
            state["_tc_id_counter"] += 1
            tc["_id"] = f"tc_{state['_tc_id_counter']}"
    state["_tc_id_counter"] = max(state["_tc_id_counter"], _max_id)
    def _new_tc_id():
        state["_tc_id_counter"] += 1; return f"tc_{state['_tc_id_counter']}"

    _max_page_id = 0
    for pg in state["pages"]:
        try: _max_page_id = max(_max_page_id, int(pg["_id"].split("_", 1)[1]))
        except (ValueError, IndexError): pass
    state["_page_id_counter"] = _max_page_id
    def _new_page_id():
        state["_page_id_counter"] += 1; return f"p_{state['_page_id_counter']}"

    def cur_page():
        pid = state["selected_page"]
        for p in state["pages"]:
            if p["_id"] == pid: return p
        return None

    # Index cache for O(1) lookups (invalidated on data change)
    _idx_cache = {"valid": False, "by_page": {}, "by_id": {}}
    def _rebuild_idx():
        c = _idx_cache
        c["by_page"] = {}; c["by_id"] = {}
        for i, tc in enumerate(state["tests"]):
            tid = tc.get("_id", "")
            pid = tc.get("page_id", "")
            c["by_id"][tid] = i
            c["by_page"].setdefault(pid, []).append(tc)
        c["valid"] = True
    def _invalidate_idx():
        _idx_cache["valid"] = False
    def tests_for_page(page_id):
        if not _idx_cache["valid"]: _rebuild_idx()
        return list(_idx_cache["by_page"].get(page_id, []))

    def auto_number_tests():
        """Re-number tests: page_number-sub_number.
        If a test has _sub_number set, use it and continue from there."""
        _invalidate_idx()  # data may have changed before this call
        for pg in state["pages"]:
            pnum = pg["number"]
            next_sub = int(pg.get("start_number", 1))
            page_tests = tests_for_page(pg["_id"])
            for tc in page_tests:
                forced = tc.get("_sub_number")
                if forced is not None:
                    next_sub = int(forced)
                tc["number"] = f"{pnum}-{next_sub}"
                next_sub += 1

    # Ensure at least one page exists
    if not state["pages"]:
        dp = {"_id": _new_page_id(), "name": "ページ1", "number": "1", "start_number": 1, "url": ""}
        state["pages"].append(dp)
        for tc in state["tests"]:
            tc.setdefault("page_id", dp["_id"])
    auto_number_tests()
    state["selected_page"] = state["pages"][0]["_id"]

    cfg = state["config"]

    # ── Helpers ──
    _init_done = [False]
    _save_timer = [None]
    _save_lock = threading.Lock()
    def schedule_save():
        if not _init_done[0]: return
        if _save_timer[0]: _save_timer[0].cancel()
        def do_save():
            with _save_lock:
                try: save_all()
                except Exception: pass
        _save_timer[0] = threading.Timer(2.0, do_save)
        _save_timer[0].daemon = True; _save_timer[0].start()

    def log(msg):
        _flog.info(msg)
        ts = datetime.now().strftime("%H:%M:%S")
        log_list.controls.append(ft.Text(f"[{ts}] {msg}", size=11, selectable=True, font_family="Consolas"))
        if len(log_list.controls) > 400: log_list.controls.pop(0)
        try: page.update()
        except Exception: pass
    def _log_error(context, exc):
        _flog.error(f"{context}: {exc}\n{traceback.format_exc()}")
        log(f"[ERROR] {context}: {exc}")
    def snack(msg, color=ft.Colors.GREEN_700):
        try:
            sb = ft.SnackBar(ft.Text(msg, color=ft.Colors.WHITE), bgcolor=color)
            page.show_dialog(sb)
        except Exception: pass
    def open_dlg(d, modal=True):
        d.modal = modal
        try: page.show_dialog(d)
        except RuntimeError:
            try: d.open = False; d.update()
            except Exception: pass
            try: page.show_dialog(d)
            except Exception: pass
    def close_dlg(d):
        try: d.open = False; d.update()
        except Exception: pass
    def save_all():
        c = dict(state["config"])
        try:
            c["browser_url"] = browser_url.value or ""
            c["browser_wait"] = browser_wait.value or "3.0"
        except NameError:
            pass  # Widgets not yet created (early exit)
        save_config(c); save_tests(state["tests"])
        save_pattern_sets(state["pattern_sets"]); save_selector_bank(state["selector_bank"])
        save_pages(state["pages"])
    def close_browser():
        if state["browser_driver"]:
            kill_driver(state["browser_driver"]); state["browser_driver"] = None
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
        return list(state["pattern_sets"].keys())

    # ================================================================
    # Page selector (Dropdown)
    # ================================================================

    def _page_dd_options():
        return [ft.dropdown.Option(key=pg["_id"], text=f"{pg['number']}. {pg['name']}")
                for pg in state["pages"]]

    def refresh_page_dd(update=True):
        page_dd.options = _page_dd_options()
        page_dd.value = state["selected_page"]
        pg = cur_page()
        if pg:
            n_tests = len(tests_for_page(pg["_id"]))
            pg_url = pg.get("url","")
            url_hint = pg_url[:40] + "..." if len(pg_url) > 40 else pg_url
            page_info_label.value = f"{n_tests}件 | {url_hint}" if url_hint else f"{n_tests}件"
        else:
            page_info_label.value = ""
        if update: page.update()

    def on_page_dd_change(e):
        if not page_dd.value: return
        state["selected_page"] = page_dd.value
        state["selected_test"] = -1
        refresh_page_dd(False); refresh_test_list(False); refresh_steps(False)
        page.update()

    def add_page(e):
        next_num = str(len(state["pages"]) + 1)
        nf = ft.TextField(label="ページ名", width=350, value=f"ページ{next_num}")
        url_f = ft.TextField(label="起点URL", width=450, hint_text="空欄なら全体設定のURLを使用")
        numf = ft.TextField(label="ページ番号", width=100, value=next_num)
        startf = ft.TextField(label="テスト開始番号", width=100, value="1", hint_text="この番号から連番")
        def on_ok(e):
            try:
                name = nf.value.strip(); num = numf.value.strip()
                if not name: snack("名前入力", ft.Colors.RED_600); return
                if not num: snack("番号入力", ft.Colors.RED_600); return
                if any(p["number"] == num for p in state["pages"]):
                    snack(f"番号 {num} は既に使用されています", ft.Colors.RED_600); return
                try: start = int(startf.value.strip() or "1")
                except ValueError: snack("開始番号は整数で", ft.Colors.RED_600); return
                new_pg = {"_id": _new_page_id(), "name": name, "number": num, "start_number": start,
                          "url": url_f.value.strip()}
                state["pages"].append(new_pg)
                state["selected_page"] = new_pg["_id"]
                auto_number_tests()
                refresh_page_dd(False); refresh_test_list(False); refresh_steps(False)
                page.update(); close_dlg(dlg)
            except Exception as x: _log_error("add_page", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("ページ追加"),
            content=ft.Column([nf, url_f, ft.Row([numf, startf], spacing=10)], tight=True, spacing=10, width=500),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def edit_page(e):
        pg = cur_page()
        if not pg: snack("ページを選択してください", ft.Colors.ORANGE_600); return
        nf = ft.TextField(label="ページ名", width=350, value=pg["name"])
        url_f = ft.TextField(label="起点URL", width=450, value=pg.get("url",""), hint_text="空欄なら全体設定のURLを使用")
        numf = ft.TextField(label="ページ番号", width=100, value=pg["number"])
        startf = ft.TextField(label="テスト開始番号", width=100, value=str(pg.get("start_number", 1)))
        def on_ok(e):
            try:
                name = nf.value.strip(); num = numf.value.strip()
                if not name: snack("名前入力", ft.Colors.RED_600); return
                if not num: snack("番号入力", ft.Colors.RED_600); return
                if num != pg["number"] and any(p["number"] == num for p in state["pages"]):
                    snack(f"番号 {num} は既に使用されています", ft.Colors.RED_600); return
                try: start = int(startf.value.strip() or "1")
                except ValueError: snack("開始番号は整数で", ft.Colors.RED_600); return
                pg["name"] = name; pg["number"] = num; pg["start_number"] = start
                pg["url"] = url_f.value.strip()
                auto_number_tests()
                refresh_page_dd(False); refresh_test_list(False); refresh_steps(False)
                page.update(); close_dlg(dlg)
            except Exception as x: _log_error("edit_page", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("ページ編集"),
            content=ft.Column([nf, url_f, ft.Row([numf, startf], spacing=10)], tight=True, spacing=10, width=500),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def del_page(e):
        if len(state["pages"]) <= 1:
            snack("最後のページは削除できません", ft.Colors.RED_600); return
        pg = cur_page()
        if not pg: return
        pid = pg["_id"]; n_tests = len(tests_for_page(pid))
        def on_yes(e):
            try:
                state["tests"] = [t for t in state["tests"] if t.get("page_id") != pid]
                state["pages"] = [p for p in state["pages"] if p["_id"] != pid]
                if state["selected_page"] == pid:
                    state["selected_page"] = state["pages"][0]["_id"] if state["pages"] else None
                state["selected_test"] = -1; auto_number_tests()
                refresh_page_dd(False); refresh_test_list(False); refresh_steps(False)
                page.update(); close_dlg(dlg)
            except Exception as x: _log_error("del_page", x); close_dlg(dlg)
        msg = f"「{pg['name']}」を削除しますか？"
        if n_tests > 0: msg += f"\n（{n_tests}件のテストケースも削除されます）"
        dlg = ft.AlertDialog(title=ft.Text("ページ削除確認"), content=ft.Text(msg),
            actions=[ft.TextButton("削除", on_click=on_yes, style=ft.ButtonStyle(color=ft.Colors.RED_600)),
                     ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def run_page(pid=None):
        if pid is None: pid = state["selected_page"]
        pg = None
        for p in state["pages"]:
            if p["_id"] == pid: pg = p; break
        label = f"【{pg['number']}_{pg['name']}】" if pg else ""
        _do_run(tests_for_page(pid), label)

    # ================================================================
    # Tab 1: Test Cases (1-column ReorderableListView)
    # ================================================================

    def _find_test_idx(tc_id):
        if not _idx_cache["valid"]: _rebuild_idx()
        return _idx_cache["by_id"].get(tc_id, -1)

    def refresh_test_list(update=True):
        _invalidate_idx()
        test_list.controls.clear()
        cur_pid = state["selected_page"]
        page_tests = tests_for_page(cur_pid) if cur_pid else []
        if not page_tests:
            test_list.controls.append(ft.Container(
                ft.Column([ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=32, color=ft.Colors.GREY_400),
                    ft.Text("＋ボタンでテストケースを追加", size=12, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=ft.Padding(20, 40, 20, 20), key="empty"))
        for tc in page_tests:
            global_idx = _find_test_idx(tc.get("_id", ""))
            selected = (global_idx == state["selected_test"])
            pat = tc.get("pattern","")
            n_steps = len([s for s in tc.get("steps",[]) if s["type"] not in ("見出し","コメント")])
            n_pats = len(state["pattern_sets"].get(pat,[])) if pat else 0
            subtitle = f"{n_steps}ステップ"
            if pat: subtitle += f" | {pat} ({n_pats}件)"
            tc_id = tc.get("_id", f"tc_fallback_{global_idx}")
            tc_number = tc.get("number", "")
            is_forced = tc.get("_sub_number") is not None
            num_color = ft.Colors.ORANGE_700 if is_forced else ft.Colors.BLUE_600
            card = ft.Container(
                ft.Row([
                    ft.Text(tc_number, size=11, color=num_color, weight=ft.FontWeight.BOLD, width=50),
                    ft.Column([
                        ft.Text(tc.get("name",""), weight=ft.FontWeight.BOLD, size=12,
                                color=ft.Colors.BLUE_800 if selected else ft.Colors.BLACK,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(subtitle, size=10, color=ft.Colors.GREY_500),
                    ], spacing=1, expand=True),
                    ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, icon_size=14, icon_color=ft.Colors.GREY_400,
                        tooltip="操作", items=[
                            ft.PopupMenuItem(icon=ft.Icons.PLAY_ARROW, content="実行",
                                on_click=lambda e, tid=tc_id: run_single(_find_test_idx(tid))),
                            ft.PopupMenuItem(icon=ft.Icons.COPY, content="コピー",
                                on_click=lambda e, tid=tc_id: copy_test(_find_test_idx(tid))),
                            ft.PopupMenuItem(),
                            ft.PopupMenuItem(icon=ft.Icons.DELETE, content="削除",
                                on_click=lambda e, tid=tc_id: del_test(_find_test_idx(tid))),
                        ]),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                bgcolor=ft.Colors.BLUE_50 if selected else None,
                ink=True, ink_color=ft.Colors.BLUE_100,
                padding=ft.Padding(8, 6, 36, 6), border_radius=6,
                border=ft.Border.all(2, ft.Colors.BLUE_300) if selected else ft.Border.all(1, ft.Colors.GREY_200),
                on_click=lambda e, tid=tc_id: select_test(_find_test_idx(tid)),
                key=tc_id)
            test_list.controls.append(card)
        has_url = bool(state["config"].get("url","").strip())
        has_tests = len(state["tests"]) > 0
        run_btn.disabled = not (has_url and has_tests)
        run_single_btn.disabled = not (has_url and has_tests)
        run_page_btn.disabled = not (has_url and page_tests)
        schedule_save()
        if update: page.update()

    _reorder_dedup = {}
    def _is_dup_reorder(handler, old, new):
        """Flet fires on_reorder twice per drag. Block same (handler, old, new) within 0.5s."""
        now = time.time()
        key = (handler, old, new)
        prev = _reorder_dedup.get(key)
        if prev and now - prev < 0.5: return True
        _reorder_dedup[key] = now; return False

    def on_test_reorder(e):
        try:
            old, new = e.old_index, e.new_index
            if old is None or new is None: return
            if _is_dup_reorder("test", old, new): return
            cur_pid = state["selected_page"]
            page_tests = tests_for_page(cur_pid) if cur_pid else []
            if not (0 <= old < len(page_tests) and 0 <= new <= len(page_tests)): return
            if old == new: return
            _flog.debug(f"on_test_reorder: old={old} new={new} len={len(page_tests)}")
            # Build new page order: pop from old, insert at new
            old_tc = page_tests[old]
            new_order = list(page_tests)
            new_order.pop(old)
            new_order.insert(new, old_tc)
            # Rebuild global list preserving other pages' positions
            result = []
            page_inserted = False
            for t in state["tests"]:
                if t.get("page_id") == cur_pid:
                    if not page_inserted:
                        result.extend(new_order)
                        page_inserted = True
                    # skip original page tests (already added via new_order)
                else:
                    result.append(t)
            if not page_inserted:
                result.extend(new_order)
            state["tests"] = result
            auto_number_tests()
            refresh_test_list(False); refresh_page_dd(False); schedule_save(); page.update()
        except Exception as x: _log_error("on_test_reorder", x)

    def _update_test_highlight():
        """Update visual selection state on existing cards without rebuilding.
        Container structure: Container > Row > [Text(num), Column > [Text(name), Text(sub)], PopupMenu]"""
        sel_tc = state["tests"][state["selected_test"]] if 0 <= state["selected_test"] < len(state["tests"]) else None
        sel_id = sel_tc.get("_id") if sel_tc else None
        for ctrl in test_list.controls:
            if not isinstance(ctrl, ft.Container) or ctrl.key is None: continue
            is_sel = (ctrl.key == sel_id)
            ctrl.bgcolor = ft.Colors.BLUE_50 if is_sel else None
            ctrl.border = ft.Border.all(2, ft.Colors.BLUE_300) if is_sel else ft.Border.all(1, ft.Colors.GREY_200)
            try:
                row = ctrl.content
                name_txt = row.controls[1].controls[0]  # Column > first Text
                name_txt.color = ft.Colors.BLUE_800 if is_sel else ft.Colors.BLACK
            except (AttributeError, IndexError):
                pass

    def select_test(idx):
        if idx < 0 or idx >= len(state["tests"]): return
        if idx == state["selected_test"]: return  # already selected
        state["selected_test"] = idx; state["collapsed"] = set()
        _update_test_highlight()
        refresh_steps(False); page.update()

    def add_test(e):
        cur_pid = state["selected_page"]
        if not cur_pid: snack("ページを選択してください", ft.Colors.ORANGE_600); return
        new_tc = {"name": f"テスト{len(tests_for_page(cur_pid))+1}", "pattern": None, "steps": [],
                  "_id": _new_tc_id(), "page_id": cur_pid, "number": ""}
        state["tests"].append(new_tc); auto_number_tests()
        state["selected_test"] = len(state["tests"]) - 1
        refresh_page_dd(False); refresh_test_list(False); refresh_steps()

    def copy_test(idx):
        if 0 <= idx < len(state["tests"]):
            tc = copy.deepcopy(state["tests"][idx])
            tc["name"] += " (コピー)"; tc["_id"] = _new_tc_id(); tc.pop("_sub_number", None)
            state["tests"].insert(idx + 1, tc); auto_number_tests()
            state["selected_test"] = idx + 1
            refresh_page_dd(False); refresh_test_list(False); refresh_steps()

    def del_test(idx):
        if not (0 <= idx < len(state["tests"])): return
        tc = state["tests"][idx]; name = tc.get("name", f"テスト{idx+1}")
        pat = tc.get("pattern"); pat_orphan = False
        if pat and pat in state["pattern_sets"]:
            pat_orphan = not any(t.get("pattern") == pat for i, t in enumerate(state["tests"]) if i != idx)
        del_pat_cb = ft.Checkbox(label=f"パターンセット「{pat}」も削除", value=True, visible=pat_orphan)
        def on_yes(e):
            try:
                if pat_orphan and del_pat_cb.value and pat in state["pattern_sets"]:
                    del state["pattern_sets"][pat]
                    if state["selected_pat_set"] == pat: state["selected_pat_set"] = None
                state["tests"].pop(idx); auto_number_tests()
                if state["selected_test"] >= len(state["tests"]):
                    state["selected_test"] = len(state["tests"]) - 1  # -1 when empty
                refresh_page_dd(False); refresh_test_list(False); refresh_steps()
                refresh_pat_set_list(False); refresh_pats(); close_dlg(dlg)
            except Exception as x: _log_error("del_test", x); close_dlg(dlg)
        content = ft.Column([ft.Text(f"「{name}」を削除しますか？"), del_pat_cb],
                            tight=True, spacing=8) if pat_orphan else ft.Text(f"「{name}」を削除しますか？")
        dlg = ft.AlertDialog(title=ft.Text("削除確認"), content=content,
            actions=[ft.TextButton("削除", on_click=on_yes, style=ft.ButtonStyle(color=ft.Colors.RED_600)),
                     ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def edit_test_name(e):
        tc = cur_test()
        if not tc: return
        nf = ft.TextField(label="テスト名", value=tc["name"], width=350)
        # 枝番: ページ番号は自動、枝番のみ編集可
        pg = None
        for p in state["pages"]:
            if p["_id"] == tc.get("page_id"): pg = p; break
        pg_prefix = pg["number"] if pg else "?"
        cur_sub = tc.get("_sub_number")
        sub_f = ft.TextField(label="枝番", width=100,
                             value=str(cur_sub) if cur_sub is not None else "",
                             hint_text="自動", keyboard_type=ft.KeyboardType.NUMBER)
        num_preview = ft.Text(f"現在: {tc.get('number','')}", size=11, color=ft.Colors.GREY_600)
        pat_opts = [ft.dropdown.Option("なし")] + [ft.dropdown.Option(n) for n in pat_set_names()]
        pf = ft.Dropdown(label="パターンセット", width=350, value=tc.get("pattern") or "なし", options=pat_opts)
        page_opts = [ft.dropdown.Option(key=pg2["_id"], text=f"{pg2['number']} {pg2['name']}") for pg2 in state["pages"]]
        page_dd_edit = ft.Dropdown(label="ページ", width=350, value=tc.get("page_id", ""), options=page_opts)
        tc_url_f = ft.TextField(label="開始URL（空欄でページURLを使用）", width=450, value=tc.get("url",""),
                                hint_text="個別URLが必要な場合のみ")
        def on_ok(e):
            try:
                tc["name"] = nf.value
                tc["pattern"] = None if pf.value == "なし" else pf.value
                tc["url"] = tc_url_f.value.strip()
                new_pid = page_dd_edit.value
                if new_pid and new_pid != tc.get("page_id"):
                    tc["page_id"] = new_pid; state["selected_page"] = new_pid
                sub_val = sub_f.value.strip()
                if sub_val:
                    try:
                        tc["_sub_number"] = int(sub_val)
                    except ValueError:
                        snack("枝番は整数で入力してください", ft.Colors.RED_600); return
                else:
                    tc.pop("_sub_number", None)
                auto_number_tests()
                refresh_page_dd(False); refresh_test_list(False); refresh_steps(); close_dlg(dlg)
            except Exception as x: _log_error("edit_test_name", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("テストケース設定"),
            content=ft.Column([nf,
                ft.Row([ft.Text(f"{pg_prefix} -", size=14, weight=ft.FontWeight.BOLD), sub_f, num_preview],
                       spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Text("枝番を指定すると、以降のテストも自動で連番になります。空欄で自動。",
                         size=11, color=ft.Colors.GREY_500),
                page_dd_edit, tc_url_f, pf], tight=True, spacing=10, width=500),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    # ── Steps ──
    def refresh_steps(update=True):
        step_reorder.controls.clear()
        tc = cur_test()
        if not tc:
            tc_header.value = "テストケースを選択してください"; tc_pattern_label.value = ""
            if update: page.update()
            return
        tc_header.value = f"{tc.get('number','')} {tc.get('name','')}"
        pat = tc.get("pattern")
        tc_pattern_label.value = f"パターン: {pat} ({len(state['pattern_sets'].get(pat,[]))}件)" if pat else "パターン: なし (1回実行)"
        if not tc.get("steps"):
            step_reorder.controls.append(ft.Container(
                ft.Column([ft.Icon(ft.Icons.TOUCH_APP, size=28, color=ft.Colors.GREY_400),
                    ft.Text("要素ブラウザからクイック追加\nまたは＋ボタンでステップ追加", size=11,
                            color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                padding=ft.Padding(20, 30, 20, 20), key="empty_steps"))
        collapsed = state["collapsed"]; hidden = False
        for i, s in enumerate(tc.get("steps",[])):
            t = s["type"]; key = str(i)
            if t == "見出し":
                sid = i; is_c = sid in collapsed; hidden = is_c
                ic = ft.Icons.EXPAND_LESS if not is_c else ft.Icons.EXPAND_MORE
                step_reorder.controls.append(ft.Container(ft.Row([
                    ft.Icon(ft.Icons.TITLE, color=ft.Colors.BLUE_800, size=16),
                    ft.Text(s.get("text",""), weight=ft.FontWeight.BOLD, size=13, color=ft.Colors.BLUE_800, expand=True),
                    ft.IconButton(ic, icon_size=16, on_click=lambda e, sid=sid: toggle_sec(sid)),
                    ft.IconButton(ft.Icons.EDIT, icon_size=14, on_click=lambda e, idx=i: show_step_dlg(idx)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=14, on_click=lambda e, idx=i: del_step(idx)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor=ft.Colors.BLUE_50, padding=ft.Padding(8,4,36,4), border_radius=4, key=key, height=36))
            elif t == "コメント":
                if hidden: continue
                step_reorder.controls.append(ft.Container(ft.Row([
                    ft.Icon(ft.Icons.COMMENT, color=ft.Colors.GREY_400, size=14),
                    ft.Text(s.get("text",""), size=11, italic=True, color=ft.Colors.GREY_500, expand=True),
                    ft.IconButton(ft.Icons.EDIT, icon_size=14, on_click=lambda e, idx=i: show_step_dlg(idx)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=14, on_click=lambda e, idx=i: del_step(idx)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(8,2,36,2), key=key, height=28))
            else:
                if hidden: continue
                step_reorder.controls.append(ft.Container(ft.Row([
                    ft.Icon(STEP_ICONS.get(t, ft.Icons.HELP), color=ft.Colors.BLUE_600, size=16),
                    ft.Text(t, size=11, color=ft.Colors.GREY_500, width=40),
                    ft.Text(step_short(s), size=12, expand=True),
                    ft.IconButton(ft.Icons.EDIT, icon_size=14, on_click=lambda e, idx=i: show_step_dlg(idx)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=14, on_click=lambda e, idx=i: del_step(idx)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(8,2,36,2), key=key, height=30))
        schedule_save()
        if update: page.update()

    def on_reorder(e):
        try:
            tc = cur_test()
            if not tc: return
            old, new = e.old_index, e.new_index
            if old is None or new is None: return
            if _is_dup_reorder("step", old, new): return
            steps = tc["steps"]; vis = _get_vis(steps)
            if not (0 <= old < len(vis) and 0 <= new <= len(vis)): return
            if old == new: return
            _flog.debug(f"on_reorder(step): old={old} new={new} vis_len={len(vis)}")
            # Extract visible items, reorder, write back
            vis_items = [steps[i] for i in vis]
            item = vis_items.pop(old)
            vis_items.insert(new, item)
            for slot, reordered in zip(vis, vis_items):
                steps[slot] = reordered
            refresh_steps()
        except Exception as x: _log_error("on_reorder", x)

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
        if idx is not None and idx >= len(tc.get("steps", [])): return
        init = tc["steps"][idx] if idx is not None else {}
        t0 = init.get("type","入力")
        type_dd = ft.Dropdown(label="種類", width=160, value=t0, options=[ft.dropdown.Option(t) for t in STEP_TYPES])
        all_sels = get_all_selectors()
        sel_field = ft.Dropdown(label="セレクタ", width=450, value=init.get("selector",""),
            options=[ft.dropdown.Option(s) for s in all_sels], editable=True) if all_sels else \
            ft.TextField(label="セレクタ", width=450, value=init.get("selector",""))
        init_val = init.get("value","")
        pat_names = pat_set_names()
        val_mode_opts = [ft.dropdown.Option("手入力")] + [ft.dropdown.Option(f"パターン: {n}") for n in pat_names]
        init_val_mode = "手入力"
        if init_val == "{パターン}" and tc.get("pattern"):
            init_val_mode = f"パターン: {tc['pattern']}"
        elif init_val == "{パターン}" and pat_names:
            init_val_mode = f"パターン: {pat_names[0]}"
        val_mode = ft.Dropdown(label="値の指定方法", width=450, value=init_val_mode, options=val_mode_opts)
        val_field = ft.TextField(label="値 (固定値を直接入力)", width=450,
            value="" if init_val == "{パターン}" else init_val,
            multiline=True, min_lines=2, max_lines=4)
        # 入力モード
        input_mode_dd = ft.Dropdown(label="入力モード", width=200, value=init.get("input_mode","overwrite"),
            options=[ft.dropdown.Option(key=k, text=t) for k, t in INPUT_MODES])
        # ナビゲーションURL
        nav_url_f = ft.TextField(label="遷移先URL", width=450, value=init.get("url",""),
            hint_text="https://... ({パターン}可)")
        sec_field = ft.TextField(label="秒数", width=120, value=init.get("seconds","1.0"))
        # スクショモード: key=内部値, text=表示名
        _SS_MODES = [
            ("fullpage", "表示範囲のみ"),
            ("fullshot", "ページ全体 (縦長)"),
            ("element", "要素のみ"),
            ("margin", "要素 + 余白"),
        ]
        mode_dd = ft.Dropdown(label="スクショ範囲", width=220, value=init.get("mode","fullpage"),
            options=[ft.dropdown.Option(key=k, text=t) for k, t in _SS_MODES])
        margin_f = ft.TextField(label="マージン(px)", width=120, value=init.get("margin_px","200"))
        text_f = ft.TextField(label="テキスト", width=450, value=init.get("text",""), multiline=True, min_lines=1, max_lines=3)
        def upd(e=None):
            try:
                t = type_dd.value
                sel_field.visible = t in ("入力","クリック","選択") or (t=="スクショ" and mode_dd.value in ("element","margin"))
                is_input = (t == "入力")
                input_mode_dd.visible = is_input
                val_mode.visible = is_input or t == "選択"
                val_field.visible = (is_input or t == "選択") and val_mode.value == "手入力"
                # クリアモードでは値入力不要
                if is_input and input_mode_dd.value == "clear":
                    val_mode.visible = False; val_field.visible = False
                nav_url_f.visible = (t == "ナビゲーション")
                sec_field.visible = t in ("待機", "戻る"); mode_dd.visible = (t=="スクショ")
                margin_f.visible = (t=="スクショ" and mode_dd.value=="margin"); text_f.visible = t in ("見出し","コメント")
                if t == "選択": val_mode.label = "選択肢の指定方法"
                else: val_mode.label = "値の指定方法"
                try: page.update()
                except Exception: pass
            except Exception as x: _log_error("show_step_dlg.upd", x)
        type_dd.on_select = upd; mode_dd.on_select = upd; val_mode.on_select = upd; input_mode_dd.on_select = upd
        # 初期表示を正しく設定
        upd()
        def on_ok(e):
            try:
                t = type_dd.value; step = {"type": t}
                if t in ("見出し","コメント"): step["text"] = text_f.value
                elif t in ("入力","クリック","選択"):
                    s = sel_field.value if hasattr(sel_field,'value') else ""
                    if not s: snack("セレクタを入力", ft.Colors.RED_600); return
                    step["selector"] = s
                    if t == "入力":
                        step["input_mode"] = input_mode_dd.value
                        if input_mode_dd.value != "clear":
                            if val_mode.value == "手入力": step["value"] = val_field.value
                            else:
                                step["value"] = "{パターン}"
                                pn = val_mode.value.replace("パターン: ", "", 1)
                                if pn in state["pattern_sets"]: tc["pattern"] = pn
                    elif t == "選択":
                        if val_mode.value == "手入力": step["value"] = val_field.value
                        else:
                            step["value"] = "{パターン}"
                            pn = val_mode.value.replace("パターン: ", "", 1)
                            if pn in state["pattern_sets"]: tc["pattern"] = pn
                elif t == "戻る":
                    try: step["seconds"] = str(float(sec_field.value))
                    except Exception: snack("秒数を正しく", ft.Colors.RED_600); return
                elif t == "ナビゲーション":
                    url = nav_url_f.value.strip()
                    if not url: snack("URLを入力", ft.Colors.RED_600); return
                    step["url"] = url
                elif t == "待機":
                    try: step["seconds"] = str(float(sec_field.value))
                    except Exception: snack("秒数を正しく", ft.Colors.RED_600); return
                elif t == "スクショ":
                    step["mode"] = mode_dd.value
                    s = sel_field.value if hasattr(sel_field,'value') else ""
                    if mode_dd.value in ("element","margin") and not s: snack("セレクタ必要", ft.Colors.RED_600); return
                    if s: step["selector"] = s
                    if mode_dd.value == "margin":
                        try: step["margin_px"] = str(int(margin_f.value))
                        except Exception: snack("整数で", ft.Colors.RED_600); return
                if idx is not None: tc["steps"][idx] = step
                else: tc["steps"].append(step)
                refresh_steps(False); refresh_test_list(); close_dlg(dlg)
            except Exception as x: _log_error("show_step_dlg.on_ok", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("ステップ編集" if idx is not None else "ステップ追加"),
            content=ft.Column([type_dd, text_f, sel_field, input_mode_dd, val_mode, val_field, nav_url_f, sec_field, mode_dd, margin_f],
                tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, width=500, height=420),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

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
            except Exception: w = 3.0
            time.sleep(w); log(f"[DEBUG] {state['browser_driver'].title}")
            # Always collect ALL elements (including hidden) for filtering
            elems = collect_elements_python(state["browser_driver"], include_hidden=True)
            state["browser_elements"] = list(elems)
            state["selector_bank"][url.split("?")[0]] = [el for el in elems if el.get("visible", True)]
            filter_el_table(); update_url_dd()
        except Exception as x:
            if state["browser_driver"]:
                try: state["browser_driver"].title
                except Exception:
                    kill_driver(state["browser_driver"]); state["browser_driver"] = None
            log(f"[ERROR] {x}")
        finally: load_btn.disabled = False; page.update()
    def filter_el_table(update=True):
        """Filter and display elements based on search text and hidden visibility."""
        el_table.rows.clear()
        query = (el_search.value or "").strip().lower()
        show_hidden = el_show_hidden.value
        visible_count = 0
        total_count = len(state["browser_elements"])
        hidden_count = sum(1 for el in state["browser_elements"] if not el.get("visible", True))
        for i, el in enumerate(state["browser_elements"]):
            is_visible = el.get("visible", True)
            # Filter: hidden visibility
            if not is_visible and not show_hidden:
                continue
            # Filter: search query (match against tag, type, id, name, hint, selector)
            if query:
                searchable = " ".join([
                    el.get("tag", ""), el.get("type", ""), el.get("id", ""),
                    el.get("name", ""), el.get("hint", ""), el.get("selector", "")
                ]).lower()
                if query not in searchable:
                    continue
            visible_count += 1
            # Row color: dim for hidden elements
            row_color = ft.Colors.ORANGE_50 if not is_visible else None
            vis_indicator = "" if is_visible else " [hidden]"
            el_table.rows.append(ft.DataRow(
                cells=[ft.DataCell(ft.Text(el["tag"],size=11)),
                       ft.DataCell(ft.Text(el.get("type",""),size=11)),
                       ft.DataCell(ft.Text(el.get("id") or el.get("name",""),size=11)),
                       ft.DataCell(ft.Text((el.get("hint","")[:20]) + vis_indicator,size=11,
                                           color=ft.Colors.ORANGE_700 if not is_visible else None)),
                       ft.DataCell(ft.Text(el["selector"],size=10,color=ft.Colors.GREY_600))],
                on_select_change=lambda e, idx=i: on_el_click(idx),
                color=row_color))
        status_parts = [f"{visible_count}/{total_count} 要素"]
        if hidden_count > 0:
            status_parts.append(f"(非表示: {hidden_count})")
        if query:
            status_parts.append(f"検索: \"{el_search.value}\"")
        el_status.value = " ".join(status_parts)
        if update:
            try: page.update()
            except Exception: pass
    def update_el_table(elems, url):
        """Legacy wrapper: store elements and apply filter."""
        state["browser_elements"] = list(elems)
        filter_el_table(False)
        log(f"[要素] {url} -> {len(elems)}")
        page.update()
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
            filter_el_table(); snack(f"バンク {len(elems)} 要素")
        else: snack("未保存URL", ft.Colors.ORANGE_600)
    def _el_visible_row_index(target_idx):
        """Map a browser_elements index to the corresponding visible row index in el_table."""
        query = (el_search.value or "").strip().lower()
        show_hidden = el_show_hidden.value
        row_idx = 0
        for i, el_item in enumerate(state["browser_elements"]):
            if not el_item.get("visible", True) and not show_hidden: continue
            if query:
                searchable = " ".join([el_item.get(k, "") for k in ("tag","type","id","name","hint","selector")]).lower()
                if query not in searchable: continue
            if i == target_idx: return row_idx
            row_idx += 1
        return -1

    def on_el_click(idx):
        state["selected_el"] = idx
        el = state["browser_elements"][idx] if idx < len(state["browser_elements"]) else None
        for ri, row in enumerate(el_table.rows):
            row.selected = False
        vis_row = _el_visible_row_index(idx)
        if 0 <= vis_row < len(el_table.rows):
            el_table.rows[vis_row].selected = True
        if el and state["browser_driver"]:
            try: state["browser_driver"].execute_script(HIGHLIGHT_JS, el["selector"])
            except Exception: pass
        page.update()
    def on_el_search_change(e):
        """Re-filter table when search text changes."""
        filter_el_table()
    def on_show_hidden_change(e):
        """Re-filter table when hidden visibility toggles."""
        filter_el_table()
    def quick_add(stype):
        tc = cur_test()
        if not tc: snack("テストケースを選択", ft.Colors.ORANGE_600); return
        idx = state["selected_el"]
        if idx < 0 or idx >= len(state["browser_elements"]): snack("要素をクリック", ft.Colors.ORANGE_600); return
        el_info = state["browser_elements"][idx]; sel = el_info["selector"]
        tag = el_info.get("tag", ""); etype = el_info.get("type", "").lower()
        actual_type = stype
        if tag == "select": actual_type = "選択"
        elif etype in ("radio", "checkbox"): actual_type = "クリック"
        elif tag in ("button", "a") or etype in ("submit", "button", "reset", "image"): actual_type = "クリック"
        step = {"type": actual_type, "selector": sel}
        if actual_type in ("入力", "選択"): step["value"] = "{パターン}"
        tc["steps"].append(step); refresh_steps(False); refresh_test_list(); snack(f"{actual_type}: {sel}")
    def quick_add_all_options(e):
        if not state["browser_driver"]: snack("ページ読込必要", ft.Colors.ORANGE_600); return
        idx = state["selected_el"]
        if idx < 0 or idx >= len(state["browser_elements"]): snack("要素をクリック", ft.Colors.ORANGE_600); return
        el_info = state["browser_elements"][idx]; tag = el_info.get("tag", ""); etype = el_info.get("type", "").lower()
        if tag != "select" and etype != "radio": snack("セレクトボックスまたはラジオボタンを選択", ft.Colors.ORANGE_600); return
        step_type, options = collect_element_options(state["browser_driver"], el_info)
        if not options: snack("選択肢が取得できませんでした", ft.Colors.RED_600); return
        el_type_name = "セレクトボックス" if tag == "select" else "ラジオボタン"
        sel = el_info.get("selector", ""); el_label = el_info.get("name", "") or el_info.get("hint", "") or sel
        if len(el_label) > 25: el_label = el_label[:22] + "..."
        base_name = f"{el_label} ({el_type_name})"; pat_name = base_name; n = 1
        while pat_name in state["pattern_sets"]: n += 1; pat_name = f"{base_name} {n}"
        tc_name = f"{el_label} 全パターン"
        add_ss = ft.Checkbox(label="選択ごとにスクショを追加", value=True)
        info_text = f"{el_type_name} {sel} から {len(options)} 件検出。\nTC「{tc_name}」とPS「{pat_name}」を作成。"
        def on_ok(ev):
            try:
                state["pattern_sets"][pat_name] = list(options); state["selected_pat_set"] = pat_name
                new_steps = []
                if step_type == "選択": new_steps.append({"type": "選択", "selector": sel, "value": "{パターン}"})
                else: new_steps.append({"type": "クリック", "selector": "{パターン}"})
                if add_ss.value: new_steps.append({"type": "スクショ", "mode": "fullpage"})
                cur_pid = state["selected_page"] or (state["pages"][0]["_id"] if state["pages"] else None)
                new_tc = {"name": tc_name, "pattern": pat_name, "steps": new_steps, "_id": _new_tc_id(),
                          "page_id": cur_pid, "number": ""}
                state["tests"].append(new_tc); auto_number_tests()
                state["selected_test"] = len(state["tests"]) - 1
                refresh_steps(False); refresh_test_list(False); refresh_page_dd(False)
                refresh_pat_set_list(False); refresh_pats()
                snack(f"{el_type_name}の全パターン {len(options)} 件を追加"); close_dlg(dlg)
            except Exception as x: _log_error("quick_add_all_options", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text(f"{el_type_name}の全パターン追加"),
            content=ft.Column([ft.Text(info_text, size=13), ft.Divider(),
                ft.Text("プレビュー:", size=11, weight=ft.FontWeight.BOLD),
                ft.Column([ft.Text(f"  {o['label']}" + (f" = {o['value'][:30]}" if o['value'] != o['label'] else ""),
                    size=11, color=ft.Colors.GREY_600) for o in options[:10]]
                    + ([ft.Text(f"  ... 他 {len(options)-10} 件", size=11, color=ft.Colors.GREY_400)]
                       if len(options) > 10 else []), spacing=2),
                ft.Divider(), add_ss], tight=True, spacing=8, width=450, scroll=ft.ScrollMode.AUTO, height=350),
            actions=[ft.TextButton("作成", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda ev: close_dlg(dlg))])
        open_dlg(dlg)
    def capture_form(e):
        tc = cur_test()
        if not tc: snack("テストケースを選択", ft.Colors.ORANGE_600); return
        if not state["browser_driver"]: snack("ページ読込必要", ft.Colors.ORANGE_600); return
        try:
            fs = capture_form_values(state["browser_driver"])
            if not fs: snack("フォーム値なし", ft.Colors.ORANGE_600); return
            tc["steps"].extend(fs); refresh_steps(False); refresh_test_list(); snack(f"フォーム値 {len(fs)} 件")
        except Exception as x: log(f"[ERROR] {x}")
    def close_br(e):
        close_browser(); el_table.rows.clear(); state["browser_elements"].clear()
        el_status.value = "閉じた"; page.update()
    def sync_url(e):
        pg = cur_page()
        browser_url.value = pg.get("url", "") if pg else ""
        page.update()

    # ================================================================
    # Tab 2: Pattern Sets
    # ================================================================
    def refresh_pat_set_list(update=True):
        pat_set_list.controls.clear()
        if not state["pattern_sets"]:
            pat_set_list.controls.append(ft.Container(
                ft.Column([ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=28, color=ft.Colors.GREY_400),
                    ft.Text("＋ボタンでパターンセットを追加", size=11, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                padding=ft.Padding(16, 30, 16, 16), key="empty_ps"))
        for name in state["pattern_sets"].keys():
            pats = state["pattern_sets"][name]; selected = (state["selected_pat_set"] == name)
            pat_set_list.controls.append(ft.Container(
                ft.Row([ft.Column([
                    ft.Text(name, weight=ft.FontWeight.BOLD, size=13,
                            color=ft.Colors.BLUE_800 if selected else ft.Colors.BLACK),
                    ft.Text(f"{len(pats)} パターン", size=10, color=ft.Colors.GREY_500)], spacing=2, expand=True),
                    ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, icon_size=18, icon_color=ft.Colors.GREY_500,
                        tooltip="操作", items=[
                            ft.PopupMenuItem(icon=ft.Icons.EDIT, content="リネーム", on_click=lambda e, n=name: rename_pat_set(n)),
                            ft.PopupMenuItem(),
                            ft.PopupMenuItem(icon=ft.Icons.DELETE, content="削除", on_click=lambda e, n=name: del_pat_set(n))])],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=ft.Colors.BLUE_50 if selected else None,
                padding=ft.Padding(10, 6, 36, 6), border_radius=6,
                border=ft.Border.all(2, ft.Colors.BLUE_300) if selected else ft.Border.all(1, ft.Colors.GREY_200),
                on_click=lambda e, n=name: select_pat_set(n), key=f"ps_{name}"))
        schedule_save()
        if update: page.update()

    def on_pat_set_reorder(e):
        try:
            names = list(state["pattern_sets"].keys())
            old, new = e.old_index, e.new_index
            if old is None or new is None: return
            if _is_dup_reorder("patset", old, new): return
            _flog.debug(f"on_pat_set_reorder: old={old} new={new} len={len(names)}")
            if 0 <= old < len(names) and 0 <= new <= len(names):
                if old == new: return
                item = names.pop(old)
                names.insert(new, item)
                state["pattern_sets"] = {n: state["pattern_sets"][n] for n in names}
                refresh_pat_set_list()
        except Exception as x: _log_error("on_pat_set_reorder", x)

    def select_pat_set(name):
        state["selected_pat_set"] = name; refresh_pat_set_list(False); refresh_pats()

    def add_pat_set(e):
        nf = ft.TextField(label="パターンセット名", width=300)
        def on_ok(e):
            try:
                n = nf.value.strip()
                if not n: snack("名前入力", ft.Colors.RED_600); return
                if n in state["pattern_sets"]: snack("既に存在", ft.Colors.RED_600); return
                state["pattern_sets"][n] = []; state["selected_pat_set"] = n
                refresh_pat_set_list(False); refresh_pats(); close_dlg(dlg)
            except Exception as x: _log_error("add_pat_set", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("パターンセット追加"), content=nf,
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def rename_pat_set(old_name):
        if old_name not in state["pattern_sets"]: return
        nf = ft.TextField(label="新しい名前", width=300, value=old_name)
        def on_ok(e):
            try:
                new_name = nf.value.strip()
                if not new_name: snack("名前入力", ft.Colors.RED_600); return
                if new_name != old_name and new_name in state["pattern_sets"]: snack("既に存在", ft.Colors.RED_600); return
                if new_name != old_name:
                    new_ps = {}
                    for k, v in state["pattern_sets"].items(): new_ps[new_name if k == old_name else k] = v
                    state["pattern_sets"] = new_ps
                    for tc in state["tests"]:
                        if tc.get("pattern") == old_name: tc["pattern"] = new_name
                    if state["selected_pat_set"] == old_name: state["selected_pat_set"] = new_name
                refresh_pat_set_list(False); refresh_pats(False); refresh_test_list(); close_dlg(dlg)
            except Exception as x: _log_error("rename_pat_set", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("リネーム"), content=nf,
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def del_pat_set(name):
        if name not in state["pattern_sets"]: return
        cnt = len(state["pattern_sets"][name])
        def on_yes(e):
            try:
                del state["pattern_sets"][name]
                if state["selected_pat_set"] == name: state["selected_pat_set"] = None
                refresh_pat_set_list(False); refresh_pats(False); refresh_test_list(); close_dlg(dlg)
            except Exception as x: _log_error("del_pat_set", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("削除確認"), content=ft.Text(f"「{name}」({cnt}件) を削除しますか？"),
            actions=[ft.TextButton("削除", on_click=on_yes, style=ft.ButtonStyle(color=ft.Colors.RED_600)),
                     ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def on_pat_reorder(e):
        try:
            name = state["selected_pat_set"]
            if not name or name not in state["pattern_sets"]: return
            pats = state["pattern_sets"][name]
            old, new = e.old_index, e.new_index
            if old is None or new is None: return
            if _is_dup_reorder("pat", old, new): return
            _flog.debug(f"on_pat_reorder: old={old} new={new} len={len(pats)}")
            if 0 <= old < len(pats) and 0 <= new <= len(pats):
                if old == new: return
                item = pats.pop(old)
                pats.insert(new, item)
                refresh_pats()
        except Exception as x: _log_error("on_pat_reorder", x)

    def refresh_pats(update=True):
        pat_items.controls.clear()
        name = state["selected_pat_set"]
        if not name or name not in state["pattern_sets"]:
            pat_header.value = "パターンセットを選択"
            if update: page.update()
            return
        pats = state["pattern_sets"][name]
        pat_header.value = f"{name} ({len(pats)} 件)"
        for i, p in enumerate(pats):
            v = p["value"]; d = v if len(v) <= 55 else v[:52]+"..."
            pat_items.controls.append(ft.Container(ft.Row([
                ft.Text(f"{i+1}", size=10, color=ft.Colors.BLUE_600, weight=ft.FontWeight.BOLD, width=28),
                ft.Column([
                    ft.Text(p["label"], weight=ft.FontWeight.BOLD, size=12, color=ft.Colors.BLUE_800),
                    ft.Text(d, size=11, color=ft.Colors.GREY_600, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=1, expand=True),
                ft.Text(f"{len(v)}字", size=10, color=ft.Colors.GREY_400, width=40),
                ft.IconButton(ft.Icons.EDIT, icon_size=14, on_click=lambda e, idx=i: edit_pat(idx)),
                ft.IconButton(ft.Icons.DELETE, icon_size=14, icon_color=ft.Colors.RED_400, on_click=lambda e, idx=i: del_pat(idx)),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                padding=ft.Padding(10, 6, 36, 6), border=ft.Border.all(1, ft.Colors.GREY_200), border_radius=4, key=f"pat_{i}"))
        schedule_save()
        if update: page.update()

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
            try:
                if not lf.value: snack("ラベル入力", ft.Colors.RED_600); return
                p = {"label": lf.value, "value": vf.value}
                if idx is not None: pats[idx] = p
                else: pats.append(p)
                refresh_pats(False); refresh_pat_set_list(False); refresh_test_list(); close_dlg(dlg)
            except Exception as x: _log_error("edit_pat", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("パターン"),
            content=ft.Column([lf, vf], tight=True, spacing=10, width=450),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def del_pat(idx):
        name = state["selected_pat_set"]
        if name and name in state["pattern_sets"]:
            state["pattern_sets"][name].pop(idx); refresh_pats(False); refresh_pat_set_list(False); refresh_test_list()

    def export_csv(e):
        name = state["selected_pat_set"]
        if not name or name not in state["pattern_sets"]: snack("パターンセットを選択", ft.Colors.ORANGE_600); return
        pats = state["pattern_sets"][name]
        if not pats: snack("パターンなし", ft.Colors.ORANGE_600); return
        outdir = state["config"].get("output_dir", os.path.join(get_app_dir(), "screenshots"))
        os.makedirs(outdir, exist_ok=True)
        fp = os.path.join(outdir, f"{_safe_filename(name, 50)}.csv")
        save_csv(fp, pats); snack(f"エクスポート: {fp}")

    def load_template(e):
        td = get_templates_dir()
        if not td: snack("templatesなし", ft.Colors.RED_600); return
        name = state["selected_pat_set"]
        if not name: snack("パターンセットを選択", ft.Colors.ORANGE_600); return
        csvs = sorted([f for f in os.listdir(td) if f.lower().endswith(".csv")])
        if not csvs: snack("CSVなし", ft.Colors.RED_600); return
        csv_cache = {f: load_csv(os.path.join(td, f)) for f in csvs}
        def on_sel(fn):
            try:
                state["pattern_sets"][name].extend(csv_cache[fn])
                refresh_pats(False); refresh_pat_set_list(False); refresh_test_list()
                snack(f"{len(csv_cache[fn])} 件追加"); close_dlg(dlg)
            except Exception as x: _log_error("load_template", x); close_dlg(dlg)
        cards = [ft.Card(ft.Container(ft.Column([
            ft.Text(os.path.splitext(f)[0], weight=ft.FontWeight.BOLD, size=13),
            ft.Text(f"{len(csv_cache[f])} 件", size=11, color=ft.Colors.GREY_600)], spacing=2),
            padding=12, on_click=lambda e, fn=f: on_sel(fn)), elevation=2) for f in csvs]
        dlg = ft.AlertDialog(title=ft.Text("テンプレート"),
            content=ft.Column(cards, spacing=6, scroll=ft.ScrollMode.AUTO, width=380, height=300),
            actions=[ft.TextButton("閉じる", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def _ensure_pat_set(ml_hint=""):
        """パターンセット未選択なら自動作成して返す。選択中ならその名前を返す。"""
        name = state["selected_pat_set"]
        if name and name in state["pattern_sets"]:
            return name
        # 自動作成
        auto_name = f"パターンセット（{ml_hint}字）" if ml_hint else f"パターンセット{len(state['pattern_sets'])+1}"
        # 同名があればサフィックス
        base = auto_name; cnt = 2
        while auto_name in state["pattern_sets"]:
            auto_name = f"{base}_{cnt}"; cnt += 1
        state["pattern_sets"][auto_name] = []
        state["selected_pat_set"] = auto_name
        refresh_pat_set_list(False)
        return auto_name

    def gen_input_check(e):
        cf = ft.TextField(label="繰り返す文字", width=80, value="あ")
        mf = ft.TextField(label="max_length", width=140, hint_text="例: 50")
        def on_ok(e):
            try:
                ch = cf.value or "あ"; ml = mf.value.strip()
                if not ml or not ml.isdigit() or int(ml) < 1: snack("max_lengthを正の整数で", ft.Colors.RED_600); return
                n = int(ml)
                name = _ensure_pat_set(ml)
                ps = []
                if n > 1: ps.append({"label": f"max-1({n-1}文字)", "value": ch * (n - 1)})
                ps.append({"label": f"max({n}文字)", "value": ch * n})
                ps.append({"label": f"max+1({n+1}文字)", "value": ch * (n + 1)})
                state["pattern_sets"][name].extend(ps)
                select_pat_set(name)
                refresh_pats(False); refresh_pat_set_list(False); refresh_test_list()
                snack(f"{name} に {len(ps)} 件追加"); close_dlg(dlg)
            except Exception as x: _log_error("gen_input_check", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("max_length用 境界値生成（文字）"),
            content=ft.Column([cf, mf,
                ft.Text("指定文字を max-1, max, max+1 文字ずつ生成", size=11, color=ft.Colors.GREY_600),
                ft.Text("パターンセット未選択なら自動作成します", size=10, color=ft.Colors.BLUE_400)],
                tight=True, spacing=10, width=350),
            actions=[ft.TextButton("追加", on_click=on_ok), ft.TextButton("閉じる", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def gen_numeric_check(e):
        mf = ft.TextField(label="max_length", width=140, hint_text="例: 10")
        DIGITS = "1234567890"
        def _make_num(length):
            """半角数値文字列を指定長で生成 (1234567890を繰り返し)"""
            if length <= 0: return ""
            return (DIGITS * (length // 10 + 1))[:length]
        def on_ok(e):
            try:
                ml = mf.value.strip()
                if not ml or not ml.isdigit() or int(ml) < 1: snack("max_lengthを正の整数で", ft.Colors.RED_600); return
                n = int(ml)
                name = _ensure_pat_set(ml)
                ps = []
                if n > 1: ps.append({"label": f"数値max-1({n-1}桁)", "value": _make_num(n - 1)})
                ps.append({"label": f"数値max({n}桁)", "value": _make_num(n)})
                ps.append({"label": f"数値max+1({n+1}桁)", "value": _make_num(n + 1)})
                state["pattern_sets"][name].extend(ps)
                select_pat_set(name)
                refresh_pats(False); refresh_pat_set_list(False); refresh_test_list()
                snack(f"{name} に {len(ps)} 件追加"); close_dlg(dlg)
            except Exception as x: _log_error("gen_numeric_check", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("max_length用 境界値生成（半角数値）"),
            content=ft.Column([mf,
                ft.Text("1234567890 を繰り返して max-1, max, max+1 桁生成", size=11, color=ft.Colors.GREY_600),
                ft.Text("パターンセット未選択なら自動作成します", size=10, color=ft.Colors.BLUE_400)],
                tight=True, spacing=10, width=350),
            actions=[ft.TextButton("追加", on_click=on_ok), ft.TextButton("閉じる", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    # ── Settings / Info / Run ──
    def show_settings(e):
        c = state["config"]
        auf = ft.TextField(label="Basic認証ID", value=c.get("basic_auth_user",""), width=210)
        apf = ft.TextField(label="パスワード", value=c.get("basic_auth_pass",""), password=True, width=210)
        of = ft.TextField(label="出力フォルダ", value=c.get("output_dir", os.path.join(get_app_dir(), "screenshots")), width=450)
        hl = ft.Checkbox(label="ヘッドレスモード (ブラウザ非表示)", value=c.get("headless")=="1")
        ss = ft.Checkbox(label="HTMLソース保存 (diff比較用)", value=c.get("save_source")=="1")
        def on_ok(e):
            try:
                state["config"].update({"basic_auth_user":auf.value,"basic_auth_pass":apf.value,
                    "output_dir":of.value,"headless":"1" if hl.value else "0",
                    "save_source":"1" if ss.value else "0"})
                save_config(state["config"]); snack("設定保存")
                refresh_test_list(False); page.update(); close_dlg(dlg)
            except Exception as x: _log_error("show_settings", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("設定"),
            content=ft.Column([ft.Row([auf, apf], spacing=10), of, hl, ss], tight=True, spacing=12, width=500),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def show_info(e):
        dlg = ft.AlertDialog(title=ft.Text("情報"),
            content=ft.Column([ft.Text(f"{APP_NAME}  v{APP_VERSION}", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Web Screenshot Automation Tool"), ft.Divider(),
                ft.Text(f"Developed by {APP_AUTHOR}")], tight=True, spacing=8, width=300),
            actions=[ft.TextButton("閉じる", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg, modal=False)

    def _do_run(test_cases_to_run, run_label=""):
        c = state["config"]
        # URL check: global, page, or test-level URL must exist somewhere
        has_any_url = any(p.get("url","").strip() for p in state["pages"])
        if not has_any_url:
            has_any_url = any(t.get("url","").strip() for t in test_cases_to_run)
        if not has_any_url: snack("URL未設定（ページまたはテストケースに設定してください）", ft.Colors.RED_600); return
        if not test_cases_to_run: snack("テストケース0件", ft.Colors.RED_600); return
        close_browser()
        stop_ev = threading.Event(); state["stop_event"] = stop_ev
        run_btn.disabled = True; run_single_btn.disabled = True; run_page_btn.disabled = True
        stop_btn.visible = True; stop_btn.disabled = False; open_folder_btn.visible = False
        progress.visible = True; progress.value = 0; progress_label.visible = True; progress_label.value = ""
        nav_bar.selected_index = 0; switch_tab(0); page.update(); save_all()
        def on_progress(current, total):
            progress.value = current / total if total > 0 else None
            progress_label.value = f"{current}/{total} パターン"; page.update()
        def on_done(outdir=None):
            run_btn.disabled = False; run_single_btn.disabled = False; run_page_btn.disabled = False
            stop_btn.visible = False; progress.visible = False; progress_label.visible = False
            state["stop_event"] = None
            if outdir and os.path.isdir(outdir):
                open_folder_btn.data = outdir; open_folder_btn.visible = True
            page.update()
        page.run_thread(run_all_tests, dict(c), list(test_cases_to_run),
                        dict(state["pattern_sets"]), lambda m: log(m), on_done, stop_ev, on_progress,
                        state["test_drivers"], list(state["pages"]), run_label)

    def run_click(e):
        _do_run(state["tests"], "【全テスト】")
    def run_single(idx):
        if 0 <= idx < len(state["tests"]):
            tc = state["tests"][idx]
            label = f"【{tc.get('number','')}_{tc.get('name','')}】"
            _do_run([tc], label)
    def stop_click(e):
        ev = state.get("stop_event")
        if ev: ev.set(); stop_btn.disabled = True; log("[中断] 中断リクエスト送信..."); page.update()

    def switch_tab(idx):
        tc_content.visible = (idx == 0); ps_content.visible = (idx == 1)
        if idx == 0: refresh_page_dd(False); refresh_test_list(False); refresh_steps(False)
        else: refresh_pat_set_list(False); refresh_pats(False)
        page.update()
    def on_nav(e): switch_tab(e.control.selected_index)

    # ── Build controls ──
    browser_url = ft.TextField(label="URL", expand=True, dense=True, value=cfg.get("browser_url",""))
    browser_url_dd = ft.Dropdown(label="履歴", width=200, dense=True,
        options=[ft.dropdown.Option(u) for u in state["selector_bank"].keys()], on_select=on_url_dd_sel)
    browser_wait = ft.TextField(label="秒", width=55, dense=True, value=cfg.get("browser_wait","3.0"))
    load_btn = ft.Button("読込", icon=ft.Icons.REFRESH, on_click=load_page_click)
    el_status = ft.Text("未読込", size=11, color=ft.Colors.GREY_500)
    el_search = ft.TextField(label="検索", width=250, dense=True, hint_text="セレクタ/id/name/ヒント",
                             on_change=on_el_search_change, prefix_icon=ft.Icons.SEARCH)
    el_show_hidden = ft.Checkbox(label="非表示要素も表示", value=False, on_change=on_show_hidden_change)
    el_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("タグ",size=11)), ft.DataColumn(ft.Text("type",size=11)),
                 ft.DataColumn(ft.Text("id/name",size=11)), ft.DataColumn(ft.Text("ヒント",size=11)),
                 ft.DataColumn(ft.Text("セレクタ",size=11))],
        rows=[], column_spacing=8, data_row_min_height=28, heading_row_height=30,
        show_checkbox_column=True)

    # Page selector
    page_dd = ft.Dropdown(label="ページ", width=200, dense=True,
                          options=_page_dd_options(), value=state["selected_page"],
                          on_select=on_page_dd_change)
    page_info_label = ft.Text("", size=10, color=ft.Colors.GREY_500)

    test_list = ft.ReorderableListView(controls=[], on_reorder=on_test_reorder, spacing=3, expand=True)
    step_reorder = ft.ReorderableListView(controls=[], on_reorder=on_reorder, spacing=1, expand=True)
    log_list = ft.ListView(spacing=1, auto_scroll=True, height=130)
    _log_expanded = [False]
    def toggle_log(e):
        _log_expanded[0] = not _log_expanded[0]
        log_list.height = 350 if _log_expanded[0] else 130
        log_toggle_btn.icon = ft.Icons.EXPAND_LESS if _log_expanded[0] else ft.Icons.EXPAND_MORE
        log_toggle_btn.tooltip = "ログを縮小" if _log_expanded[0] else "ログを拡大"; page.update()
    log_toggle_btn = ft.IconButton(ft.Icons.EXPAND_MORE, icon_size=16, tooltip="ログを拡大", on_click=toggle_log)
    tc_header = ft.Text("", weight=ft.FontWeight.BOLD, size=15)
    tc_pattern_label = ft.Text("", size=11, color=ft.Colors.GREY_600)
    pat_set_list = ft.ReorderableListView(controls=[], on_reorder=on_pat_set_reorder, spacing=4, expand=True)
    pat_items = ft.ReorderableListView(controls=[], on_reorder=on_pat_reorder, spacing=3, expand=True)
    pat_header = ft.Text("", weight=ft.FontWeight.BOLD, size=15)
    progress = ft.ProgressBar(visible=False, value=0)
    progress_label = ft.Text("", size=11, color=ft.Colors.GREY_600, visible=False)
    run_single_btn = ft.Button("選択テスト実行", icon=ft.Icons.PLAY_ARROW, bgcolor=ft.Colors.GREEN_600,
                               color=ft.Colors.WHITE, on_click=lambda e: run_single(state["selected_test"]), height=42)
    run_page_btn = ft.Button("ページ実行", icon=ft.Icons.PLAY_ARROW, bgcolor=ft.Colors.TEAL_600,
                             color=ft.Colors.WHITE, on_click=lambda e: run_page(), height=42)
    run_btn = ft.Button("全テスト実行", icon=ft.Icons.PLAY_ARROW, bgcolor=ft.Colors.BLUE_600,
                        color=ft.Colors.WHITE, on_click=run_click, height=42)
    stop_btn = ft.Button("中断", icon=ft.Icons.STOP, bgcolor=ft.Colors.RED_600,
                         color=ft.Colors.WHITE, on_click=stop_click, height=42, visible=False)
    def open_folder_click(e):
        path = open_folder_btn.data
        if path and os.path.isdir(path):
            import subprocess; subprocess.Popen(["explorer", os.path.normpath(path)])
    open_folder_btn = ft.Button("出力フォルダを開く", icon=ft.Icons.FOLDER_OPEN,
                                on_click=open_folder_click, height=42, visible=False)

    # ── Layout: Tab 1 ──
    tc_content = ft.Row([
        ft.Container(ft.Column([
            ft.Row([page_dd,
                    ft.IconButton(ft.Icons.ADD, tooltip="ページ追加", icon_size=18, on_click=add_page),
                    ft.IconButton(ft.Icons.EDIT, tooltip="ページ編集", icon_size=18, on_click=edit_page),
                    ft.IconButton(ft.Icons.DELETE, tooltip="ページ削除", icon_size=18, on_click=del_page),
                   ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            page_info_label,
            ft.Divider(height=1),
            ft.Row([ft.Text("テストケース", weight=ft.FontWeight.BOLD, size=13),
                    ft.IconButton(ft.Icons.ADD, tooltip="テスト追加", icon_size=16, on_click=add_test)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            test_list,
        ], spacing=4), width=320, padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),
        ft.Column([
            ft.Container(ft.Column([
                ft.Row([tc_header, ft.IconButton(ft.Icons.EDIT, icon_size=16, tooltip="テスト設定", on_click=edit_test_name)],
                       alignment=ft.MainAxisAlignment.START),
                tc_pattern_label,
                ft.Row([ft.IconButton(ft.Icons.ADD, tooltip="ステップ追加", icon_size=18, on_click=lambda e: show_step_dlg(None)),
                        ft.IconButton(ft.Icons.TITLE, tooltip="見出し", icon_size=18,
                            on_click=lambda e: (cur_test() and cur_test()["steps"].append({"type":"見出し","text":"セクション"}), refresh_steps())),
                        ft.IconButton(ft.Icons.COMMENT, tooltip="コメント", icon_size=18,
                            on_click=lambda e: (cur_test() and cur_test()["steps"].append({"type":"コメント","text":""}), refresh_steps()))], spacing=0),
                step_reorder,
            ], spacing=4), padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8, expand=True),
            ft.Container(ft.Column([
                ft.Row([ft.Text("ログ", size=12, weight=ft.FontWeight.BOLD), log_toggle_btn],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN), log_list]),
                padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),
        ], expand=3, spacing=6),
        ft.Container(ft.Column([
            ft.Text("要素ブラウザ", weight=ft.FontWeight.BOLD, size=13),
            ft.Row([browser_url, browser_wait], spacing=4),
            ft.Row([browser_url_dd, ft.OutlinedButton("保存済みを読込", on_click=load_bank)], spacing=4),
            ft.Row([load_btn, ft.OutlinedButton("閉じる", on_click=close_br),
                    ft.TextButton("ページURLを使う", icon=ft.Icons.SYNC, on_click=sync_url)], spacing=4, wrap=True),
            ft.Row([el_search, el_show_hidden], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            el_status,
            ft.Container(ft.Column([el_table], scroll=ft.ScrollMode.AUTO),
                expand=True, border=ft.Border.all(1, ft.Colors.GREY_200), border_radius=4),
            ft.Text("ステップ追加:", size=10, color=ft.Colors.GREY_500),
            ft.Row([ft.Button("入力", icon=ft.Icons.EDIT, on_click=lambda e: quick_add("入力")),
                    ft.Button("クリック", icon=ft.Icons.MOUSE, on_click=lambda e: quick_add("クリック")),
                    ft.Button("選択", icon=ft.Icons.ARROW_DROP_DOWN_CIRCLE, on_click=lambda e: quick_add("選択"))], spacing=4),
            ft.Row([ft.Button("全パターン", icon=ft.Icons.LIST, on_click=quick_add_all_options),
                    ft.Button("値取込", icon=ft.Icons.SAVE, on_click=capture_form)], spacing=4),
        ], spacing=4), width=500, padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),
    ], spacing=8, expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

    # ── Layout: Tab 2 ──
    ps_content = ft.Row([
        ft.Container(ft.Column([
            ft.Row([ft.Text("パターンセット", weight=ft.FontWeight.BOLD, size=14),
                    ft.IconButton(ft.Icons.ADD, tooltip="追加", icon_size=18, on_click=add_pat_set)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            pat_set_list,
        ], spacing=4), width=320, padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),
        ft.Column([
            ft.Row([pat_header,
                    ft.Row([ft.Button("追加", icon=ft.Icons.ADD, on_click=add_pat),
                            ft.Button("テンプレート", icon=ft.Icons.FOLDER_OPEN, on_click=load_template),
                            ft.Button("文字max", icon=ft.Icons.STRAIGHTEN, on_click=gen_input_check, tooltip="max_length境界値(文字)"),
                            ft.Button("数値max", icon=ft.Icons.PIN, on_click=gen_numeric_check, tooltip="max_length境界値(半角数値)"),
                            ft.Button("CSVエクスポート", icon=ft.Icons.DOWNLOAD, on_click=export_csv)], spacing=4)],
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
        ft.Row([progress, progress_label], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([open_folder_btn, stop_btn, run_single_btn, run_page_btn, run_btn],
               alignment=ft.MainAxisAlignment.END, spacing=8)], expand=True, spacing=4))
    page.navigation_bar = nav_bar

    refresh_page_dd(False); refresh_test_list(False); refresh_steps(False)
    refresh_pat_set_list(False); refresh_pats(False)
    page.update()
    _init_done[0] = True
    _flog.info(f"{APP_NAME} v{APP_VERSION} started ({len(state['pages'])} pages, {len(state['tests'])} tests, {len(state['pattern_sets'])} pattern sets)")

    def _cleanup_all_drivers():
        """Best-effort quit of Selenium drivers (non-blocking)."""
        for drv in list(state.get("test_drivers", [])):
            try: drv.quit()
            except Exception: pass
        state["test_drivers"] = []
        if state["browser_driver"]:
            try: state["browser_driver"].quit()
            except Exception: pass
            state["browser_driver"] = None

    def _kill_children_and_exit():
        """Kill all child processes (Flet runtime, WebView) but NOT this process.
        Then sys.exit(0) so PyInstaller's atexit cleanup can delete _MEIxxxxxx."""
        my_pid = os.getpid()
        _flog.info(f"Killing child processes of PID={my_pid}")
        if sys.platform == 'win32':
            import subprocess as _sp
            child_pids = []
            # Method 1: wmic (Win10, some Win11)
            try:
                result = _sp.run(
                    ['wmic', 'process', 'where', f'ParentProcessId={my_pid}', 'get', 'ProcessId'],
                    capture_output=True, text=True, timeout=3, creationflags=0x08000000)
                for line in result.stdout.strip().split('\n'):
                    cpid = line.strip()
                    if cpid.isdigit() and cpid != str(my_pid):
                        child_pids.append(cpid)
            except Exception:
                pass
            # Method 2: PowerShell (Win11 where wmic is removed)
            if not child_pids:
                try:
                    ps_cmd = f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={my_pid}' | Select-Object -ExpandProperty ProcessId"
                    result = _sp.run(['powershell', '-NoProfile', '-Command', ps_cmd],
                        capture_output=True, text=True, timeout=5, creationflags=0x08000000)
                    for line in result.stdout.strip().split('\n'):
                        cpid = line.strip()
                        if cpid.isdigit() and cpid != str(my_pid):
                            child_pids.append(cpid)
                except Exception:
                    pass
            # Kill found children
            for cpid in child_pids:
                try:
                    _sp.run(['taskkill', '/F', '/T', '/PID', cpid],
                            capture_output=True, timeout=3, creationflags=0x08000000)
                except Exception:
                    pass
            if child_pids:
                time.sleep(0.2)
            _flog.info(f"Killed {len(child_pids)} child processes")
        else:
            try:
                import signal as _sig
                os.killpg(os.getpgid(my_pid), _sig.SIGTERM)
            except Exception:
                pass
        # Normal exit → PyInstaller atexit cleanup runs → _MEI folder deleted
        _deadline = threading.Timer(1.0, lambda: os._exit(0))
        _deadline.daemon = True; _deadline.start()
        sys.exit(0)

    def on_window_event(e: ft.WindowEvent):
        if e.type == ft.WindowEventType.CLOSE:
            # 1. Save data (fast)
            if _save_timer[0]: _save_timer[0].cancel()
            with _save_lock:
                try: save_all()
                except Exception: pass
            # 2. Signal any running tests to stop
            ev = state.get("stop_event")
            if ev: ev.set()
            # 3. Best-effort Selenium cleanup
            _cleanup_all_drivers()
            # 4. Kill Flet children, then clean exit
            _kill_children_and_exit()

    import signal
    def _signal_cleanup(signum, frame):
        try: save_all()
        except Exception: pass
        _kill_children_and_exit()
    try:
        signal.signal(signal.SIGTERM, _signal_cleanup)
        signal.signal(signal.SIGINT, _signal_cleanup)
    except (OSError, ValueError): pass

    page.window.prevent_close = True
    page.window.on_event = on_window_event

if __name__ == "__main__":
    ft.run(main)
