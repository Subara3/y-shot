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
APP_VERSION = "2.1"
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
    # Pass 1: collect basic info
    hidden_els = []  # (index_in_results, selenium_element)
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
            entry = {"selector": sel, "tag": tag, "type": etype, "name": ename, "id": eid, "hint": hint, "visible": visible, "hidden_reason": ""}
            if not visible:
                hidden_els.append((len(results), el))
            results.append(entry)
        except Exception: continue
    # Pass 2: batch JS for hidden reasons (single call instead of per-element)
    if hidden_els:
        batch_els = [el for _, el in hidden_els]
        try:
            reasons = driver.execute_script(
                "var results=[];"
                "for(var i=0;i<arguments.length;i++){"
                "  var e=arguments[i];"
                "  try{var s=window.getComputedStyle(e);"
                "  if(s.display==='none'){results.push('display:none');continue;}"
                "  if(s.visibility==='hidden'){results.push('visibility:hidden');continue;}"
                "  if(parseFloat(s.opacity)===0){results.push('opacity:0');continue;}"
                "  var r=e.getBoundingClientRect();"
                "  if(r.width===0&&r.height===0){results.push('size:0');continue;}"
                "  if(r.bottom<0||r.right<0){results.push('off-viewport');continue;}"
                "  results.push('other');}catch(x){results.push('unknown');}"
                "}return results;", *batch_els) or []
            for j, (idx, _) in enumerate(hidden_els):
                if j < len(reasons):
                    results[idx]["hidden_reason"] = reasons[j]
        except Exception:
            for idx, _ in hidden_els:
                results[idx]["hidden_reason"] = "unknown"
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
    # Prefer stable test attributes over name/class
    for attr in ("data-testid", "data-cy", "data-test"):
        val = el.get_attribute(attr) or ""
        if val:
            s = f'[{attr}="{_css_escape_attr(val)}"]'
            try:
                if len(driver.find_elements(By.CSS_SELECTOR, s)) == 1: return s
            except Exception: pass
    aria = el.get_attribute("aria-label") or ""
    if aria:
        s = f'{tag}[aria-label="{_css_escape_attr(aria)}"]'
        try:
            if len(driver.find_elements(By.CSS_SELECTOR, s)) == 1: return s
        except Exception: pass
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
    "var all=document.querySelectorAll(s);"
    "if(!all.length)return JSON.stringify({found:0});"
    "var e=all[0];"
    "e.scrollIntoView({block:'center',behavior:'instant'});"
    "var r=e.getBoundingClientRect(),h=document.createElement('div');h.id='__yshot_hl';"
    "var color=all.length===1?'#FF4444':'#FF8800';"
    "h.style.cssText='position:fixed;border:3px solid '+color+';background:rgba(255,68,68,0.15);"
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
    "return JSON.stringify({found:all.length,tag:e.tagName,id:e.id||'',name:e.getAttribute('name')||''});"
    "}catch(x){return JSON.stringify({found:0,error:x.message});}})(arguments[0]);")

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

STEP_TYPES = ["入力", "クリック", "選択", "待機", "要素待機", "スクロール", "スクショ", "戻る", "ナビゲーション", "見出し", "コメント"]
STEP_ICONS = {"入力": ft.Icons.EDIT, "クリック": ft.Icons.MOUSE,
              "選択": ft.Icons.ARROW_DROP_DOWN_CIRCLE,
              "待機": ft.Icons.HOURGLASS_BOTTOM, "要素待機": ft.Icons.VISIBILITY,
              "スクロール": ft.Icons.SWAP_VERT,
              "スクショ": ft.Icons.CAMERA_ALT,
              "戻る": ft.Icons.ARROW_BACK, "ナビゲーション": ft.Icons.OPEN_IN_BROWSER,
              "見出し": ft.Icons.TITLE, "コメント": ft.Icons.COMMENT}
SCROLL_MODES = [("element", "要素へスクロール"), ("pixel", "ピクセル指定"), ("top", "先頭に戻る")]
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
    if t == "スクロール":
        sm = step.get("scroll_mode", "element")
        if sm == "top": return "先頭に戻る"
        if sm == "pixel": return f"↓{step.get('scroll_px','0')}px"
        sel = step.get("selector","")
        if len(sel) > 25: sel = sel[:22]+"..."
        return f"→ {sel}"
    if t == "要素待機":
        sel = step.get("selector",""); timeout = step.get("seconds","10")
        if len(sel) > 25: sel = sel[:22]+"..."
        return f"{sel} (最大{timeout}秒)"
    if t == "スクショ":
        m = step.get("mode","fullpage")
        if m == "fullpage": return "表示範囲"
        if m == "fullshot": return "ページ全体(縦長)"
        if m == "margin": return f"要素+{step.get('margin_px','500')}px"
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

