"""
y-diff: y-shot HTMLソース比較レビューツール v1.2
  PHPバージョンアップ等でのリグレッション検証用。
  2つのy-shot出力フォルダを比較し、差分をレビュー・マーク・記録する。
"""
import os, sys, json, re, difflib, threading, logging
# Set AppUserModelID so Windows taskbar shows the exe icon, not the Flet client icon
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ydiff.app")
except Exception:
    pass
from datetime import datetime
import flet as ft

# File logger (separate from y-shot)
def _setup_logger():
    _log_dir = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__)), "log")
    os.makedirs(_log_dir, exist_ok=True)
    _log_file = os.path.join(_log_dir, f"y-diff_{datetime.now().strftime('%Y%m%d')}.log")
    logger = logging.getLogger("y-diff")
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        fh = logging.FileHandler(_log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(fh)
    return logger
_flog = _setup_logger()

APP_NAME = "y-diff"
APP_VERSION = "1.5"

# ============================================================
# Constants
# ============================================================
SOURCE_DOM = "dom"
SOURCE_RAW = "raw"
SOURCE_PATH = "path"

def _get_file_path(entry, preferred=SOURCE_DOM):
    """Get file path from scan entry, trying preferred source then fallbacks."""
    return entry.get(preferred) or entry.get(SOURCE_DOM) or entry.get(SOURCE_RAW) or entry.get(SOURCE_PATH)

# ============================================================
# Noise normalization patterns
# ============================================================
_NOISE_PATTERNS = [
    (re.compile(r'(<(?:input|meta)[^>]*(?:name|content)\s*=\s*["\'](?:_token|csrf[_-]?token|csrfmiddlewaretoken|__RequestVerificationToken|authenticity_token|nonce|PHPSESSID|session_id|_session|jsessionid)[^>]*(?:value|content)\s*=\s*["\'])[^"\']*(["\'])', re.I), r'\1__NORM__\2'),
    # Datetime: preserve format pattern (YYYY-MM-DD vs YYYY/MM/DD), replace only digits
    (re.compile(r'\d{4}([-/])\d{2}\1\d{2}([\sT])\d{2}:\d{2}:\d{2}(\+\d{2}:\d{2})?'), r'__D4__\1__D2__\1__D2__\2__T2__:__T2__:__T2__'),
    (re.compile(r'\d{4}([-/])\d{2}\1\d{2}([\sT])\d{2}:\d{2}'), r'__D4__\1__D2__\1__D2__\2__T2__:__T2__'),
    (re.compile(r'(?<=["\'\s=])\d{10,13}(?=["\'\s&;])'), '__TS__'),
    (re.compile(r'(nonce\s*=\s*["\'])[A-Za-z0-9+/=]+(["\'])', re.I), r'\1__NONCE__\2'),
    (re.compile(r'(\?(?:v|t|_|ver|version|cache|cb|_dc)\s*=)[^"\'&\s]+', re.I), r'\1__CACHE__'),
    # Tracking scripts (line-based, no backtracking)
    (re.compile(r'^.*(?:googletagmanager|google-analytics|clarity\.ms|ads-twitter|yimg\.jp/images/listing|doubleclick\.net/pagead).*$', re.I | re.M), '<!-- __TRACKING__ -->'),
    (re.compile(r'dataLayer\.push\(\{[^}]*\}\);?', re.I), '/* __GTM__ */'),
    (re.compile(r'^.*googletagmanager.*$', re.I | re.M), '<!-- __GTM_NS__ -->'),
    # GTM inline script block (w[l]=w[l]||[], etc.)
    (re.compile(r'^w\[l\]\s*=.*$', re.M), '/* __GTM_INIT__ */'),
    (re.compile(r'^w\[l\]\.push\(.*$', re.M), '/* __GTM_PUSH__ */'),
    (re.compile(r'^\}\)\(window,\s*document.*$', re.M), '/* __GTM_END__ */'),
    # GTM form interaction tracking (remove entire attribute)
    (re.compile(r'\s*data-gtm-form-interact[-\w]*="[^"]*"'), ''),
    # Google Ads viewthrough conversion
    (re.compile(r'(googleads\.g\.doubleclick\.net/pagead/viewthroughconversion/)[^"]*'), r'\1__ADS__'),
    # Twitter/X tracking pixels
    (re.compile(r'((?:t\.co|analytics\.twitter\.com)/i/adsct\?)[^"]*', re.I), r'\1__TW_ID__'),
    # Generic UUID
    (re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I), '__UUID__'),
    # PHP version strings in comments/meta
    (re.compile(r'(PHP/?)\d+\.\d+(\.\d+)?', re.I), r'\1__VER__'),
    # NOTE: PHP errors/warnings are NOT normalized here — they are classified as
    # "php_warning" by classify_line() so they remain visible for VU review.
]

# Pre-compiled patterns for normalize() — avoids recompilation on each call
_RE_TRAILING_WS = re.compile(r'[ \t]+$', re.M)
_RE_BLANK_LINES = re.compile(r'\n{3,}')
_RE_EMPTY_LINES = re.compile(r'^\s*\n', re.M)
_RE_GTM_BLOCK = re.compile(r'<script>\s*\(function\(w,\s*d,\s*s,\s*l,\s*i\).*?</script>', re.S)
_RE_SCRIPT = re.compile(r'<script\b[^>]*>.*?</script>', re.S)
_RE_PRE = re.compile(r'<pre\b[^>]*>.*?</pre>', re.S)
_RE_CODE = re.compile(r'<code\b[^>]*>.*?</code>', re.S)
_RE_JS_IF = re.compile(r'if\s*\(')
_RE_JS_FUNC = re.compile(r'\s*\(\s*function\s*\(')
_RE_JS_SEMI = re.compile(r'\)\s*;\s*')
_RE_JS_ELSE = re.compile(r'\}\s*else\s*\{')
_RE_JS_BRACE = re.compile(r'\)\s*\{')
_RE_JS_COMMA = re.compile(r',\s+')
_RE_JS_PAREN_L = re.compile(r'\(\s+')
_RE_JS_PAREN_R = re.compile(r'\s+\)')
_RE_JS_QUOTE_L = re.compile(r"\(\s*'")
_RE_JS_QUOTE_R = re.compile(r"'\s*\)")
_RE_COLLAPSE_WS = re.compile(r'\s+')
_RE_EMPTY_SCRIPT = re.compile(r'<script[^>]*>\s*</script>')
_RE_EMPTY_STYLE = re.compile(r'<style[^>]*>\s*</style>')
_RE_CLOSE_STRUCT = re.compile(r'</(head|body|html)>')
_RE_BLOCK_SPLIT = re.compile(r'><(?=(html|head|body|div|p|form|table|tr|td|th|ul|ol|li|section|article|nav|header|footer|main|aside|h[1-6]|script|style|link|meta|hr|br|noscript|iframe|input|select|textarea|button|label|img|a\b|span)\b)')
_RE_COMMENT_OPEN = re.compile(r'><!--')
_RE_COMMENT_CLOSE = re.compile(r'--><')
_RE_NOISE_REMNANT = re.compile(r'<!-- __(?:TRACKING|GTM_BLOCK|GTM_NS)__ -->')
_RE_GTM_COMMENT = re.compile(r'/\* __GTM[^*]*\*/')

def normalize(html):
    s = html.replace('\r\n', '\n').replace('\r', '\n')
    s = s.replace('\t', '  ')
    s = _RE_TRAILING_WS.sub('', s)
    s = _RE_BLANK_LINES.sub('\n\n', s)
    s = _RE_EMPTY_LINES.sub('', s)
    # 1. Noise patterns FIRST (before tag joining, so line-based patterns still work)
    for pat, repl in _NOISE_PATTERNS:
        s = pat.sub(repl, s)
    # 2. Remove entire GTM/tracking script blocks (multiline, greedy but bounded)
    s = _RE_GTM_BLOCK.sub('<!-- __GTM_BLOCK__ -->', s)
    # 3. Protect <script>, <pre>, <code> content — replace with placeholders before whitespace normalization
    _protected = []
    def _protect(m):
        _protected.append(m.group(0))
        return f'__PROTECTED_{len(_protected)-1}__'
    s = _RE_SCRIPT.sub(_protect, s)
    s = _RE_PRE.sub(_protect, s)
    s = _RE_CODE.sub(_protect, s)
    # 4. JS formatting normalization (only for non-protected HTML)
    s = _RE_JS_IF.sub('if(', s)
    s = _RE_JS_FUNC.sub('(function(', s)
    s = _RE_JS_SEMI.sub(');', s)
    s = _RE_JS_ELSE.sub('}else{', s)
    s = _RE_JS_BRACE.sub('){', s)
    s = _RE_JS_COMMA.sub(',', s)
    s = _RE_JS_PAREN_L.sub('(', s)
    s = _RE_JS_PAREN_R.sub(')', s)
    s = _RE_JS_QUOTE_L.sub("('", s)
    s = _RE_JS_QUOTE_R.sub("')", s)
    # 5. Collapse all whitespace (tabs, newlines, spaces) into single spaces
    s = _RE_COLLAPSE_WS.sub(' ', s)
    # 6. Clean up spaces around tags
    s = s.replace('> <', '><')
    # Restore protected blocks
    for i, block in enumerate(_protected):
        block = block.replace('\r\n', '\n').replace('\r', '\n')
        block = _RE_TRAILING_WS.sub('', block)
        s = s.replace(f'__PROTECTED_{i}__', block)
    # 7. Remove empty script/style tags (browser-injected remnants)
    s = _RE_EMPTY_SCRIPT.sub('', s)
    s = _RE_EMPTY_STYLE.sub('', s)
    # 8. Remove standalone closing tags for structural elements
    s = _RE_CLOSE_STRUCT.sub('', s)
    # 9. Split into lines at block-level OPENING tag boundaries for readable diff
    s = _RE_BLOCK_SPLIT.sub('>\n<', s)
    s = _RE_COMMENT_OPEN.sub('>\n<!--', s)
    s = _RE_COMMENT_CLOSE.sub('-->\n<', s)
    # 10. Remove all noise placeholder remnants
    s = _RE_NOISE_REMNANT.sub('', s)
    s = _RE_GTM_COMMENT.sub('', s)
    s = _RE_EMPTY_LINES.sub('', s)
    return s

def _extract_text_content(html_line):
    """HTMLタグを除去してテキスト内容だけ抽出"""
    s = re.sub(r'<[^>]+>', '', html_line)
    return re.sub(r'\s+', ' ', s).strip()

def classify_line(line):
    l = line.lower()
    # PHP warnings/errors — highest priority, must not be masked as noise
    if re.search(r'\b(?:notice|warning|deprecated|fatal error|parse error)\s*:', l): return "php_warning"
    if re.search(r'\.php\s+on\s+line\s+\d+', l): return "php_warning"
    if re.search(r'<(?:input|select|textarea|option|button|label|form)\b', l): return "form"
    if re.search(r'\b(?:value|checked|selected|disabled|readonly|placeholder|required)\s*=', l): return "form"
    if re.search(r'</?(?:div|section|article|nav|header|footer|main|aside|table|tr|td|th|ul|ol|li)\b', l): return "structural"
    if re.search(r'\b(?:class|id|style)\s*=', l): return "structural"
    if re.search(r'<(?:p|span|h[1-6]|a|strong|em|b|i|img|br)\b', l) or not l.strip().startswith('<'): return "content"
    return "structural"

def classify_change(la, lb):
    """変更行ペアの分類。テキスト内容が同じでタグ構造だけ違えばnoiseにする"""
    cat_a = classify_line(la) if la else "structural"
    cat_b = classify_line(lb) if lb else "structural"
    # 両方structuralで、テキスト内容が同じなら noise
    if cat_a == "structural" and cat_b == "structural":
        if la and lb and _extract_text_content(la) == _extract_text_content(lb):
            return "noise"
    _CAT_PRIORITY = {"php_warning": 4, "form": 3, "content": 2, "structural": 1, "noise": 0}
    return cat_a if _CAT_PRIORITY.get(cat_a, 0) >= _CAT_PRIORITY.get(cat_b, 0) else cat_b

# ============================================================
# Folder scanning
# ============================================================
_RE_NUM_PREFIX = re.compile(r'^\d{3}_')  # e.g. "001_" prefix in y-shot filenames

def _strip_num_prefix(key):
    """Strip the 3-digit number prefix from y-shot filenames for fallback matching.
    e.g. '1_page/001_1-1_test_ss1' → '1_page/1-1_test_ss1'"""
    parts = key.rsplit('/', 1)
    if len(parts) == 2:
        return parts[0] + '/' + _RE_NUM_PREFIX.sub('', parts[1])
    return _RE_NUM_PREFIX.sub('', key)

def scan_source_folder(folder):
    result = {}
    source_dir = None
    for root, dirs, files in os.walk(folder):
        if os.path.basename(root) == '_source':
            source_dir = root; break
        if '_source' in dirs:
            source_dir = os.path.join(root, '_source'); break
    if not source_dir or not os.path.isdir(source_dir):
        for root, dirs, files in os.walk(folder):
            for f in sorted(files):
                if f.lower().endswith(('.html', '.htm')):
                    key = os.path.relpath(os.path.join(root, f), folder).replace('\\', '/')
                    result[key] = {"path": os.path.join(root, f)}
        return result
    for root, dirs, files in os.walk(source_dir):
        dirs.sort()
        for f in sorted(files):
            if not f.lower().endswith(('.html', '.htm')): continue
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, source_dir).replace('\\', '/')
            if rel.endswith('_dom.html'):
                key = rel[:-9]
                result.setdefault(key, {})["dom"] = fp
            elif rel.endswith('_raw.html'):
                key = rel[:-9]
                result.setdefault(key, {})["raw"] = fp
            else:
                result.setdefault(rel, {})["path"] = fp
    return result

def scan_image_folder(folder):
    """Scan a y-shot output folder for PNG screenshot files. Returns {relative_key: path}."""
    result = {}
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in sorted(dirs) if not d.startswith("_")]
        for f in sorted(files):
            if not f.lower().endswith(".png"): continue
            if f.lower().endswith("_diff.png"): continue  # Skip y-diff generated diff images
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, folder).replace('\\', '/')
            result[rel] = fp
    return result