def _generate_report(outdir, log_cb, pages=None):
    """Generate an HTML report. Walks subdirectories for PNGs."""
    try:
        all_pngs = []
        for root, dirs, files in os.walk(outdir):
            dirs[:] = [d for d in sorted(dirs) if not d.startswith("_")]
            for fn in sorted(files):
                if fn.lower().endswith(".png"):
                    rel = os.path.relpath(os.path.join(root, fn), outdir).replace("\\", "/")
                    all_pngs.append(rel)
        if not all_pngs: return
        # Collect page URLs
        url_lines = ""
        if pages:
            urls = [f'<li><strong>{pg.get("number","")}.{pg.get("name","")}</strong>: <a href="{pg.get("url","")}">{pg.get("url","")}</a></li>'
                    for pg in pages if pg.get("url","")]
            if urls: url_lines = '<h2>対象URL</h2><ul>' + ''.join(urls) + '</ul>'
        html = ['<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">',
                '<title>y-shot レポート</title>',
                '<style>body{font-family:sans-serif;max-width:1200px;margin:0 auto;padding:20px;background:#f8f9fa}',
                'h1{color:#333}h2{color:#555;margin-top:32px;border-bottom:2px solid #ddd;padding-bottom:4px}',
                '.card{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.1);margin:16px 0;padding:16px}',
                '.card img{max-width:100%;border:1px solid #ddd;border-radius:4px}',
                '.card .name{font-weight:bold;color:#555;margin-bottom:8px;font-size:14px}',
                '.card .meta{font-size:12px;color:#888;margin-bottom:6px}</style></head><body>',
                f'<h1>y-shot レポート</h1><p>{os.path.basename(outdir)} — {len(all_pngs)} 枚</p>',
                url_lines]
        cur_dir = None
        for rel in all_pngs:
            d = os.path.dirname(rel)
            if d != cur_dir:
                cur_dir = d
                if d: html.append(f'<h2>{d}</h2>')
            # A5: Parse filename for metadata
            fn_base = os.path.splitext(os.path.basename(rel))[0]
            parts = fn_base.split('_')
            meta = ""
            if len(parts) >= 4:
                # Format: 001_番号_テスト名_p01_パターン_ss1
                tc_num = parts[1] if len(parts) > 1 else ""
                tc_name = parts[2] if len(parts) > 2 else ""
                pat_label = parts[4] if len(parts) > 4 else ""
                meta = f'<div class="meta">{tc_num} {tc_name} — {pat_label}</div>'
            html.append(f'<div class="card">{meta}<div class="name">{rel}</div><img src="{rel}" loading="lazy"></div>')
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

        # Write URL summary on a cover sheet
        ws_cover = wb.active; ws_cover.title = "概要"
        ws_cover.column_dimensions["A"].width = 20; ws_cover.column_dimensions["B"].width = 80
        ws_cover.cell(row=1, column=1, value="y-shot レポート").font = ws_cover.cell(row=1, column=1).font.copy(bold=True, size=14)
        ws_cover.cell(row=2, column=1, value="実行日時"); ws_cover.cell(row=2, column=2, value=os.path.basename(outdir))
        ws_cover.cell(row=3, column=1, value="スクショ数"); ws_cover.cell(row=3, column=2, value=len(all_pngs))
        if run_label: ws_cover.cell(row=4, column=1, value="実行ラベル"); ws_cover.cell(row=4, column=2, value=run_label)
        row = 6
        ws_cover.cell(row=row, column=1, value="対象URL").font = ws_cover.cell(row=row, column=1).font.copy(bold=True, size=12)
        row += 1
        if pages:
            for pg in pages:
                url = pg.get("url", "")
                if url:
                    ws_cover.cell(row=row, column=1, value=f"{pg.get('number','')}.{pg.get('name','')}")
                    ws_cover.cell(row=row, column=2, value=url)
                    row += 1

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
            for folder_name, pngs in groups.items():
                sheet_name = folder_name[:31] if folder_name != "root" else "エビデンス"
                _base, _n = sheet_name, 2
                while sheet_name in [s.title for s in wb.worksheets]:
                    sheet_name = f"{_base[:28]}({_n})"; _n += 1
                ws = wb.create_sheet(title=sheet_name)
                _write_sheet(ws, pngs)
        else:
            ws = wb.create_sheet(title="エビデンス")
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
        opts.add_argument("--ignore-certificate-errors")
        opts.add_argument("--allow-insecure-localhost")
        opts.add_argument("--disable-features=HttpsUpgrades")
        if config.get("headless") == "1":
            opts.add_argument("--headless=new")
            log_cb("[INFO] ヘッドレスモード")
        driver = webdriver.Chrome(options=opts); driver.set_window_size(1280, 900)
        if driver_ref is not None: driver_ref.append(driver)
        ba = config.get("basic_auth_user","").strip()
        if ba:
            import base64 as _b64_auth
            _auth_token = _b64_auth.b64encode(f"{ba}:{config.get('basic_auth_pass','')}".encode()).decode()
            try:
                driver.execute_cdp_cmd("Network.enable", {})
                driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Authorization": f"Basic {_auth_token}"}})
            except Exception:
                pass  # Fallback: URL embedding will still be tried
            log_cb("[INFO] Basic認証を設定 (CDP)")
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

        # Build page lookup — folders are created lazily on first use
        page_dirs = {}  # page_id -> directory path (resolved, but not yet on disk)
        save_source = config.get("save_source", "1") == "1"
        source_dirs = {}  # page_id -> _source subdirectory path
        source_root = os.path.join(outdir, "_source")
        _needed_page_ids = set(tc.get("page_id", "") for tc in test_cases)
        _page_dir_paths = {}  # page_id -> planned path (not yet created)
        if pages:
            for pg in pages:
                if pg["_id"] not in _needed_page_ids: continue
                pg_num = pg.get("number", "0")
                pg_name = _safe_filename(pg.get("name", ""), 30)
                _page_dir_paths[pg["_id"]] = os.path.join(outdir, f"{pg_num}_{pg_name}")
        def _ensure_page_dir(pid):
            """Create page output directory on first use and return its path."""
            if pid in page_dirs:
                return page_dirs[pid]
            planned = _page_dir_paths.get(pid)
            if planned:
                os.makedirs(planned, exist_ok=True)
                page_dirs[pid] = planned
                if save_source:
                    os.makedirs(source_root, exist_ok=True)
                    src_dir = os.path.join(source_root, os.path.basename(planned))
                    os.makedirs(src_dir, exist_ok=True)
                    source_dirs[pid] = src_dir
                return planned
            return outdir

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
            tc_pid = tc.get("page_id")
            tc_outdir = None  # resolved lazily on first screenshot
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
                _step_failed = False
                for si, step in enumerate(steps, 1):
                    if stop_event and stop_event.is_set(): break
                    if _step_failed and step.get("type") != "スクショ":
                        # Skip remaining steps after failure (except screenshots for evidence)
                        continue
                    st = step["type"]
                    if st in ("見出し","コメント"):
                        if st == "見出し": log_cb(f"  ## {step.get('text','')}")
                        continue
                    # iframe switching
                    if "_frame" in step:
                        try:
                            driver.switch_to.default_content()
                            fi = step.get("_frame_index", 0)
                            iframes = driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
                            if fi < len(iframes): driver.switch_to.frame(iframes[fi])
                        except Exception as fx: log_cb(f"  S{si} [WARN] iframe切替失敗: {fx}")
                    elif si > 1:
                        # Return to default content if previous step was in iframe
                        try: driver.switch_to.default_content()
                        except Exception: pass
                    if st == "入力":
                        sel = step.get("selector","")
                        iv = step.get("value","{パターン}").replace("{パターン}",value).replace("{pattern}",value)
                        input_mode = step.get("input_mode", "overwrite")
                        try:
                            e = WebDriverWait(driver,10).until(EC.presence_of_element_located((By.CSS_SELECTOR,sel)))
                            driver.execute_script("arguments[0].scrollIntoView({block:'center',behavior:'instant'});", e)
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
                        except Exception as x:
                            log_cb(f"  S{si} [WARN] 入力失敗: {x}")
                            _step_failed = True
                    elif st == "クリック":
                        sel = step.get("selector","").replace("{パターン}",value).replace("{pattern}",value)
                        try:
                            _el = WebDriverWait(driver,10).until(EC.element_to_be_clickable((By.CSS_SELECTOR,sel)))
                            driver.execute_script("arguments[0].scrollIntoView({block:'center',behavior:'instant'});", _el)
                            _el.click()
                            log_cb(f"  S{si} クリック: {sel}")
                        except Exception as x:
                            log_cb(f"  S{si} [WARN] クリック失敗: {x}")
                            _step_failed = True
                    elif st == "選択":
                        sel = step.get("selector","")
                        sv = step.get("value","").replace("{パターン}",value).replace("{pattern}",value)
                        try:
                            el = WebDriverWait(driver,10).until(EC.presence_of_element_located((By.CSS_SELECTOR,sel)))
                            driver.execute_script("arguments[0].scrollIntoView({block:'center',behavior:'instant'});", el)
                            dd = SeleniumSelect(el)
                            try: dd.select_by_value(sv)
                            except Exception: dd.select_by_visible_text(sv)
                            log_cb(f"  S{si} 選択: {sel} -> {sv}")
                        except Exception as x:
                            log_cb(f"  S{si} [WARN] 選択失敗: {x}")
                            _step_failed = True
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
                    elif st == "スクロール":
                        sm = step.get("scroll_mode", "element")
                        try:
                            if sm == "top":
                                driver.execute_script("window.scrollTo(0,0);")
                                log_cb(f"  S{si} スクロール: 先頭")
                            elif sm == "pixel":
                                px = int(step.get("scroll_px", "0"))
                                driver.execute_script(f"window.scrollTo(0,{px});")
                                log_cb(f"  S{si} スクロール: {px}px")
                            else:
                                sel = step.get("selector","")
                                el = WebDriverWait(driver,10).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                                driver.execute_script("arguments[0].scrollIntoView({block:'center',behavior:'instant'});", el)
                                log_cb(f"  S{si} スクロール: {sel}")
                            time.sleep(0.3)
                        except Exception as x: log_cb(f"  S{si} [WARN] スクロール失敗: {x}")
                    elif st == "待機":
                        s = float(step.get("seconds","1.0")); time.sleep(s); log_cb(f"  S{si} 待機: {s}秒")
                    elif st == "要素待機":
                        sel = step.get("selector","")
                        timeout = float(step.get("seconds","10"))
                        try:
                            WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                            log_cb(f"  S{si} 要素待機OK: {sel}")
                        except Exception as x:
                            log_cb(f"  S{si} [WARN] 要素待機タイムアウト({timeout}秒): {sel}")
                    elif st == "スクショ":
                        # Flash effect (brief white overlay before capture)
                        try:
                            driver.execute_script(
                                "var f=document.createElement('div');f.id='__yshot_flash';"
                                "f.style.cssText='position:fixed;top:0;left:0;width:100%;height:100%;"
                                "background:white;opacity:0.7;z-index:2147483647;pointer-events:none;';"
                                "document.body.appendChild(f);"
                                "setTimeout(function(){var x=document.getElementById('__yshot_flash');if(x)x.remove();},150);")
                            time.sleep(0.2)
                        except Exception: pass
                        sc += 1; gss += 1; mode = step.get("mode","fullpage"); sel = step.get("selector","")
                        if tc_outdir is None: tc_outdir = _ensure_page_dir(tc_pid)
                        safe_tc = _safe_filename(tc_name, 20)
                        safe_number = _safe_filename(tc_number, 10) if tc_number else ""
                        num_prefix = f"{safe_number}_" if safe_number else ""
                        if len(pats) > 1:
                            safe_label = _safe_filename(label, 30)
                            fn = f"{gss:03d}_{num_prefix}{safe_tc}_{safe_label}_ss{sc}.png"
                        else:
                            fn = f"{gss:03d}_{num_prefix}{safe_tc}_ss{sc}.png"
                        fp = os.path.join(tc_outdir, fn)
                        try:
                            if mode == "element" and sel:
                                driver.find_element(By.CSS_SELECTOR, sel).screenshot(fp)
                            elif mode == "margin" and sel:
                                mg = int(step.get("margin_px",500))
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
                                        actual_h = min(total_h, 16384)
                                        if total_h > 16384:
                                            log_cb(f"  S{si} [WARN] ページ高さ{total_h}px > 上限16384px。画像が切れます")
                                        driver.set_window_size(max(total_w, 1280), actual_h)
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
                    progress_cb(done_pats, total_pats, f"{tc_number} {tc_name}")

        if stop_event and stop_event.is_set():
            log_cb(f"\n[中断完了] -> {outdir}")
        else:
            log_cb(f"\n[全完了] {len(test_cases)} テスト -> {outdir}")
        _used_pages = [pg for pg in (pages or []) if pg["_id"] in page_dirs]
        _generate_report(outdir, log_cb, pages=_used_pages)
        _generate_excel_report(outdir, log_cb, pages=_used_pages, test_cases=test_cases, run_label=run_label)
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
def _safe_json_save(filepath, data):
    """Atomic JSON save: write to .tmp, backup old file, then rename."""
    tmp = filepath + ".tmp"
    bak = filepath + ".backup"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if os.path.isfile(filepath):
        try: os.replace(filepath, bak)
        except Exception: pass
    os.replace(tmp, filepath)