def compare_images(path_a, path_b):
    """Compare two PNG images. Returns (same: bool, diff_pct: float, diff_img_path: str|None)."""
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageFilter
        _img_a_raw = Image.open(path_a); img_a = _img_a_raw.convert("RGB"); _img_a_raw.close()
        _img_b_raw = Image.open(path_b); img_b = _img_b_raw.convert("RGB"); _img_b_raw.close()
        if img_a.size != img_b.size:
            # Generate side-by-side for size mismatch
            diff_dir = os.path.dirname(path_b)
            diff_name = os.path.splitext(os.path.basename(path_b))[0] + "_diff.png"
            diff_path = os.path.join(diff_dir, diff_name)
            total_w = img_a.size[0] + img_b.size[0] + 20
            max_h = max(img_a.size[1], img_b.size[1])
            canvas = Image.new("RGB", (total_w, max_h + 30), (255, 255, 255))
            canvas.paste(img_a, (0, 30))
            canvas.paste(img_b, (img_a.size[0] + 20, 30))
            draw = ImageDraw.Draw(canvas)
            draw.text((5, 5), f"旧: {img_a.size[0]}x{img_a.size[1]}", fill=(0, 0, 200))
            draw.text((img_a.size[0] + 25, 5), f"新: {img_b.size[0]}x{img_b.size[1]}", fill=(200, 0, 0))
            canvas.save(diff_path)
            return False, 100.0, diff_path
        diff = ImageChops.difference(img_a, img_b)
        pixels = img_a.size[0] * img_a.size[1]
        if pixels == 0: return True, 0.0, None
        # Quick check: if all pixels identical, skip heavy processing
        if diff.getbbox() is None:
            return True, 0.0, None
        # Convert to grayscale for threshold check
        diff_gray = diff.convert("L")
        # Use thumbnail for fast percentage calculation
        thumb_size = (200, 200)
        diff_thumb = diff_gray.copy()
        diff_thumb.thumbnail(thumb_size)
        thumb_data = list(diff_thumb.getdata())
        thumb_changed = sum(1 for v in thumb_data if v > 10)
        pct = (thumb_changed / len(thumb_data)) * 100
        if pct < 0.01:
            return True, 0.0, None
        # Generate diff highlight image with red bounding boxes around changed regions
        diff_dir = os.path.dirname(path_b)
        diff_name = os.path.splitext(os.path.basename(path_b))[0] + "_diff.png"
        diff_path = os.path.join(diff_dir, diff_name)
        # Create binary mask → dilate → find bounding boxes
        mask = diff_gray.point(lambda v: 255 if v > 10 else 0)
        # Dilate to merge nearby changed pixels into regions
        mask = mask.filter(ImageFilter.MaxFilter(15))
        # Red overlay on changed areas
        overlay = img_b.copy()
        red_layer = Image.new("RGB", img_b.size, (255, 0, 0))
        mask_rgb = mask.convert("L")
        overlay = Image.composite(red_layer, overlay, mask_rgb)
        blended = Image.blend(img_b, overlay, 0.4)
        # Draw bounding rectangles using row-scan approach (much faster than BFS)
        draw = ImageDraw.Draw(blended)
        w, h = img_a.size
        # Downscale mask for fast region detection (4x smaller)
        scale = 4
        small_mask = mask.resize((w // scale, h // scale), Image.NEAREST)
        small_w, small_h = small_mask.size
        small_data = list(small_mask.getdata())
        visited = [False] * (small_w * small_h)
        regions = []
        for sy in range(small_h):
            for sx in range(small_w):
                si = sy * small_w + sx
                if small_data[si] > 0 and not visited[si]:
                    # BFS on downscaled image (much fewer pixels)
                    min_x, min_y, max_x, max_y = sx, sy, sx, sy
                    stack = [(sx, sy)]
                    while stack:
                        cx, cy = stack.pop()
                        ci = cy * small_w + cx
                        if cx < 0 or cx >= small_w or cy < 0 or cy >= small_h: continue
                        if visited[ci] or small_data[ci] == 0: continue
                        visited[ci] = True
                        min_x = min(min_x, cx); max_x = max(max_x, cx)
                        min_y = min(min_y, cy); max_y = max(max_y, cy)
                        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                            nx, ny = cx+dx, cy+dy
                            if 0 <= nx < small_w and 0 <= ny < small_h:
                                ni = ny * small_w + nx
                                if not visited[ni] and small_data[ni] > 0:
                                    stack.append((nx, ny))
                    # Scale back to original coordinates
                    rx1, ry1 = min_x * scale, min_y * scale
                    rx2, ry2 = min((max_x + 1) * scale, w), min((max_y + 1) * scale, h)
                    if (rx2 - rx1) > 5 and (ry2 - ry1) > 5:
                        regions.append((rx1, ry1, rx2, ry2))
        for x1, y1, x2, y2 in regions:
            draw.rectangle([x1-2, y1-2, x2+2, y2+2], outline=(255, 0, 0), width=2)
        blended.save(diff_path)
        return False, pct, diff_path
    except ImportError:
        return False, -1.0, None
    except Exception as x:
        _flog.error(f"compare_images: {x}")
        return False, -1.0, None

def read_file(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as x:
        return f"<!-- ERROR: {x} -->"

# Pre-compiled noise detection patterns for compute_diff (avoid recompilation per line)
_NOISE_MARKER_PAT = re.compile(r'__(?:NORM|D4|D2|T2|TS|NONCE|CACHE|TRACKING|GTM|UUID|VER|ADS|TW_ID|GTM_BLOCK|GTM_INIT|GTM_PUSH|GTM_END|GTM_NS)__')
_NOISE_STRIP_PAT = re.compile(r'__(?:D4|D2|T2|TS|NORM|NONCE|CACHE|UUID|VER|TRACKING|GTM|GTM_BLOCK|GTM_INIT|GTM_PUSH|GTM_END|GTM_NS|ADS|TW_ID)__')

def _is_noise(text_a, text_b=None):
    """Check if a change is noise. For replace ops, both lines must be noise-only."""
    if not ('__' in (text_a or '')):
        return False
    if not _NOISE_MARKER_PAT.search(text_a or ''):
        return False
    if text_b is not None:
        struct_a = _NOISE_STRIP_PAT.sub('##', text_a or '')
        struct_b = _NOISE_STRIP_PAT.sub('##', text_b or '')
        if struct_a != struct_b:
            return False
    return True

def compute_diff_normalized(norm_a, norm_b):
    """Compute diff from already-normalized text (avoids double normalization)."""
    return _compute_diff_lines(norm_a.splitlines(keepends=True), norm_b.splitlines(keepends=True))

def compute_diff(text_a, text_b):
    return _compute_diff_lines(normalize(text_a).splitlines(keepends=True), normalize(text_b).splitlines(keepends=True))

def _compute_diff_lines(lines_a, lines_b):
    sm = difflib.SequenceMatcher(None, lines_a, lines_b)
    ops = []
    stats = {"same": 0, "add": 0, "del": 0, "change": 0, "noise": 0, "php_warning": 0}
    cat_counts = {"form": 0, "content": 0, "structural": 0, "noise": 0, "php_warning": 0}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                ops.append(("=", i1+k, j1+k, lines_a[i1+k], lines_b[j1+k], None))
                stats["same"] += 1
        elif tag == 'replace':
            n = max(i2-i1, j2-j1)
            for k in range(n):
                la = lines_a[i1+k].rstrip('\n') if i1+k < i2 else None
                lb = lines_b[j1+k].rstrip('\n') if j1+k < j2 else None
                is_noise = _is_noise(la, lb)
                cat = "noise" if is_noise else classify_change(la, lb)
                if la is not None and lb is not None:
                    ops.append(("~", i1+k, j1+k, la, lb, cat)); stats["change"] += 1
                elif la is not None:
                    ops.append(("-", i1+k, None, la, None, cat)); stats["del"] += 1
                else:
                    ops.append(("+", None, j1+k, None, lb, cat)); stats["add"] += 1
                if is_noise: stats["noise"] += 1
                else: cat_counts[cat] = cat_counts.get(cat, 0) + 1
                if cat == "php_warning": stats["php_warning"] += 1
        elif tag == 'delete':
            for k in range(i2 - i1):
                la = lines_a[i1+k].rstrip('\n')
                is_noise = _is_noise(la)
                cat = "noise" if is_noise else classify_line(la)
                ops.append(("-", i1+k, None, la, None, cat)); stats["del"] += 1
                if is_noise: stats["noise"] += 1
                else: cat_counts[cat] = cat_counts.get(cat, 0) + 1
                if cat == "php_warning": stats["php_warning"] += 1
        elif tag == 'insert':
            for k in range(j2 - j1):
                lb = lines_b[j1+k].rstrip('\n')
                is_noise = _is_noise(lb)
                cat = "noise" if is_noise else classify_line(lb)
                ops.append(("+", None, j1+k, None, lb, cat)); stats["add"] += 1
                if is_noise: stats["noise"] += 1
                else: cat_counts[cat] = cat_counts.get(cat, 0) + 1
                if cat == "php_warning": stats["php_warning"] += 1
    return ops, stats, cat_counts

# ============================================================
# Review state persistence
# ============================================================
REVIEW_FILE = "html_diff_review.json"

def load_review(folder_a, folder_b):
    for d in [folder_b, folder_a]:
        p = os.path.join(d, REVIEW_FILE)
        if os.path.isfile(p):
            try:
                with open(p, 'r', encoding='utf-8') as f: return json.load(f)
            except Exception: pass
    return {}

def save_review(folder_b, review_data):
    p = os.path.join(folder_b, REVIEW_FILE)
    try:
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(review_data, f, ensure_ascii=False, indent=2)
    except Exception: pass

# ============================================================
# Flet UI
# ============================================================
MARK_OPTIONS = [
    ("unreviewed", "未レビュー", ft.Colors.GREY_400),
    ("ok", "OK (問題なし)", ft.Colors.GREEN_600),
    ("noise", "ノイズのみ", ft.Colors.BLUE_400),
    ("check", "要確認", ft.Colors.ORANGE_600),
    ("problem", "問題あり", ft.Colors.RED_600),
]
MARK_ICONS = {
    "unreviewed": ft.Icons.RADIO_BUTTON_UNCHECKED,
    "ok": ft.Icons.CHECK_CIRCLE,
    "noise": ft.Icons.FILTER_DRAMA,
    "check": ft.Icons.WARNING_AMBER,
    "problem": ft.Icons.ERROR,
}
CAT_COLORS = {
    "form": ft.Colors.GREEN_100,
    "content": ft.Colors.PURPLE_100,
    "structural": ft.Colors.AMBER_50,
    "noise": ft.Colors.GREY_200,
    "php_warning": ft.Colors.RED_100,
}
CAT_TEXT_DEL = {
    "form": ft.Colors.GREEN_900,
    "content": ft.Colors.PURPLE_900,
    "structural": ft.Colors.RED_700,
    "noise": ft.Colors.GREY_500,
    "php_warning": ft.Colors.RED_900,
}
CAT_TEXT_ADD = {
    "form": ft.Colors.GREEN_800,
    "content": ft.Colors.PURPLE_700,
    "structural": ft.Colors.TEAL_700,
    "noise": ft.Colors.GREY_500,
    "php_warning": ft.Colors.RED_800,
}

def main(page: ft.Page):
    page.title = f"{APP_NAME} v{APP_VERSION}"
    page.window.width = 1600; page.window.height = 950
    page.padding = 10
    # Set window icon (check both PyInstaller bundle and source dir)
    for _icon_dir in [getattr(sys, '_MEIPASS', ''), os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__))]:
        _icon_path = os.path.join(_icon_dir, "assets", "diff_icon.ico")
        if os.path.isfile(_icon_path):
            try: page.window.icon = _icon_path
            except Exception: pass
            break
    # Clean exit handling (based on y-shot's robust exit)
    def _kill_children_and_exit():
        my_pid = os.getpid()
        _flog.info(f"Killing child processes of PID={my_pid}")
        if sys.platform == 'win32':
            import subprocess as _sp
            child_pids = []
            try:
                result = _sp.run(['wmic', 'process', 'where', f'ParentProcessId={my_pid}', 'get', 'ProcessId'],
                    capture_output=True, text=True, timeout=3, creationflags=0x08000000)
                for line in result.stdout.strip().split('\n'):
                    cpid = line.strip()
                    if cpid.isdigit() and cpid != str(my_pid): child_pids.append(cpid)
            except Exception: pass
            if not child_pids:
                try:
                    ps_cmd = f"Get-CimInstance Win32_Process -Filter 'ParentProcessId={my_pid}' | Select-Object -ExpandProperty ProcessId"
                    result = _sp.run(['powershell', '-NoProfile', '-Command', ps_cmd],
                        capture_output=True, text=True, timeout=5, creationflags=0x08000000)
                    for line in result.stdout.strip().split('\n'):
                        cpid = line.strip()
                        if cpid.isdigit() and cpid != str(my_pid): child_pids.append(cpid)
                except Exception: pass
            for cpid in child_pids:
                try: _sp.run(['taskkill', '/F', '/T', '/PID', cpid], capture_output=True, timeout=3, creationflags=0x08000000)
                except Exception: pass
            _flog.info(f"Killed {len(child_pids)} child processes")
        _deadline = threading.Timer(1.0, lambda: os._exit(0))
        _deadline.daemon = True; _deadline.start()
        sys.exit(0)

    def _on_window_event(e):
        is_close = False
        try: is_close = (e.type == ft.WindowEventType.CLOSE)
        except Exception:
            try: is_close = (e.data == "close")
            except Exception: pass
        if is_close:
            _flog.info("Window close requested")
            _kill_children_and_exit()

    import signal
    def _signal_cleanup(signum, frame):
        _kill_children_and_exit()
    try:
        signal.signal(signal.SIGTERM, _signal_cleanup)
        signal.signal(signal.SIGINT, _signal_cleanup)
    except (OSError, ValueError): pass

    page.window.prevent_close = True
    page.window.on_event = _on_window_event
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.TEAL)

    state = {
        "folder_a": "", "folder_b": "",
        "files_a": {}, "files_b": {},
        "imgs_a": {}, "imgs_b": {},  # image scan results
        "matched": [],
        "img_matched": [],  # image comparison results
        "diff_cache": {},
        "selected_key": None,
        "review": {},
        "src_type": "dom",
        "view_mode": "source",  # "source" or "image"
        "scanning": False,
        "scan_abort": False,
        "ready": False,
        "list_page": 0,
    }

    def snack(msg, color=ft.Colors.GREEN_700):
        try: page.show_dialog(ft.SnackBar(ft.Text(msg, color=ft.Colors.WHITE), bgcolor=color))
        except Exception: pass

    # ── Folder selection (TextField + confirm) ──
    def _apply_folder(side):
        try:
            path = (folder_a_field.value or "").strip() if side == 'A' else (folder_b_field.value or "").strip()
            path = path.strip('"').strip("'")
            if not path or not os.path.isdir(path):
                snack("フォルダが見つかりません", ft.Colors.RED_700); return
            if side == 'A':
                state["folder_a"] = path
                folder_a_field.value = path
                folder_a_field.label = f"旧: {os.path.basename(path)}"
            else:
                state["folder_b"] = path
                folder_b_field.value = path
                folder_b_field.label = f"新: {os.path.basename(path)}"
            page.update()
        except Exception as x:
            _flog.error(f"_apply_folder: {x}")
            snack(f"エラー: {x}", ft.Colors.RED_700)

    def _scan_recent_folders():
        """Scan for recent y-shot output folders (timestamp directories with _source)."""
        candidates = []
        # Check common locations
        search_roots = set()
        for ini_path in [os.path.join(os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__)), "y_shot_config.ini")]:
            if os.path.isfile(ini_path):
                try:
                    import configparser; c = configparser.ConfigParser(); c.read(ini_path, encoding="utf-8")
                    od = c.get("settings", "output_dir", fallback="")
                    if od and os.path.isdir(od): search_roots.add(od)
                except Exception: pass
        # Also check nearby screenshots folder
        app_dir = os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__))
        for sub in ["screenshots", os.path.join("dist", "screenshots")]:
            p = os.path.join(app_dir, sub)
            if os.path.isdir(p): search_roots.add(p)
        for root in search_roots:
            try:
                for d in sorted(os.listdir(root), reverse=True):
                    fp = os.path.join(root, d)
                    if os.path.isdir(fp) and (re.match(r'\d{8,14}$', d) or os.path.isfile(os.path.join(fp, "report.html"))):
                        candidates.append(fp)
                        if len(candidates) >= 20: break
            except Exception: pass
        return candidates

    def _on_recent_select(side, e):
        try:
            dd = recent_dd_a if side == 'A' else recent_dd_b
            if dd and dd.value:
                field = folder_a_field if side == 'A' else folder_b_field
                field.value = dd.value
                page.update()
                _apply_folder(side)
        except Exception as x:
            _flog.error(f"_on_recent_select: {x}")
            snack(f"エラー: {x}", ft.Colors.RED_700)

    # B1: Threaded scan — compute in background, update UI on main thread
    def do_scan():
        if state["scanning"]:
            # 既にスキャン中なら中断
            state["scan_abort"] = True
            return
        state["scanning"] = True
        state["scan_abort"] = False
        status_label.value = "スキャン中..."; page.update()
        state["diff_cache"].clear()
        page.run_thread(_do_scan_bg)

    def _do_scan_bg():
        try:
            if state.get("scan_abort"): return
            # All computation in background (no UI access)
            files_a = scan_source_folder(state["folder_a"])
            files_b = scan_source_folder(state["folder_b"])
            # Fallback matching: if keys differ only by numeric prefix, remap
            stripped_a = {_strip_num_prefix(k): k for k in files_a}
            stripped_b = {_strip_num_prefix(k): k for k in files_b}
            for sk, orig_a in stripped_a.items():
                if orig_a not in files_b and sk in stripped_b:
                    orig_b = stripped_b[sk]
                    if orig_b not in files_a:
                        # Remap: use the stripped key as the common key
                        files_a[sk] = files_a.pop(orig_a)
                        files_b[sk] = files_b.pop(orig_b)
            review = load_review(state["folder_a"], state["folder_b"])
            src = state["src_type"]
            keys = sorted(set(list(files_a.keys()) + list(files_b.keys())))
            matched = []
            diff_cache = {}
            total_keys = len(keys)
            for ki, k in enumerate(keys):
                if state.get("scan_abort"): return
                if ki % 10 == 0:
                    try: status_label.value = f"ソース比較中... {ki+1}/{total_keys}"; page.update()
                    except Exception: pass
                in_a = k in files_a; in_b = k in files_b
                status = "only"; stats = cat_counts = None
                if in_a and in_b:
                    pa = _get_file_path(files_a[k], src)
                    pb = _get_file_path(files_b[k], src)
                    if pa and pb:
                        ta = read_file(pa); tb = read_file(pb)
                        na = normalize(ta); nb = normalize(tb)
                        if na == nb:
                            status = "same"
                            stats = {"same": len(ta.splitlines()), "add":0, "del":0, "change":0, "noise":0, "php_warning":0}
                            cat_counts = {}
                        else:
                            status = "diff"
                            # 正規化済みテキストをキャッシュ（compute_diffで再利用）
                            diff_cache[k] = ("_normalized", na, nb)
                    else:
                        status = "same"
                matched.append({"key": k, "in_a": in_a, "in_b": in_b, "status": status, "stats": stats, "cat_counts": cat_counts})
            # Image scan (with fallback matching)
            imgs_a = scan_image_folder(state["folder_a"])
            imgs_b = scan_image_folder(state["folder_b"])
            stripped_ia = {_strip_num_prefix(k): k for k in imgs_a}
            stripped_ib = {_strip_num_prefix(k): k for k in imgs_b}
            for sk, orig_a in stripped_ia.items():
                if orig_a not in imgs_b and sk in stripped_ib:
                    orig_b = stripped_ib[sk]
                    if orig_b not in imgs_a:
                        imgs_a[sk] = imgs_a.pop(orig_a)
                        imgs_b[sk] = imgs_b.pop(orig_b)
            img_keys = sorted(set(list(imgs_a.keys()) + list(imgs_b.keys())))
            img_matched = []
            total_imgs = len(img_keys)
            for ii, k in enumerate(img_keys):
                if state.get("scan_abort"): return
                if ii % 5 == 0:
                    try: status_label.value = f"画像比較中... {ii+1}/{total_imgs}"; page.update()
                    except Exception: pass
                in_a = k in imgs_a; in_b = k in imgs_b
                img_status = "only"; diff_pct = 0.0; diff_path = None
                if in_a and in_b:
                    same, diff_pct, diff_path = compare_images(imgs_a[k], imgs_b[k])
                    img_status = "same" if same else "diff"
                img_matched.append({"key": k, "in_a": in_a, "in_b": in_b, "status": img_status,
                                    "diff_pct": diff_pct, "diff_path": diff_path})
            # Atomic state update
            state["files_a"] = files_a
            state["files_b"] = files_b
            state["imgs_a"] = imgs_a
            state["imgs_b"] = imgs_b
            state["review"] = review
            state["matched"] = matched
            state["img_matched"] = img_matched
            state["diff_cache"] = diff_cache
            # Auto-select first diff
            active = matched if state["view_mode"] == "source" else img_matched
            state["selected_key"] = next((m["key"] for m in active if m["status"] == "diff"), None)
            # Now safe to update UI
            src_count = len(matched); img_count = len(img_matched)
            status_label.value = f"ソース: {src_count} | 画像: {img_count}"
            refresh_file_list(False); refresh_diff(False)
        except Exception as x:
            import traceback as _tb
            _flog.error(f"scan: {x}\n{_tb.format_exc()}")
            status_label.value = f"エラー: {x}"
        finally:
            was_aborted = state.get("scan_abort", False)
            state["scanning"] = False
            state["scan_abort"] = False
            if was_aborted:
                status_label.value = "スキャン中断"
            else:
                state["ready"] = True
            try: page.update()
            except Exception: pass

    # ── File list ──
    PAGE_SIZE = 50

    def refresh_file_list(update=True):
        try:
            file_list.controls.clear()
            cnt = {"same": 0, "diff": 0, "only": 0}
            try: filter_mark = mark_filter_dd.value
            except Exception: filter_mark = "all"
            try: filter_status = status_filter_dd.value
            except Exception: filter_status = "all"
            items = state["img_matched"] if state["view_mode"] == "image" else state["matched"]
            # フィルタ適用済みリストを作成
            filtered = []
            for m in items:
                cnt[m["status"]] = cnt.get(m["status"], 0) + 1
                review = state["review"].get(m["key"], {})
                mark = review.get("mark", "unreviewed")
                if filter_mark and filter_mark != "all" and mark != filter_mark: continue
                if filter_status and filter_status != "all" and m["status"] != filter_status: continue
                filtered.append(m)
            # ページネーション
            total_filtered = len(filtered)
            total_pages = max(1, (total_filtered + PAGE_SIZE - 1) // PAGE_SIZE)
            current_page = min(state["list_page"], total_pages - 1)
            state["list_page"] = current_page
            start = current_page * PAGE_SIZE
            page_items = filtered[start:start + PAGE_SIZE]
            if total_pages > 1:
                def _go_page(p):
                    state["list_page"] = p
                    refresh_file_list()
                nav_controls = []
                if current_page > 0:
                    nav_controls.append(ft.TextButton("◀前", on_click=lambda e: _go_page(current_page - 1)))
                nav_controls.append(ft.Text(f"{current_page+1}/{total_pages} ({total_filtered}件)", size=10, color=ft.Colors.GREY_600))
                if current_page < total_pages - 1:
                    nav_controls.append(ft.TextButton("次▶", on_click=lambda e: _go_page(current_page + 1)))
                file_list.controls.append(ft.Row(nav_controls, alignment=ft.MainAxisAlignment.CENTER, spacing=4))
            for m in page_items:
                selected = m["key"] == state["selected_key"]
                if m["status"] == "same": icon = ft.Icon(ft.Icons.CHECK, size=14, color=ft.Colors.GREEN_500)
                elif m["status"] == "diff": icon = ft.Icon(ft.Icons.COMPARE_ARROWS, size=14, color=ft.Colors.ORANGE_600)
                else: icon = ft.Icon(ft.Icons.ARROW_FORWARD if m["in_a"] else ft.Icons.ARROW_BACK, size=14, color=ft.Colors.GREY_500)
                item_review = state["review"].get(m["key"], {})
                item_mark = item_review.get("mark", "unreviewed")
                mark_color = dict((o[0], o[2]) for o in MARK_OPTIONS).get(item_mark, ft.Colors.GREY_400)
                mark_icon = ft.Icon(MARK_ICONS.get(item_mark, ft.Icons.RADIO_BUTTON_UNCHECKED), size=12, color=mark_color)
                sub_parts = []
                if state["view_mode"] == "image":
                    if "diff_pct" in m and m["diff_pct"] >= 0:
                        sub_parts.append(f"差分{m['diff_pct']:.1f}%")
                else:
                    if m.get("stats"):
                        s = m["stats"]
                        meaningful = s.get("change",0) + s.get("add",0) + s.get("del",0) - s.get("noise",0)
                        if meaningful > 0: sub_parts.append(f"差分{meaningful}")
                        if s.get("noise",0): sub_parts.append(f"ノイズ{s['noise']}")
                    if m.get("cat_counts"):
                        for c in ("php_warning", "form", "content", "structural"):
                            if m["cat_counts"].get(c, 0): sub_parts.append(f"{c}:{m['cat_counts'][c]}")
                item_note = item_review.get("note", "")
                if item_note: sub_parts.append(f"memo:{item_note[:15]}")
                subtitle = " | ".join(sub_parts) if sub_parts else ("一致" if m["status"] == "same" else ("差分あり" if m["status"] == "diff" else ""))
                display_name = m["key"]
                if len(display_name) > 50: display_name = "..." + display_name[-47:]
                card = ft.Container(
                    ft.Row([icon, mark_icon,
                        ft.Column([
                            ft.Text(display_name, size=11, weight=ft.FontWeight.BOLD if selected else ft.FontWeight.NORMAL,
                                    color=ft.Colors.BLUE_800 if selected else ft.Colors.BLACK, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(subtitle, size=9, color=ft.Colors.GREY_500),
                        ], spacing=1, expand=True),
                    ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(8, 5, 8, 5), border_radius=4,
                    bgcolor=ft.Colors.BLUE_50 if selected else None,
                    border=ft.Border.all(1, ft.Colors.BLUE_300 if selected else ft.Colors.GREY_200),
                    on_click=lambda e, k=m["key"]: select_file(k))
                file_list.controls.append(card)
            if total_pages > 1:
                nav_controls2 = []
                if current_page > 0:
                    nav_controls2.append(ft.TextButton("◀前", on_click=lambda e: _go_page(current_page - 1)))
                nav_controls2.append(ft.Text(f"{current_page+1}/{total_pages}", size=10, color=ft.Colors.GREY_600))
                if current_page < total_pages - 1:
                    nav_controls2.append(ft.TextButton("次▶", on_click=lambda e: _go_page(current_page + 1)))
                file_list.controls.append(ft.Row(nav_controls2, alignment=ft.MainAxisAlignment.CENTER, spacing=4))
            badge_same.value = str(cnt.get("same", 0))
            badge_diff.value = str(cnt.get("diff", 0))
            badge_only.value = str(cnt.get("only", 0))
            total = len(state["matched"])
            reviewed = sum(1 for m in state["matched"] if state["review"].get(m["key"], {}).get("mark", "unreviewed") != "unreviewed")
            progress_label.value = f"レビュー: {reviewed}/{total}"
            if update: page.update()
        except Exception as x:
            _flog.error(f"refresh_file_list: {x}")

    def select_file(key):
        if state["scanning"]: return
        state["selected_key"] = key
        # 選択したアイテムが表示されるページに移動
        try:
            filter_mark = mark_filter_dd.value
        except Exception: filter_mark = "all"
        try:
            filter_status = status_filter_dd.value
        except Exception: filter_status = "all"
        items = state["img_matched"] if state["view_mode"] == "image" else state["matched"]
        idx = 0
        for m in items:
            review = state["review"].get(m["key"], {})
            mark = review.get("mark", "unreviewed")
            if filter_mark and filter_mark != "all" and mark != filter_mark: continue
            if filter_status and filter_status != "all" and m["status"] != filter_status: continue
            if m["key"] == key:
                state["list_page"] = idx // PAGE_SIZE
                break
            idx += 1
        refresh_file_list(False); refresh_diff(False)
        try: page.update()
        except Exception: pass

    # ── Diff display (B1: uses cache, with safety) ──
    def refresh_diff(update=True):
        try:
            diff_list.controls.clear()
            key = state["selected_key"]
            if not key:
                diff_list.controls.append(ft.Text("ファイルを選択してください", color=ft.Colors.GREY_400))
                if update: page.update()
                return

            # Image mode
            if state["view_mode"] == "image":
                _refresh_image_diff(key, update)
                return

            matched = state["matched"]  # snapshot
            m = next((x for x in matched if x["key"] == key), None)
            if not m:
                if update: page.update()
                return
            review = state["review"].get(key, {})
            try: mark_dd.value = review.get("mark", "unreviewed")
            except Exception: pass
            try: note_field.value = review.get("note", "")
            except Exception: pass
            diff_header.value = key
            if not m.get("in_a") or not m.get("in_b"):
                side = "左のみ" if m.get("in_a") else "右のみ"
                diff_list.controls.append(ft.Text(f"{side}に存在するファイル", size=13, color=ft.Colors.GREY_600))
                if update: page.update()
                return
            # Use cached diff if available
            cached = state["diff_cache"].get(key)
            if cached and cached[0] != "_normalized":
                ops, stats, cat_counts = cached
            else:
                # スキャン時にキャッシュされた正規化テキストがあれば再利用
                if cached and cached[0] == "_normalized":
                    na, nb = cached[1], cached[2]
                    ops, stats, cat_counts = compute_diff_normalized(na, nb)
                else:
                    fa, fb = state["files_a"], state["files_b"]
                    src = state["src_type"]
                    fa_entry = fa.get(key, {}); fb_entry = fb.get(key, {})
                    pa = _get_file_path(fa_entry, src)
                    pb = _get_file_path(fb_entry, src)
                    ta = read_file(pa) if pa else ""; tb = read_file(pb) if pb else ""
                    ops, stats, cat_counts = compute_diff(ta, tb)
                state["diff_cache"][key] = (ops, stats, cat_counts)
                # matchedリストのstats/cat_countsも更新
                if m: m["stats"] = stats; m["cat_counts"] = cat_counts
            try: ctx = int(ctx_dd.value)
            except Exception: ctx = 3
            try: show_noise = noise_cb.value
            except Exception: show_noise = False
            php_warn = stats.get('php_warning', 0)
            summary = f"一致: {stats['same']} | 変更: {stats['change']} | 追加: {stats['add']} | 削除: {stats['del']} | ノイズ除外: {stats['noise']}"
            if php_warn: summary += f" | ⚠ PHP警告: {php_warn}"
            if cat_counts:
                cats = " | ".join(f"{c}:{n}" for c, n in cat_counts.items() if n > 0 and c != "noise")
                if cats: summary += f" | {cats}"
            diff_summary.value = summary
            diff_summary.color = ft.Colors.GREY_600
            visible_indices = set()
            for i, op in enumerate(ops):
                if op[0] != '=':
                    if op[5] == "noise" and not show_noise: continue
                    for j in range(max(0, i-ctx), min(len(ops), i+ctx+1)):
                        visible_indices.add(j)
            if ctx == 0: visible_indices = set(range(len(ops)))
            MAX_DISPLAY = 500  # 表示行数上限
            display_count = 0
            last_shown = -1
            for i, op in enumerate(ops):
                if i not in visible_indices: continue
                if display_count >= MAX_DISPLAY:
                    remaining = sum(1 for j in visible_indices if j > i)
                    diff_list.controls.append(ft.Container(
                        ft.Text(f"... 残り {remaining} 行（表示上限 {MAX_DISPLAY} 行）...", size=11, color=ft.Colors.ORANGE_700, text_align=ft.TextAlign.CENTER),
                        bgcolor=ft.Colors.ORANGE_50, padding=4))
                    break
                if last_shown >= 0 and i - last_shown > 1:
                    diff_list.controls.append(ft.Container(
                        ft.Text(f"... {i - last_shown - 1} 行省略 ...", size=10, color=ft.Colors.GREY_400, text_align=ft.TextAlign.CENTER),
                        bgcolor=ft.Colors.GREY_100, padding=2))
                last_shown = i
                display_count += 1
                typ, la_idx, lb_idx, la, lb, cat = op
                ln_a = str(la_idx + 1) if la_idx is not None else ""
                ln_b = str(lb_idx + 1) if lb_idx is not None else ""
                if typ == '=':
                    diff_list.controls.append(ft.Container(
                        ft.Row([ft.Text(ln_a, size=10, color=ft.Colors.GREY_400, width=40, text_align=ft.TextAlign.RIGHT),
                                ft.Text(la.rstrip('\n') if la else "", size=10, font_family="Consolas", expand=True, selectable=True)],
                               spacing=4), padding=ft.Padding(4, 0, 4, 0)))
                elif typ == '~':
                    cat_color = CAT_COLORS.get(cat, ft.Colors.GREY_100)
                    cat_label = f" [{cat}]" if cat else ""
                    del_color = CAT_TEXT_DEL.get(cat, ft.Colors.RED_700)
                    add_color = CAT_TEXT_ADD.get(cat, ft.Colors.GREEN_700)
                    diff_list.controls.append(ft.Container(
                        ft.Column([
                            ft.Row([ft.Text(ln_a, size=10, color=ft.Colors.GREY_400, width=40, text_align=ft.TextAlign.RIGHT),
                                    ft.Text(f"- {la}{cat_label}", size=10, font_family="Consolas", color=del_color, expand=True, selectable=True)], spacing=4),
                            ft.Row([ft.Text(ln_b, size=10, color=ft.Colors.GREY_400, width=40, text_align=ft.TextAlign.RIGHT),
                                    ft.Text(f"+ {lb}{cat_label}", size=10, font_family="Consolas", color=add_color, expand=True, selectable=True)], spacing=4),
                        ], spacing=0), bgcolor=cat_color, padding=ft.Padding(4, 2, 4, 2), border_radius=2))
                elif typ == '-':
                    cat_label = f" [{cat}]" if cat else ""
                    del_color = CAT_TEXT_DEL.get(cat, ft.Colors.RED_700)
                    diff_list.controls.append(ft.Container(
                        ft.Row([ft.Text(ln_a, size=10, color=ft.Colors.GREY_400, width=40, text_align=ft.TextAlign.RIGHT),
                                ft.Text(f"- {la}{cat_label}", size=10, font_family="Consolas", color=del_color, expand=True, selectable=True)],
                               spacing=4), bgcolor=CAT_COLORS.get(cat, ft.Colors.RED_50), padding=ft.Padding(4, 0, 4, 0)))
                elif typ == '+':
                    cat_label = f" [{cat}]" if cat else ""
                    add_color = CAT_TEXT_ADD.get(cat, ft.Colors.GREEN_700)
                    diff_list.controls.append(ft.Container(
                        ft.Row([ft.Text(ln_b, size=10, color=ft.Colors.GREY_400, width=40, text_align=ft.TextAlign.RIGHT),
                                ft.Text(f"+ {lb}{cat_label}", size=10, font_family="Consolas", color=add_color, expand=True, selectable=True)],
                               spacing=4), bgcolor=CAT_COLORS.get(cat, ft.Colors.GREEN_50), padding=ft.Padding(4, 0, 4, 0)))
            if not diff_list.controls:
                diff_list.controls.append(ft.Text("差分なし（ノイズ除外後一致）", size=13, color=ft.Colors.GREEN_600))
            if update: page.update()
        except Exception as x:
            import traceback as _tb
            _flog.error(f"refresh_diff: {x}\n{_tb.format_exc()}")
            diff_list.controls.clear()
            diff_list.controls.append(ft.Text(f"差分表示エラー: {x}", color=ft.Colors.RED_600))
            if update:
                try: page.update()
                except Exception: pass

    # ── Image diff display ──
    def _refresh_image_diff(key, update=True):
        try:
            diff_list.controls.clear()
            items = state["img_matched"]
            m = next((x for x in items if x["key"] == key), None)
            if not m:
                if update: page.update()
                return
            review = state["review"].get(key, {})
            try: mark_dd.value = review.get("mark", "unreviewed")
            except Exception: pass
            try: note_field.value = review.get("note", "")
            except Exception: pass
            diff_header.value = key
            pct = m.get("diff_pct", 0)
            if m["status"] == "same":
                diff_summary.value = "完全一致"
                diff_summary.color = ft.Colors.GREEN_700
                diff_list.controls.append(ft.Container(
                    ft.Column([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, size=48, color=ft.Colors.GREEN_500),
                        ft.Text("完全一致", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                        ft.Text("ピクセル単位で差分なし", size=12, color=ft.Colors.GREY_500),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    padding=30))
            elif pct < 1:
                diff_summary.value = f"微差: {pct:.2f}%"
                diff_summary.color = ft.Colors.ORANGE_700
            else:
                diff_summary.value = f"差分: {pct:.1f}%"
                diff_summary.color = ft.Colors.RED_700

            # Show images
            imgs_a = state["imgs_a"]; imgs_b = state["imgs_b"]
            if m.get("in_a") and key in imgs_a:
                diff_list.controls.append(ft.Text("ベース (旧)", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_600))
                diff_list.controls.append(ft.Image(src=imgs_a[key], width=700, fit="contain", border_radius=4))
            if m.get("in_b") and key in imgs_b:
                diff_list.controls.append(ft.Text("比較対象 (新)", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_600))
                diff_list.controls.append(ft.Image(src=imgs_b[key], width=700, fit="contain", border_radius=4))
            if m.get("diff_path") and os.path.isfile(m["diff_path"]):
                diff_list.controls.append(ft.Text("差分ハイライト (赤=変更箇所)", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.RED_600))
                diff_list.controls.append(ft.Image(src=m["diff_path"], width=700, fit="contain", border_radius=4))
            if m["status"] == "diff" and m.get("in_a") and m.get("in_b"):
                try:
                    from PIL import Image as _PILImg
                    sa = _PILImg.open(imgs_a[key]).size
                    sb = _PILImg.open(imgs_b[key]).size
                    if sa != sb:
                        diff_list.controls.append(ft.Text(f"サイズ差: {sa[0]}x{sa[1]} → {sb[0]}x{sb[1]}", size=12, color=ft.Colors.ORANGE_700))
                except Exception: pass
            if update: page.update()
        except Exception as x:
            _flog.error(f"_refresh_image_diff: {x}")
            diff_list.controls.clear()
            diff_list.controls.append(ft.Text(f"画像表示エラー: {x}", color=ft.Colors.RED_600))
            if update:
                try: page.update()
                except Exception: pass

    # ── Review actions ──
    def on_mark_change(e):
        try:
            key = state["selected_key"]
            if not key: return
            state["review"].setdefault(key, {})["mark"] = mark_dd.value or "unreviewed"
            save_review(state["folder_b"], state["review"])
            refresh_file_list(False); page.update()
        except Exception as x: _flog.error(f"on_mark_change: {x}")

    def on_note_change(e):
        try:
            key = state["selected_key"]
            if not key: return
            state["review"].setdefault(key, {})["note"] = note_field.value or ""
            save_review(state["folder_b"], state["review"])
        except Exception as x: _flog.error(f"on_note_change: {x}")

    def _find_diff_file(direction):
        """Find next/prev file with diff status, respecting active filters. direction: 1=next, -1=prev."""
        matched = state["img_matched"] if state["view_mode"] == "image" else state["matched"]
        if not matched: return None
        try: filter_mark = mark_filter_dd.value
        except Exception: filter_mark = "all"
        try: filter_status = status_filter_dd.value
        except Exception: filter_status = "all"
        # フィルタ適用済みリストを作成
        visible = []
        for m in matched:
            rv = state["review"].get(m["key"], {})
            mk = rv.get("mark", "unreviewed")
            if filter_mark and filter_mark != "all" and mk != filter_mark: continue
            if filter_status and filter_status != "all" and m["status"] != filter_status: continue
            visible.append(m)
        if not visible: return None
        sel = state["selected_key"]
        idx = next((i for i, m in enumerate(visible) if m["key"] == sel), -1)
        start = idx + direction
        end = len(visible) if direction > 0 else -1
        if start < 0 or start >= len(visible): return None
        for i in range(start, end, direction):
            if 0 <= i < len(visible) and visible[i].get("status") == "diff":
                return visible[i]["key"]
        return None

    def on_next(e):
        key = _find_diff_file(1)
        if key: select_file(key)
        else: snack("最後の差分ファイルです", ft.Colors.ORANGE_700)

    # B4: Previous button
    def on_prev(e):
        key = _find_diff_file(-1)
        if key: select_file(key)
        else: snack("最初の差分ファイルです", ft.Colors.ORANGE_700)

    def on_mark_ok_next(e):
        try:
            key = state["selected_key"]
            if key:
                state["review"].setdefault(key, {})["mark"] = "ok"
                save_review(state["folder_b"], state["review"])
            on_next(e)
        except Exception as x: _flog.error(f"on_mark_ok_next: {x}")

    # B3: Mark all same files as OK
    def mark_all_same_ok(e):
        count = 0
        # ソースと画像の両方を対象にする
        for items in [state["matched"], state["img_matched"]]:
            for m in items:
                if m["status"] == "same":
                    r = state["review"].setdefault(m["key"], {})
                    if r.get("mark", "unreviewed") == "unreviewed":
                        r["mark"] = "ok"
                        count += 1
        save_review(state["folder_b"], state["review"])
        refresh_file_list(); snack(f"一致ファイル {count} 件を OK にマーク")

    # B6: Enhanced report (HTML format)
    def export_report(e):
        from html import escape as _h
        ts = datetime.now().strftime('%Y-%m-%d %H:%M')
        total = len(state["matched"])
        reviewed = sum(1 for m in state["matched"] if state["review"].get(m["key"], {}).get("mark", "unreviewed") != "unreviewed")
        html_parts = [
            '<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">',
            f'<title>y-diff レビューレポート {ts}</title>',
            '<style>body{font-family:sans-serif;max-width:1000px;margin:0 auto;padding:20px}',
            'h1{color:#00695C}h2{border-bottom:2px solid #ddd;padding-bottom:4px;margin-top:24px}',
            'table{border-collapse:collapse;width:100%;margin:12px 0}th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;font-size:13px}',
            'th{background:#E0F2F1}.ok{color:#2E7D32}.problem{color:#C62828}.check{color:#E65100}.noise{color:#1565C0}.unreviewed{color:#9E9E9E}',
            '.stats{display:flex;gap:20px;margin:12px 0;font-size:14px}',
            '</style></head><body>',
            f'<h1>y-diff レビューレポート</h1>',
            f'<p>日時: {ts}<br>ベース: {_h(state["folder_a"])}<br>比較: {_h(state["folder_b"])}</p>',
            f'<div class="stats"><span>合計: {total}</span><span>レビュー済: {reviewed}/{total}</span></div>',
        ]
        for mark_key, mark_label, _ in MARK_OPTIONS:
            items = [m for m in state["matched"] if state["review"].get(m["key"], {}).get("mark", "unreviewed") == mark_key]
            if not items: continue
            html_parts.append(f'<h2 class="{mark_key}">{mark_label} ({len(items)}件)</h2><table><tr><th>ファイル</th><th>差分</th><th>カテゴリ</th><th>メモ</th></tr>')
            for m in items:
                note = state["review"].get(m["key"], {}).get("note", "")
                s = m.get("stats") or {}
                diff_str = f"変更{s.get('change',0)} 追加{s.get('add',0)} 削除{s.get('del',0)}" if s else "-"
                cc = m.get("cat_counts") or {}
                cat_str = ", ".join(f"{c}:{n}" for c, n in cc.items() if n > 0) if cc else "-"
                html_parts.append(f'<tr><td>{_h(m["key"])}</td><td>{_h(diff_str)}</td><td>{_h(cat_str)}</td><td>{_h(note)}</td></tr>')
            html_parts.append('</table>')
        html_parts.append('</body></html>')
        report_dir = os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv else __file__))
        fp = os.path.join(report_dir, f"review_report_{datetime.now().strftime('%Y%m%d%H%M')}.html")
        try:
            with open(fp, 'w', encoding='utf-8') as f: f.write('\n'.join(html_parts))
            snack(f"レポート出力: {fp}")
        except Exception as x:
            snack(f"出力失敗: {x}", ft.Colors.RED_700)

    # B7: Rescan button
    def rescan(e):
        if state["folder_a"] and state["folder_b"]:
            state["selected_key"] = None; do_scan()
        else: snack("フォルダを選択してください", ft.Colors.ORANGE_700)

    def on_src_type_change(e):
        state["src_type"] = src_type_dd.value
        state["diff_cache"].clear()
        if state["folder_a"] and state["folder_b"]: do_scan()

    def on_view_mode_change(e):
        state["view_mode"] = view_mode_dd.value
        state["selected_key"] = None
        refresh_file_list(False); refresh_diff(False); page.update()

    def on_ctx_change(e): refresh_diff()
    def on_noise_change(e): refresh_diff()

    # B4: Keyboard shortcuts (guarded)
    def on_keyboard(e: ft.KeyboardEvent):
        if state["scanning"] or not state["ready"]: return
        try:
            key = e.key; ctrl = e.ctrl or e.meta
            if key.lower() == 'n' and not ctrl: on_next(None)
            elif key.lower() == 'p' and not ctrl: on_prev(None)
            elif key.lower() == 'o' and not ctrl: on_mark_ok_next(None)
            elif key.lower() == 'e' and ctrl: export_report(None)
            elif key.lower() == 'r' and ctrl: rescan(None)
        except Exception: pass
    page.on_keyboard_event = on_keyboard

    # ── Build controls ──
    _recent = _scan_recent_folders()
    _recent_opts = [ft.dropdown.Option(key=p, text=os.path.basename(p)) for p in _recent]
    folder_a_field = ft.TextField(label="パス", expand=True, dense=True, hint_text="y-shot出力フォルダのパスを貼り付け", on_submit=lambda e: _apply_folder('A'))
    folder_b_field = ft.TextField(label="パス", expand=True, dense=True, hint_text="y-shot出力フォルダのパスを貼り付け", on_submit=lambda e: _apply_folder('B'))
    recent_dd_a = ft.Dropdown(label="履歴", width=220, dense=True, options=list(_recent_opts), on_select=lambda e: _on_recent_select('A', e))
    recent_dd_b = ft.Dropdown(label="履歴", width=220, dense=True, options=list(_recent_opts), on_select=lambda e: _on_recent_select('B', e))
    folder_a_label = ft.Text("", size=11, color=ft.Colors.GREY_500)
    folder_b_label = ft.Text("", size=11, color=ft.Colors.GREY_500)
    status_label = ft.Text("", size=11, color=ft.Colors.GREY_500)
    progress_label = ft.Text("", size=11, color=ft.Colors.TEAL_700)
    badge_same = ft.Text("0", size=11, color=ft.Colors.GREEN_600)
    badge_diff = ft.Text("0", size=11, color=ft.Colors.ORANGE_600)
    badge_only = ft.Text("0", size=11, color=ft.Colors.GREY_500)

    mark_filter_dd = ft.Dropdown(label="判定", width=130, dense=True, value="all",
        options=[ft.dropdown.Option(key="all", text="すべて")] + [ft.dropdown.Option(key=m[0], text=m[1]) for m in MARK_OPTIONS],
        on_select=lambda e: refresh_file_list())
    status_filter_dd = ft.Dropdown(label="状態", width=120, dense=True, value="all",
        options=[ft.dropdown.Option(key="all", text="すべて"),
                 ft.dropdown.Option(key="diff", text="差分あり"),
                 ft.dropdown.Option(key="same", text="一致"),
                 ft.dropdown.Option(key="only", text="片方のみ")],
        on_select=lambda e: refresh_file_list())

    file_list = ft.ListView(controls=[], spacing=2, expand=True)
    diff_header = ft.Text("", size=13, weight=ft.FontWeight.BOLD, selectable=True)
    diff_summary = ft.Text("", size=11, color=ft.Colors.GREY_600)
    diff_list = ft.ListView(controls=[], spacing=0, expand=True)

    mark_dd = ft.Dropdown(label="判定", width=160, dense=True, value="unreviewed",
        options=[ft.dropdown.Option(key=m[0], text=m[1]) for m in MARK_OPTIONS],
        on_select=on_mark_change)
    note_field = ft.TextField(label="メモ", expand=True, dense=True, on_blur=on_note_change, on_submit=on_note_change)
    src_type_dd = ft.Dropdown(label="ソース種別", width=130, dense=True, value="dom",
        options=[ft.dropdown.Option(key="dom", text="DOM"), ft.dropdown.Option(key="raw", text="Raw")],
        on_select=on_src_type_change)
    ctx_dd = ft.Dropdown(label="前後行", width=120, dense=True, value="3",
        options=[ft.dropdown.Option(key="3", text="3行"), ft.dropdown.Option(key="5", text="5行"),
                 ft.dropdown.Option(key="10", text="10行"), ft.dropdown.Option(key="0", text="全行")],
        on_select=on_ctx_change)
    noise_cb = ft.Checkbox(label="ノイズも表示", value=False, on_change=on_noise_change)
    view_mode_dd = ft.Dropdown(label="比較モード", width=140, dense=True, value="source",
        options=[ft.dropdown.Option(key="source", text="ソース比較"), ft.dropdown.Option(key="image", text="画像比較")],
        on_select=on_view_mode_change)

    # ── Layout ──
    page.appbar = ft.AppBar(
        title=ft.Text(APP_NAME, weight=ft.FontWeight.BOLD), center_title=False, bgcolor=ft.Colors.TEAL_50,
        actions=[
            ft.TextButton("再スキャン", icon=ft.Icons.REFRESH, on_click=rescan),
            ft.Button("レポート出力", icon=ft.Icons.DESCRIPTION, on_click=export_report),
        ])

    page.add(ft.Column([
        ft.Column([
            ft.Row([ft.Text("旧", size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_600, width=20),
                    folder_a_field, recent_dd_a],
                   spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([ft.Text("新", size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_600, width=20),
                    folder_b_field, recent_dd_b],
                   spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Row([ft.ElevatedButton("実行", icon=ft.Icons.PLAY_ARROW,
                        on_click=lambda e: ((_apply_folder('A'), _apply_folder('B'), do_scan()) if not state["scanning"] else do_scan())),
                    view_mode_dd,
                    status_label, progress_label,
                    ft.Text("N=次 P=前 O=OK→次", size=9, color=ft.Colors.GREY_400)], spacing=12),
        ], spacing=2),
        ft.Divider(height=1),
        ft.Row([
            ft.Container(ft.Column([
                ft.Row([ft.Text("ファイル", weight=ft.FontWeight.BOLD, size=12),
                        ft.Row([ft.Icon(ft.Icons.CHECK, size=10, color=ft.Colors.GREEN_500), badge_same,
                                ft.Icon(ft.Icons.COMPARE_ARROWS, size=10, color=ft.Colors.ORANGE_600), badge_diff,
                                ft.Text("他", size=9), badge_only], spacing=3)],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([mark_filter_dd, status_filter_dd], spacing=4),
                ft.OutlinedButton("一致を一括OK", icon=ft.Icons.CHECK_CIRCLE, on_click=mark_all_same_ok),
                file_list,
            ], spacing=4), width=300, padding=6, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),
            ft.Column([
                ft.Container(ft.Column([
                    diff_header, diff_summary,
                    ft.Row([mark_dd, note_field], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Row([
                        ft.Button("OK→次", icon=ft.Icons.CHECK, bgcolor=ft.Colors.GREEN_600, color=ft.Colors.WHITE, on_click=on_mark_ok_next, height=32),
                        ft.Button("前", icon=ft.Icons.NAVIGATE_BEFORE, on_click=on_prev, height=32),
                        ft.Button("次", icon=ft.Icons.NAVIGATE_NEXT, on_click=on_next, height=32),
                        src_type_dd, ctx_dd, noise_cb,
                    ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
                ], spacing=4), padding=6, border=ft.Border.all(1, ft.Colors.GREY_300), border_radius=8),
                ft.Container(diff_list, expand=True, padding=4, border=ft.Border.all(1, ft.Colors.GREY_200), border_radius=4),
            ], expand=True, spacing=4),
        ], spacing=6, expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
    ], expand=True, spacing=4))

if __name__ == "__main__":
    ft.run(main)