def _safe_json_load(filepath, default):
    """Load JSON with backup recovery on corruption."""
    for p in [filepath, filepath + ".backup"]:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, Exception):
                continue
    return default

def load_tests():
    return _safe_json_load(_data_path(TESTS_FILE), [])
def save_tests(tests):
    _safe_json_save(_data_path(TESTS_FILE), tests)
def load_pattern_sets():
    return _safe_json_load(_data_path(PATTERNS_FILE), {})
def save_pattern_sets(ps):
    _safe_json_save(_data_path(PATTERNS_FILE), ps)
def load_selector_bank():
    return _safe_json_load(_data_path(SELECTOR_BANK_FILE), {})
def save_selector_bank(bank):
    _safe_json_save(_data_path(SELECTOR_BANK_FILE), bank)
def load_pages():
    return _safe_json_load(_data_path(PAGES_FILE), [])
def save_pages(pages):
    _safe_json_save(_data_path(PAGES_FILE), pages)
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
    # Set window icon to ebi
    _icon_path = os.path.join(get_bundle_dir(), "assets", "shot_icon.ico")
    if not os.path.isfile(_icon_path): _icon_path = os.path.join(get_app_dir(), "assets", "shot_icon.ico")
    if os.path.isfile(_icon_path):
        try: page.window.icon = _icon_path
        except Exception: pass
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
        "stop_event": None, "test_drivers": [], "running": False,
        "selected_test_per_page": {},
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
        if "[ERROR]" in msg: color = ft.Colors.RED_600
        elif "[WARN]" in msg: color = ft.Colors.ORANGE_700
        else: color = ft.Colors.GREY_700
        log_list.controls.append(ft.Text(f"[{ts}] {msg}", size=11, selectable=True, font_family="Consolas", color=color))
        if len(log_list.controls) > 400: log_list.controls.pop(0)
        try: page.update()
        except Exception: pass
    def _log_error(context, exc):
        _flog.error(f"{context}: {exc}\n{traceback.format_exc()}")
        log(f"[ERROR] {context}: {exc}")
    def _guard_running():
        """Return True and show snack if tests are running (blocks editing)."""
        if state["running"]:
            snack("テスト実行中は編集できません", ft.Colors.ORANGE_700)
            return True
        return False
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
        # Restore remembered test selection for this page
        remembered_id = state["selected_test_per_page"].get(page_dd.value, "")
        state["selected_test"] = -1
        if remembered_id:
            for i, tc in enumerate(state["tests"]):
                if tc.get("_id") == remembered_id:
                    state["selected_test"] = i; break
        refresh_page_dd(False); refresh_test_list(False); refresh_steps(False)
        # Auto-sync browser URL to selected page
        pg = cur_page()
        if pg and pg.get("url", ""):
            try: browser_url.value = pg["url"]
            except NameError: pass
        page.update()

    def add_page(e):
        if _guard_running(): return
        next_num = str(len(state["pages"]) + 1)
        nf = ft.TextField(label="ページ名", width=350, value=f"ページ{next_num}")
        url_f = ft.TextField(label="起点URL", width=450, hint_text="このページの起点URL")
        numf = ft.TextField(label="ページ番号", width=100, value=next_num)
        startf = ft.TextField(label="テスト開始番号", width=100, value="1", hint_text="この番号から連番")
        def on_ok(e):
            try:
                name = nf.value.strip(); num = numf.value.strip()
                if not name: snack("名前入力", ft.Colors.RED_700); return
                if not num: snack("番号入力", ft.Colors.RED_700); return
                if any(p["number"] == num for p in state["pages"]):
                    snack(f"番号 {num} は既に使用されています", ft.Colors.RED_700); return
                try: start = int(startf.value.strip() or "1")
                except ValueError: snack("開始番号は整数で", ft.Colors.RED_700); return
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
        if _guard_running(): return
        pg = cur_page()
        if not pg: snack("ページを選択してください", ft.Colors.ORANGE_700); return
        nf = ft.TextField(label="ページ名", width=350, value=pg["name"])
        url_f = ft.TextField(label="起点URL", width=450, value=pg.get("url",""), hint_text="このページの起点URL")
        numf = ft.TextField(label="ページ番号", width=100, value=pg["number"])
        startf = ft.TextField(label="テスト開始番号", width=100, value=str(pg.get("start_number", 1)))
        def on_ok(e):
            try:
                name = nf.value.strip(); num = numf.value.strip()
                if not name: snack("名前入力", ft.Colors.RED_700); return
                if not num: snack("番号入力", ft.Colors.RED_700); return
                if num != pg["number"] and any(p["number"] == num for p in state["pages"]):
                    snack(f"番号 {num} は既に使用されています", ft.Colors.RED_700); return
                try: start = int(startf.value.strip() or "1")
                except ValueError: snack("開始番号は整数で", ft.Colors.RED_700); return
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
        if _guard_running(): return
        if len(state["pages"]) <= 1:
            snack("最後のページは削除できません", ft.Colors.RED_700); return
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
        has_any_url = any(p.get("url","").strip() for p in state["pages"]) or any(t.get("url","").strip() for t in state["tests"])
        has_tests = len(state["tests"]) > 0
        run_btn.disabled = not (has_any_url and has_tests)
        run_single_btn.disabled = not (has_any_url and has_tests)
        run_page_btn.disabled = not (has_any_url and page_tests)
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
        # Remember selection per page
        tc = state["tests"][idx]
        pid = tc.get("page_id", "")
        if pid: state["selected_test_per_page"][pid] = tc.get("_id", "")
        _update_test_highlight()
        refresh_steps(False); page.update()

    def add_test(e):
        if _guard_running(): return
        cur_pid = state["selected_page"]
        if not cur_pid: snack("ページを選択してください", ft.Colors.ORANGE_700); return
        new_tc = {"name": f"テスト{len(tests_for_page(cur_pid))+1}", "pattern": None, "steps": [],
                  "_id": _new_tc_id(), "page_id": cur_pid, "number": ""}
        state["tests"].append(new_tc); auto_number_tests()
        state["selected_test"] = len(state["tests"]) - 1
        refresh_page_dd(False); refresh_test_list(False); refresh_steps()

    def copy_test(idx):
        if _guard_running(): return
        if 0 <= idx < len(state["tests"]):
            tc = copy.deepcopy(state["tests"][idx])
            tc["name"] += " (コピー)"; tc["_id"] = _new_tc_id(); tc.pop("_sub_number", None)
            state["tests"].insert(idx + 1, tc); auto_number_tests()
            state["selected_test"] = idx + 1
            refresh_page_dd(False); refresh_test_list(False); refresh_steps()

    def del_test(idx):
        if _guard_running(): return
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
        if _guard_running(): return
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
                        snack("枝番は整数で入力してください", ft.Colors.RED_700); return
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
                    ft.Text(t, size=10, color=ft.Colors.GREY_500, width=38),
                    ft.Text(step_short(s), size=11, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, tooltip=step_short(s)),
                    ft.IconButton(ft.Icons.EDIT, icon_size=14, on_click=lambda e, idx=i: show_step_dlg(idx)),
                    ft.IconButton(ft.Icons.DELETE, icon_size=14, on_click=lambda e, idx=i: del_step(idx)),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(8,2,36,2), key=key, height=28))
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
        if _guard_running(): return
        tc = cur_test()
        if not tc or not (0 <= idx < len(tc["steps"])): return
        step = tc["steps"][idx]
        label = step_short(step)
        if len(label) > 30: label = label[:27] + "..."
        def on_yes(e):
            tc["steps"].pop(idx)
            state["collapsed"] = {c if c < idx else c-1 for c in state["collapsed"] if c != idx}
            refresh_steps(); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("ステップ削除"),
            content=ft.Text(f"「{step['type']}: {label}」を削除しますか？"),
            actions=[ft.TextButton("削除", on_click=on_yes, style=ft.ButtonStyle(color=ft.Colors.RED_600)),
                     ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def show_step_dlg(idx):
        if _guard_running(): return
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
        margin_f = ft.TextField(label="マージン(px)", width=120, value=init.get("margin_px","500"))
        text_f = ft.TextField(label="テキスト", width=450, value=init.get("text",""), multiline=True, min_lines=1, max_lines=3)
        # Scroll controls
        scroll_mode_dd = ft.Dropdown(label="スクロール方法", width=220, value=init.get("scroll_mode","element"),
            options=[ft.dropdown.Option(key=k, text=t) for k, t in SCROLL_MODES])
        scroll_px_f = ft.TextField(label="位置(px)", width=120, value=init.get("scroll_px","0"), hint_text="上端からのpx")
        # Groups must be defined BEFORE upd() references them
        input_group = ft.Column([sel_field, input_mode_dd, val_mode, val_field], spacing=8, tight=True)
        nav_group = ft.Column([nav_url_f], spacing=8, tight=True)
        time_group = ft.Column([sec_field], spacing=8, tight=True)
        ss_group = ft.Column([ft.Row([mode_dd, margin_f], spacing=8)], spacing=8, tight=True)
        scroll_group = ft.Column([ft.Row([scroll_mode_dd, scroll_px_f], spacing=8)], spacing=8, tight=True)
        text_group = ft.Column([text_f], spacing=8, tight=True)
        def upd(e=None):
            try:
                t = type_dd.value
                is_input = (t == "入力")
                needs_sel = t in ("入力","クリック","選択","要素待機") or (t=="スクショ" and mode_dd.value in ("element","margin")) or (t=="スクロール" and scroll_mode_dd.value=="element")
                sel_field.visible = needs_sel
                input_mode_dd.visible = is_input
                val_mode.visible = is_input or t == "選択"
                val_field.visible = (is_input or t == "選択") and val_mode.value == "手入力"
                if is_input and input_mode_dd.value == "clear":
                    val_mode.visible = False; val_field.visible = False
                nav_url_f.visible = (t == "ナビゲーション")
                sec_field.visible = t in ("待機", "戻る", "要素待機"); mode_dd.visible = (t=="スクショ")
                scroll_mode_dd.visible = (t == "スクロール")
                scroll_px_f.visible = (t == "スクロール" and scroll_mode_dd.value == "pixel")
                if t == "要素待機": sec_field.label = "タイムアウト(秒)"
                else: sec_field.label = "秒数"
                margin_f.visible = (t=="スクショ" and mode_dd.value=="margin")
                text_f.visible = t in ("見出し","コメント")
                if t == "選択": val_mode.label = "選択肢の指定方法"
                else: val_mode.label = "値の指定方法"
                # Hide empty groups entirely
                input_group.visible = needs_sel or is_input or t == "選択"
                nav_group.visible = (t == "ナビゲーション")
                time_group.visible = t in ("待機", "戻る", "要素待機")
                ss_group.visible = (t == "スクショ")
                scroll_group.visible = (t == "スクロール")
                text_group.visible = t in ("見出し","コメント")
                try: page.update()
                except Exception: pass
            except Exception as x: _log_error("show_step_dlg.upd", x)
        type_dd.on_select = upd; mode_dd.on_select = upd; val_mode.on_select = upd; input_mode_dd.on_select = upd; scroll_mode_dd.on_select = upd
        # 初期表示を正しく設定
        upd()
        def on_ok(e):
            try:
                t = type_dd.value; step = {"type": t}
                if t in ("見出し","コメント"): step["text"] = text_f.value
                elif t in ("入力","クリック","選択"):
                    s = sel_field.value if hasattr(sel_field,'value') else ""
                    if not s: snack("セレクタを入力", ft.Colors.RED_700); return
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
                    except Exception: snack("秒数を正しく", ft.Colors.RED_700); return
                elif t == "ナビゲーション":
                    url = nav_url_f.value.strip()
                    if not url: snack("URLを入力", ft.Colors.RED_700); return
                    step["url"] = url
                elif t == "待機":
                    try: step["seconds"] = str(float(sec_field.value))
                    except Exception: snack("秒数を正しく", ft.Colors.RED_700); return
                elif t == "要素待機":
                    s = sel_field.value if hasattr(sel_field,'value') else ""
                    if not s: snack("セレクタを入力", ft.Colors.RED_700); return
                    step["selector"] = s
                    try: step["seconds"] = str(float(sec_field.value or "10"))
                    except Exception: snack("秒数を正しく", ft.Colors.RED_700); return
                elif t == "スクロール":
                    step["scroll_mode"] = scroll_mode_dd.value
                    if scroll_mode_dd.value == "element":
                        s = sel_field.value if hasattr(sel_field,'value') else ""
                        if not s: snack("セレクタを入力", ft.Colors.RED_700); return
                        step["selector"] = s
                    elif scroll_mode_dd.value == "pixel":
                        try: step["scroll_px"] = str(int(scroll_px_f.value or "0"))
                        except Exception: snack("整数で入力", ft.Colors.RED_700); return
                elif t == "スクショ":
                    step["mode"] = mode_dd.value
                    s = sel_field.value if hasattr(sel_field,'value') else ""
                    if mode_dd.value in ("element","margin") and not s: snack("セレクタ必要", ft.Colors.RED_700); return
                    if s: step["selector"] = s
                    if mode_dd.value == "margin":
                        try: step["margin_px"] = str(int(margin_f.value))
                        except Exception: snack("整数で", ft.Colors.RED_700); return
                if idx is not None: tc["steps"][idx] = step
                else: tc["steps"].append(step)
                refresh_steps(False); refresh_test_list(); close_dlg(dlg)
            except Exception as x: _log_error("show_step_dlg.on_ok", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("ステップ編集" if idx is not None else "ステップ追加"),
            content=ft.Column([type_dd, text_group, input_group, nav_group, time_group, scroll_group, ss_group],
                tight=True, spacing=12, scroll=ft.ScrollMode.AUTO, width=500),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    # ── Element browser ──
    def _el_loading_start(msg="読込中..."):
        el_loading.visible = True; load_btn.disabled = True
        el_status.value = msg; el_status.color = ft.Colors.BLUE_600
        page.update()
    def _el_loading_end(msg="", color=ft.Colors.GREY_500):
        el_loading.visible = False; load_btn.disabled = False
        if msg: el_status.value = msg; el_status.color = color
        page.update()
    def load_page_click(e):
        url = browser_url.value
        if not url: snack("URL入力", ft.Colors.RED_700); return
        _el_loading_start("ブラウザ起動中...")
        page.run_thread(do_load_page, url)
    def do_load_page(url):
        try:
            from selenium import webdriver
            if state["browser_driver"] is None:
                _br_opts = webdriver.ChromeOptions()
                _br_opts.add_argument("--ignore-certificate-errors")
                _br_opts.add_argument("--allow-insecure-localhost")
                _br_opts.add_argument("--disable-features=HttpsUpgrades")
                state["browser_driver"] = webdriver.Chrome(options=_br_opts); state["browser_driver"].set_window_size(1280,900)
            ba = state["config"].get("basic_auth_user","").strip()
            if ba:
                import base64 as _b64_ba
                _auth_tok = _b64_ba.b64encode(f"{ba}:{state['config'].get('basic_auth_pass','')}".encode()).decode()
                try:
                    state["browser_driver"].execute_cdp_cmd("Network.enable", {})
                    state["browser_driver"].execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Authorization": f"Basic {_auth_tok}"}})
                except Exception: pass
            el_status.value = "ページ読込中..."; page.update()
            lu = build_auth_url(url, ba, state["config"].get("basic_auth_pass","")) if ba else url
            state["browser_driver"].get(lu)
            try: w = float(browser_wait.value)
            except Exception: w = 3.0
            time.sleep(w); log(f"[DEBUG] {state['browser_driver'].title}")
            el_status.value = "要素を収集中..."; page.update()
            _do_collect_elements(url)
        except Exception as x:
            if state["browser_driver"]:
                try: state["browser_driver"].title
                except Exception:
                    kill_driver(state["browser_driver"]); state["browser_driver"] = None
            log(f"[ERROR] {x}")
        finally: _el_loading_end()
    def _do_collect_elements(url=None):
        """Collect elements from current DOM state (no page navigation)."""
        drv = state["browser_driver"]
        elems = collect_elements_python(drv, include_hidden=True)
        # Detect iframes and collect their elements too
        from selenium.webdriver.common.by import By
        try:
            iframes = drv.find_elements(By.CSS_SELECTOR, "iframe, frame")
            for fi, iframe in enumerate(iframes):
                frame_id = iframe.get_attribute("id") or iframe.get_attribute("name") or f"frame_{fi}"
                try:
                    drv.switch_to.frame(iframe)
                    frame_elems = collect_elements_python(drv, include_hidden=True)
                    for fe in frame_elems:
                        fe["hint"] = f"[iframe:{frame_id}] " + fe.get("hint", "")
                        fe["_frame"] = frame_id
                        fe["_frame_index"] = fi
                    elems.extend(frame_elems)
                    drv.switch_to.default_content()
                except Exception:
                    try: drv.switch_to.default_content()
                    except Exception: pass
        except Exception: pass
        state["browser_elements"] = list(elems)
        if url:
            bank = state["selector_bank"]
            bank[url.split("?")[0]] = [el for el in elems if el.get("visible", True)]
            # A4: LRU limit — keep only newest 50 URLs
            _BANK_MAX = 50
            if len(bank) > _BANK_MAX:
                keys = list(bank.keys())
                for old_key in keys[:len(keys) - _BANK_MAX]:
                    del bank[old_key]
        filter_el_table(); update_url_dd()
        log(f"[要素] DOM再取得 {len(elems)} 要素")
    def reload_dom_click(e):
        """Re-collect elements from current DOM without navigating."""
        if not state["browser_driver"]: snack("ブラウザ未起動", ft.Colors.ORANGE_700); return
        _el_loading_start("DOM再取得中...")
        try:
            _do_collect_elements()
        except Exception as x:
            log(f"[ERROR] DOM再取得失敗: {x}")
        finally: _el_loading_end()
    def on_el_sort_change(e):
        filter_el_table()

    def filter_el_table(update=True):
        """Filter and display elements based on search text, hidden visibility, and sort."""
        el_table.rows.clear()
        query = (el_search.value or "").strip().lower()
        show_hidden = el_show_hidden.value
        visible_count = 0
        total_count = len(state["browser_elements"])
        hidden_count = sum(1 for el in state["browser_elements"] if not el.get("visible", True))
        # Build sorted index
        sort_key = "dom"
        try: sort_key = el_sort_dd.value or "dom"
        except NameError: pass
        indexed_els = list(enumerate(state["browser_elements"]))
        if sort_key == "tag":
            indexed_els.sort(key=lambda x: (x[1].get("tag",""), x[1].get("type","")))
        elif sort_key == "type":
            indexed_els.sort(key=lambda x: (x[1].get("type",""), x[1].get("tag","")))
        elif sort_key == "id":
            indexed_els.sort(key=lambda x: (x[1].get("id","") or x[1].get("name","") or "zzz"))
        for i, el in indexed_els:
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
            reason = el.get("hidden_reason", "")
            vis_indicator = "" if is_visible else f" [{reason}]" if reason else " [hidden]"
            is_selected = (i == state["selected_el"])
            el_table.rows.append(ft.DataRow(
                cells=[ft.DataCell(ft.Text(el["tag"],size=11)),
                       ft.DataCell(ft.Text(el.get("type",""),size=11)),
                       ft.DataCell(ft.Text(el.get("id") or el.get("name",""),size=11)),
                       ft.DataCell(ft.Text((el.get("hint","")[:20]) + vis_indicator,size=11,
                                           color=ft.Colors.ORANGE_700 if not is_visible else None)),
                       ft.DataCell(ft.Text(el["selector"],size=10,color=ft.Colors.GREY_600))],
                on_select_change=lambda e, idx=i: on_el_click(idx),
                selected=is_selected,
                color=row_color))
        status_parts = [f"{visible_count}/{total_count} 要素"]
        if hidden_count > 0:
            status_parts.append(f"(非表示: {hidden_count})")
        if query:
            status_parts.append(f"検索: \"{el_search.value}\"")
        el_status.value = " ".join(status_parts); el_status.color = ft.Colors.GREY_500
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
            try:
                result_json = state["browser_driver"].execute_script(HIGHLIGHT_JS, el["selector"])
                if result_json:
                    import json as _json
                    info = _json.loads(result_json)
                    found = info.get("found", 0)
                    if found == 0:
                        el_status.value = f"セレクタ不一致: {el['selector']}"
                    elif found > 1:
                        el_status.value = f"セレクタ {found}件一致（曖昧）: {el['selector']}"
                    else:
                        el_status.value = f"一致: {el['selector']} ({info.get('tag','')})"
            except Exception:
                pass
        # Also update selector test field with the selected selector
        try: sel_test_field.value = el["selector"] if el else ""
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
        if not tc: snack("テストケースを選択", ft.Colors.ORANGE_700); return
        idx = state["selected_el"]
        if idx < 0 or idx >= len(state["browser_elements"]): snack("要素をクリック", ft.Colors.ORANGE_700); return
        el_info = state["browser_elements"][idx]; sel = el_info["selector"]
        tag = el_info.get("tag", ""); etype = el_info.get("type", "").lower()
        actual_type = stype
        if tag == "select": actual_type = "選択"
        elif etype in ("radio", "checkbox"): actual_type = "クリック"
        elif tag in ("button", "a") or etype in ("submit", "button", "reset", "image"): actual_type = "クリック"
        converted = actual_type != stype
        step = {"type": actual_type, "selector": sel}
        if "_frame" in el_info: step["_frame"] = el_info["_frame"]; step["_frame_index"] = el_info.get("_frame_index", 0)
        if actual_type in ("入力", "選択"): step["value"] = "{パターン}"
        tc["steps"].append(step); refresh_steps(False); refresh_test_list()
        if converted:
            snack(f"要素に合わせて「{actual_type}」に変更: {sel}", ft.Colors.BLUE_600)
        else:
            snack(f"{actual_type}: {sel}")
    def quick_add_all_options(e):
        if not state["browser_driver"]: snack("ページ読込必要", ft.Colors.ORANGE_700); return
        idx = state["selected_el"]
        if idx < 0 or idx >= len(state["browser_elements"]): snack("要素をクリック", ft.Colors.ORANGE_700); return
        el_info = state["browser_elements"][idx]; tag = el_info.get("tag", ""); etype = el_info.get("type", "").lower()
        if tag != "select" and etype != "radio": snack("セレクトボックスまたはラジオボタンを選択", ft.Colors.ORANGE_700); return
        step_type, options = collect_element_options(state["browser_driver"], el_info)
        if not options: snack("選択肢が取得できませんでした", ft.Colors.RED_700); return
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
        if not tc: snack("テストケースを選択", ft.Colors.ORANGE_700); return
        if not state["browser_driver"]: snack("ページ読込必要", ft.Colors.ORANGE_700); return
        try:
            fs = capture_form_values(state["browser_driver"])
            if not fs: snack("フォーム値なし", ft.Colors.ORANGE_700); return
            tc["steps"].extend(fs); refresh_steps(False); refresh_test_list(); snack(f"フォーム値 {len(fs)} 件")
        except Exception as x: log(f"[ERROR] {x}")
    def test_selector_click(e):
        """Test a CSS selector by highlighting the matched element in the browser."""
        if not state["browser_driver"]: snack("ブラウザ未起動", ft.Colors.ORANGE_700); return
        sel_to_test = (sel_test_field.value or "").strip()
        if not sel_to_test: snack("セレクタを入力してください", ft.Colors.ORANGE_700); return
        try:
            from selenium.webdriver.common.by import By
            matches = state["browser_driver"].find_elements(By.CSS_SELECTOR, sel_to_test)
            if not matches:
                snack(f"該当なし: {sel_to_test}", ft.Colors.RED_700)
            else:
                state["browser_driver"].execute_script(HIGHLIGHT_JS, sel_to_test)
                snack(f"一致: {len(matches)} 要素", ft.Colors.GREEN_700 if len(matches) == 1 else ft.Colors.ORANGE_700)
        except Exception as x:
            snack(f"セレクタエラー: {x}", ft.Colors.RED_700)
    def close_br(e):
        close_browser(); el_table.rows.clear(); state["browser_elements"].clear()
        el_status.value = "未読込"; el_status.color = ft.Colors.GREY_500; page.update()
    def sync_url(e):
        pg = cur_page()
        browser_url.value = pg.get("url", "") if pg else ""
        page.update()

    # ================================================================
    # Tab 2: Pattern Sets
    # ================================================================
    def on_ps_search_change(e):
        refresh_pat_set_list()

    def refresh_pat_set_list(update=True):
        pat_set_list.controls.clear()
        ps_query = ""
        try: ps_query = (ps_search.value or "").strip().lower()
        except NameError: pass
        if not state["pattern_sets"]:
            pat_set_list.controls.append(ft.Container(
                ft.Column([ft.Icon(ft.Icons.ADD_CIRCLE_OUTLINE, size=28, color=ft.Colors.GREY_400),
                    ft.Text("＋ボタンでパターンセットを追加", size=11, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                padding=ft.Padding(16, 30, 16, 16), key="empty_ps"))
        for name in state["pattern_sets"].keys():
            if ps_query and ps_query not in name.lower(): continue
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
        if _guard_running(): return
        nf = ft.TextField(label="パターンセット名", width=300)
        def on_ok(e):
            try:
                n = nf.value.strip()
                if not n: snack("名前入力", ft.Colors.RED_700); return
                if n in state["pattern_sets"]: snack("既に存在", ft.Colors.RED_700); return
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
                if not new_name: snack("名前入力", ft.Colors.RED_700); return
                if new_name != old_name and new_name in state["pattern_sets"]: snack("既に存在", ft.Colors.RED_700); return
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
        if _guard_running(): return
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
        if _guard_running(): return
        name = state["selected_pat_set"]
        if not name: return
        edit_pat(None)

    def edit_pat(idx):
        if _guard_running(): return
        name = state["selected_pat_set"]
        if not name: return
        pats = state["pattern_sets"][name]
        init = pats[idx] if idx is not None else {}
        lf = ft.TextField(label="ラベル", width=400, value=init.get("label",""))
        vf = ft.TextField(label="入力値", width=400, value=init.get("value",""), multiline=True, min_lines=3, max_lines=6)
        def on_ok(e):
            try:
                if not lf.value: snack("ラベル入力", ft.Colors.RED_700); return
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
        if _guard_running(): return
        name = state["selected_pat_set"]
        if not name or name not in state["pattern_sets"]: return
        pats = state["pattern_sets"][name]
        if not (0 <= idx < len(pats)): return
        pat = pats[idx]
        label = pat.get("label", f"パターン{idx+1}")
        def on_yes(e):
            pats.pop(idx); refresh_pats(False); refresh_pat_set_list(False); refresh_test_list(); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("パターン削除"),
            content=ft.Text(f"「{label}」を削除しますか？"),
            actions=[ft.TextButton("削除", on_click=on_yes, style=ft.ButtonStyle(color=ft.Colors.RED_600)),
                     ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    def export_csv(e):
        name = state["selected_pat_set"]
        if not name or name not in state["pattern_sets"]: snack("パターンセットを選択", ft.Colors.ORANGE_700); return
        pats = state["pattern_sets"][name]
        if not pats: snack("パターンなし", ft.Colors.ORANGE_700); return
        outdir = state["config"].get("output_dir", os.path.join(get_app_dir(), "screenshots"))
        os.makedirs(outdir, exist_ok=True)
        fp = os.path.join(outdir, f"{_safe_filename(name, 50)}.csv")
        save_csv(fp, pats); snack(f"エクスポート: {fp}")

    def load_template(e):
        name = state["selected_pat_set"]
        if not name: snack("パターンセットを選択", ft.Colors.ORANGE_700); return
        td = get_templates_dir()
        csvs = sorted([f for f in os.listdir(td) if f.lower().endswith(".csv")]) if td else []
        csv_cache = {f: load_csv(os.path.join(td, f)) for f in csvs} if td else {}
        def on_sel(fn):
            try:
                state["pattern_sets"][name].extend(csv_cache[fn])
                refresh_pats(False); refresh_pat_set_list(False); refresh_test_list()
                snack(f"{len(csv_cache[fn])} 件追加"); close_dlg(dlg)
            except Exception as x: _log_error("load_template", x); close_dlg(dlg)
        def on_import_csv(e):
            try:
                fp = csv_path_f.value.strip()
                if not fp or not os.path.isfile(fp):
                    snack("ファイルが見つかりません", ft.Colors.RED_700); return
                rows = load_csv(fp)
                if not rows: snack("データなし（label,value ヘッダが必要）", ft.Colors.RED_700); return
                state["pattern_sets"][name].extend(rows)
                refresh_pats(False); refresh_pat_set_list(False); refresh_test_list()
                snack(f"{len(rows)} 件インポート"); close_dlg(dlg)
            except Exception as x: _log_error("import_csv", x); snack(f"インポート失敗: {x}", ft.Colors.RED_600)
        csv_path_f = ft.TextField(label="CSVファイルパス", width=380, hint_text="label,value 形式のCSV", dense=True)
        cards = [ft.Card(ft.Container(ft.Column([
            ft.Text(os.path.splitext(f)[0], weight=ft.FontWeight.BOLD, size=13),
            ft.Text(f"{len(csv_cache[f])} 件", size=11, color=ft.Colors.GREY_600)], spacing=2),
            padding=12, on_click=lambda e, fn=f: on_sel(fn)), elevation=2) for f in csvs]
        content_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, width=420, tight=True)
        content_col.controls.append(ft.Text("CSVファイルから直接インポート:", size=12, weight=ft.FontWeight.BOLD))
        content_col.controls.append(ft.Row([csv_path_f, ft.TextButton("読込", on_click=on_import_csv)], spacing=4))
        if cards:
            content_col.controls.append(ft.Divider())
            content_col.controls.append(ft.Text("テンプレート:", size=12, weight=ft.FontWeight.BOLD))
            content_col.controls.extend(cards)
        dlg = ft.AlertDialog(title=ft.Text("テンプレート / CSVインポート"),
            content=content_col,
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
                if not ml or not ml.isdigit() or int(ml) < 1: snack("max_lengthを正の整数で", ft.Colors.RED_700); return
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
                if not ml or not ml.isdigit() or int(ml) < 1: snack("max_lengthを正の整数で", ft.Colors.RED_700); return
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
                state["config"].pop("url", None)  # 旧グローバルURL設定を除去
                save_config(state["config"]); snack("設定保存")
                refresh_test_list(False); page.update(); close_dlg(dlg)
            except Exception as x: _log_error("show_settings", x); close_dlg(dlg)
        dlg = ft.AlertDialog(title=ft.Text("設定"),
            content=ft.Column([ft.Row([auf, apf], spacing=10), of, hl, ss], tight=True, spacing=12, width=500),
            actions=[ft.TextButton("OK", on_click=on_ok), ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
        open_dlg(dlg)

    # ── Project Export / Import ──
    def export_project(e):
        """Export pages, tests, and pattern sets as a single JSON project file."""
        try:
            save_all()
            project_data = {
                "app": APP_NAME, "version": APP_VERSION,
                "pages": state["pages"],
                "tests": state["tests"],
                "pattern_sets": state["pattern_sets"],
            }
            outdir = state["config"].get("output_dir", os.path.join(get_app_dir(), "screenshots"))
            os.makedirs(outdir, exist_ok=True)
            # Build default filename from first page name
            first_name = state["pages"][0]["name"] if state["pages"] else "project"
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            fp = os.path.join(outdir, f"{_safe_filename(first_name, 30)}_{ts}.yshot.json")
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)
            snack(f"エクスポート: {fp}")
            log(f"[プロジェクト] エクスポート: {fp}")
        except Exception as x:
            _log_error("export_project", x); snack(f"エクスポート失敗: {x}", ft.Colors.RED_600)

    def import_project(e):
        """Import a .yshot.json project file via file picker dialog."""
        # Scan for available project files
        search_dirs = [
            state["config"].get("output_dir", os.path.join(get_app_dir(), "screenshots")),
            get_app_dir(),
        ]
        found_files = []
        for d in search_dirs:
            if not os.path.isdir(d): continue
            for fn in os.listdir(d):
                if fn.endswith(".yshot.json"):
                    fp = os.path.join(d, fn)
                    found_files.append(fp)
        found_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

        path_field = ft.TextField(label="ファイルパス", width=450, hint_text=".yshot.json ファイルのパスを入力",
                                  value=found_files[0] if found_files else "")
        mode_dd = ft.Dropdown(label="インポート方法", width=250, value="replace",
            options=[ft.dropdown.Option(key="replace", text="置換（現在のデータを上書き）"),
                     ft.dropdown.Option(key="merge", text="マージ（現在のデータに追加）")])
        file_list_col = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, height=150)
        if found_files:
            for fp in found_files[:10]:
                fn = os.path.basename(fp)
                file_list_col.controls.append(
                    ft.TextButton(fn, on_click=lambda e, p=fp: _set_path(p), tooltip=fp))
        else:
            file_list_col.controls.append(ft.Text("検出されたプロジェクトファイルなし", size=11, color=ft.Colors.GREY_500))

        def _set_path(p):
            path_field.value = p; page.update()

        def on_ok(e):
            try:
                fp = path_field.value.strip()
                if not fp or not os.path.isfile(fp):
                    snack("ファイルが見つかりません", ft.Colors.RED_700); return
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "pages" not in data or "tests" not in data:
                    snack("無効なプロジェクトファイルです", ft.Colors.RED_700); return

                imp_pages = data.get("pages", [])
                imp_tests = data.get("tests", [])
                imp_pats = data.get("pattern_sets", {})

                if mode_dd.value == "replace":
                    state["pages"] = imp_pages
                    state["tests"] = imp_tests
                    state["pattern_sets"] = imp_pats
                else:
                    # Merge: remap IDs to avoid collision
                    page_id_map = {}
                    for pg in imp_pages:
                        old_id = pg["_id"]
                        new_id = _new_page_id()
                        pg["_id"] = new_id
                        page_id_map[old_id] = new_id
                    for tc in imp_tests:
                        tc["_id"] = _new_tc_id()
                        old_pid = tc.get("page_id", "")
                        if old_pid in page_id_map:
                            tc["page_id"] = page_id_map[old_pid]
                    state["pages"].extend(imp_pages)
                    state["tests"].extend(imp_tests)
                    for k, v in imp_pats.items():
                        if k in state["pattern_sets"]:
                            # Avoid overwrite: rename
                            new_k = f"{k}_imported"
                            n = 2
                            while new_k in state["pattern_sets"]:
                                new_k = f"{k}_imported_{n}"; n += 1
                            state["pattern_sets"][new_k] = v
                        else:
                            state["pattern_sets"][k] = v

                # Re-init ID counters
                _max_id = 0
                for tc in state["tests"]:
                    try: _max_id = max(_max_id, int(tc["_id"].split("_", 1)[1]))
                    except (ValueError, IndexError): pass
                state["_tc_id_counter"] = _max_id
                _max_pg = 0
                for pg in state["pages"]:
                    try: _max_pg = max(_max_pg, int(pg["_id"].split("_", 1)[1]))
                    except (ValueError, IndexError): pass
                state["_page_id_counter"] = _max_pg

                if not state["pages"]:
                    state["pages"].append({"_id": _new_page_id(), "name": "ページ1", "number": "1", "start_number": 1, "url": ""})
                state["selected_page"] = state["pages"][0]["_id"]
                state["selected_test"] = -1
                state["selected_pat_set"] = None
                auto_number_tests()
                save_all()
                refresh_page_dd(False); refresh_test_list(False); refresh_steps(False)
                refresh_pat_set_list(False); refresh_pats(False); page.update()
                src_ver = data.get("version", "?")
                snack(f"インポート完了 ({len(imp_pages)}ページ, {len(imp_tests)}テスト)")
                log(f"[プロジェクト] インポート: {fp} (v{src_ver}, {mode_dd.value})")
                close_dlg(dlg)
            except json.JSONDecodeError:
                snack("JSONパースエラー", ft.Colors.RED_600)
            except Exception as x:
                _log_error("import_project", x); snack(f"インポート失敗: {x}", ft.Colors.RED_600)

        dlg = ft.AlertDialog(title=ft.Text("プロジェクトインポート"),
            content=ft.Column([path_field, mode_dd,
                ft.Text("検出されたファイル:", size=11, weight=ft.FontWeight.BOLD),
                file_list_col], tight=True, spacing=10, width=500),
            actions=[ft.TextButton("インポート", on_click=on_ok),
                     ft.TextButton("キャンセル", on_click=lambda e: close_dlg(dlg))])
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
        if not test_cases_to_run: snack("テストケース0件", ft.Colors.RED_700); return
        # URL pre-check: resolve URL for each test case and warn about missing ones
        _page_url_map = {pg["_id"]: pg.get("url","").strip() for pg in state["pages"]}
        no_url_tests = []
        for tc in test_cases_to_run:
            tc_url = tc.get("url","").strip()
            if not tc_url and not _page_url_map.get(tc.get("page_id",""), ""):
                no_url_tests.append(tc)
        if len(no_url_tests) == len(test_cases_to_run):
            snack("URL未設定（ページまたはテストケースに設定してください）", ft.Colors.RED_700); return
        if no_url_tests:
            names = "\n".join(f"  - {tc.get('number','')} {tc.get('name','')}" for tc in no_url_tests[:10])
            if len(no_url_tests) > 10: names += f"\n  ... 他 {len(no_url_tests)-10} 件"
            def on_continue(e):
                close_dlg(warn_dlg)
                _do_run_execute(test_cases_to_run, run_label)
            warn_dlg = ft.AlertDialog(title=ft.Text("URL未設定のテストケースがあります"),
                content=ft.Column([
                    ft.Text(f"{len(no_url_tests)} 件のテストはURL未設定のためスキップされます:", size=12),
                    ft.Text(names, size=11, font_family="Consolas"),
                ], tight=True, spacing=8, width=450),
                actions=[ft.TextButton("続行", on_click=on_continue),
                         ft.TextButton("キャンセル", on_click=lambda e: close_dlg(warn_dlg))])
            open_dlg(warn_dlg); return
        _do_run_execute(test_cases_to_run, run_label)

    def _do_run_execute(test_cases_to_run, run_label=""):
        c = state["config"]
        close_browser()
        state["running"] = True
        stop_ev = threading.Event(); state["stop_event"] = stop_ev
        run_btn.disabled = True; run_single_btn.disabled = True; run_page_btn.disabled = True
        run_btn.icon = ft.Icons.HOURGLASS_TOP; run_single_btn.icon = ft.Icons.HOURGLASS_TOP; run_page_btn.icon = ft.Icons.HOURGLASS_TOP
        stop_btn.visible = True; stop_btn.disabled = False; open_folder_btn.visible = False
        run_spinner.visible = True; progress.visible = True; progress.value = 0; progress_label.visible = True; progress_label.value = ""
        nav_bar.selected_index = 0; switch_tab(0); page.update(); save_all()
        def on_progress(current, total, tc_label=""):
            progress.value = current / total if total > 0 else None
            label = f"{current}/{total} パターン"
            if tc_label: label += f" — {tc_label}"
            progress_label.value = label; page.update()
        def on_done(outdir=None):
            state["running"] = False
            run_btn.disabled = False; run_single_btn.disabled = False; run_page_btn.disabled = False
            run_btn.icon = ft.Icons.PLAY_ARROW; run_single_btn.icon = ft.Icons.PLAY_ARROW; run_page_btn.icon = ft.Icons.PLAY_ARROW
            stop_btn.visible = False; run_spinner.visible = False; progress.visible = False; progress_label.visible = False
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
    _init_browser_url = cfg.get("browser_url","")
    if not _init_browser_url:
        _init_pg = cur_page()
        if _init_pg: _init_browser_url = _init_pg.get("url", "")
    browser_url = ft.TextField(label="URL", expand=True, dense=True, value=_init_browser_url)
    browser_url_dd = ft.Dropdown(label="履歴", expand=True, dense=True,
        options=[ft.dropdown.Option(u) for u in state["selector_bank"].keys()], on_select=on_url_dd_sel)
    browser_wait = ft.TextField(label="秒", width=55, dense=True, value=cfg.get("browser_wait","3.0"))
    load_btn = ft.Button("読込", icon=ft.Icons.DOWNLOAD, on_click=load_page_click)
    el_loading = ft.ProgressRing(width=14, height=14, stroke_width=2, visible=False)
    el_status = ft.Text("未読込", size=11, color=ft.Colors.GREY_500)
    el_search = ft.TextField(label="検索", expand=True, dense=True, hint_text="セレクタ/id/name/ヒント",
                             on_change=on_el_search_change, prefix_icon=ft.Icons.SEARCH)
    el_show_hidden = ft.Checkbox(label="非表示要素も表示", value=False, on_change=on_show_hidden_change)
    el_sort_dd = ft.Dropdown(label="並び", width=100, dense=True, value="dom",
        options=[ft.dropdown.Option(key="dom", text="DOM順"),
                 ft.dropdown.Option(key="tag", text="タグ別"),
                 ft.dropdown.Option(key="type", text="type別"),
                 ft.dropdown.Option(key="id", text="id/name別")],
        on_select=on_el_sort_change)
    sel_test_field = ft.TextField(label="セレクタテスト", expand=True, dense=True, hint_text="CSSセレクタを入力して検証")
    el_table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text("タグ",size=11)), ft.DataColumn(ft.Text("type",size=11)),
                 ft.DataColumn(ft.Text("id/name",size=11)), ft.DataColumn(ft.Text("ヒント",size=11)),
                 ft.DataColumn(ft.Text("セレクタ",size=11))],
        rows=[], column_spacing=8, data_row_min_height=28, heading_row_height=30,
        show_checkbox_column=True)

    # Page selector
    page_dd = ft.Dropdown(label="ページ", expand=True, dense=True,
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
    ps_search = ft.TextField(label="検索", width=250, dense=True, hint_text="パターンセット名",
                             on_change=on_ps_search_change, prefix_icon=ft.Icons.SEARCH)
    pat_set_list = ft.ReorderableListView(controls=[], on_reorder=on_pat_set_reorder, spacing=4, expand=True)
    pat_items = ft.ReorderableListView(controls=[], on_reorder=on_pat_reorder, spacing=3, expand=True)
    pat_header = ft.Text("", weight=ft.FontWeight.BOLD, size=15)
    run_spinner = ft.ProgressRing(width=16, height=16, stroke_width=2, visible=False)
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

    # ── Layout: Tab 1 (collapsible test list) ──
    _tc_panel_collapsed = [False]
    tc_panel_full = ft.Column([
        ft.Row([page_dd,
                ft.IconButton(ft.Icons.ADD, tooltip="ページ追加", icon_size=16, icon_color=ft.Colors.GREY_700, style=ft.ButtonStyle(padding=4), on_click=add_page),
                ft.IconButton(ft.Icons.EDIT, tooltip="ページ編集", icon_size=16, icon_color=ft.Colors.GREY_700, style=ft.ButtonStyle(padding=4), on_click=edit_page),
                ft.IconButton(ft.Icons.DELETE, tooltip="ページ削除", icon_size=16, icon_color=ft.Colors.GREY_700, style=ft.ButtonStyle(padding=4), on_click=del_page),
               ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        page_info_label,
        ft.Divider(height=1),
        ft.Row([ft.Text("テストケース", weight=ft.FontWeight.BOLD, size=13),
                ft.IconButton(ft.Icons.ADD, tooltip="テスト追加", icon_size=16, on_click=add_test)],
               alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        test_list,
    ], spacing=4)
    tc_panel_mini = ft.Column([
        ft.Text("TC", size=10, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER),
    ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER, visible=False)
    def toggle_tc_panel(e):
        _tc_panel_collapsed[0] = not _tc_panel_collapsed[0]
        collapsed = _tc_panel_collapsed[0]
        tc_panel_full.visible = not collapsed
        tc_panel_mini.visible = collapsed
        tc_panel_container.width = 40 if collapsed else 320
        tc_collapse_btn.icon = ft.Icons.CHEVRON_RIGHT if collapsed else ft.Icons.CHEVRON_LEFT
        tc_collapse_btn.tooltip = "テスト一覧を展開" if collapsed else "テスト一覧を折りたたむ"
        page.update()
    tc_collapse_btn = ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_size=16, tooltip="テスト一覧を折りたたむ",
                                     on_click=toggle_tc_panel, icon_color=ft.Colors.GREY_500, style=ft.ButtonStyle(padding=2))
    tc_panel_container = ft.Container(ft.Column([
        ft.Row([tc_collapse_btn], alignment=ft.MainAxisAlignment.END),
        tc_panel_full, tc_panel_mini,
    ], spacing=0), width=320, padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8)

    tc_content = ft.Row([
        tc_panel_container,
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
            ft.Row([browser_url_dd, ft.OutlinedButton("読込", on_click=load_bank)], spacing=4),
            ft.Row([load_btn, ft.OutlinedButton("DOM再取得", icon=ft.Icons.REFRESH, on_click=reload_dom_click),
                    ft.OutlinedButton("閉じる", on_click=close_br)], spacing=4, wrap=True),
            ft.Row([el_search, el_sort_dd, el_show_hidden], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([sel_test_field, ft.OutlinedButton("テスト", icon=ft.Icons.PLAY_ARROW, on_click=test_selector_click)], spacing=4),
            ft.Row([el_loading, el_status], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(ft.Column([el_table], scroll=ft.ScrollMode.AUTO),
                expand=True, border=ft.Border.all(1, ft.Colors.GREY_200), border_radius=4),
            ft.Text("ステップ追加:", size=10, color=ft.Colors.GREY_500),
            ft.Row([ft.Button("入力", icon=ft.Icons.EDIT, on_click=lambda e: quick_add("入力")),
                    ft.Button("クリック", icon=ft.Icons.MOUSE, on_click=lambda e: quick_add("クリック")),
                    ft.Button("選択", icon=ft.Icons.ARROW_DROP_DOWN_CIRCLE, on_click=lambda e: quick_add("選択"))], spacing=4),
            ft.Row([ft.Button("全パターン", icon=ft.Icons.LIST, on_click=quick_add_all_options),
                    ft.Button("値取込", icon=ft.Icons.SAVE, on_click=capture_form)], spacing=4),
        ], spacing=4), expand=2, padding=8, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),
    ], spacing=8, expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

    # ── Layout: Tab 2 ──
    ps_content = ft.Row([
        ft.Container(ft.Column([
            ft.Row([ft.Text("パターンセット", weight=ft.FontWeight.BOLD, size=14),
                    ft.IconButton(ft.Icons.ADD, tooltip="追加", icon_size=18, on_click=add_pat_set)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ps_search,
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
        actions=[ft.IconButton(ft.Icons.FILE_UPLOAD, tooltip="プロジェクトエクスポート", on_click=export_project),
                 ft.IconButton(ft.Icons.FILE_DOWNLOAD, tooltip="プロジェクトインポート", on_click=import_project),
                 ft.IconButton(ft.Icons.SETTINGS, tooltip="設定", on_click=show_settings),
                 ft.IconButton(ft.Icons.INFO_OUTLINE, tooltip="情報", on_click=show_info)])

    page.add(ft.Column([ft.Stack([tc_content, ps_content], expand=True),
        ft.Row([run_spinner, progress, progress_label], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([open_folder_btn, stop_btn, run_single_btn, run_page_btn, run_btn],
               alignment=ft.MainAxisAlignment.END, spacing=8)], expand=True, spacing=4))
    page.navigation_bar = nav_bar

    # ── Keyboard shortcuts ──
    def on_keyboard(e: ft.KeyboardEvent):
        if not _init_done[0]: return
        key = e.key; ctrl = e.ctrl or e.meta
        if ctrl and key.lower() == "s":
            save_all(); snack("保存しました")
        elif ctrl and key.lower() == "n":
            if nav_bar.selected_index == 0:
                add_test(None)
            else:
                add_pat_set(None)
        elif key == "Delete":
            if nav_bar.selected_index == 0:
                idx = state["selected_test"]
                if 0 <= idx < len(state["tests"]): del_test(idx)
            else:
                name = state["selected_pat_set"]
                if name: del_pat_set(name)
    page.on_keyboard_event = on_keyboard

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
