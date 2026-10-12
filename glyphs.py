"""Template reader for the game's own font. Tesseract can't read it, but the font never changes, so we
cut text into characters and match each against saved reference shapes (glyphs/ folder)."""
import glob, os, re
import cv2, numpy as np
import config
from ocr_time import parse_time

W, H = 16, 24
_NAME = re.compile(r"^(.)_(\d+)_([\d.]+)_([\d.]+)\.png$")
_lib = None

def white_mask(img, vmin=190, smax=70):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return ((hsv[..., 2] > vmin) & (hsv[..., 1] < smax)).astype(np.uint8) * 255

def _tight(sub):
    """Crop a 0/1 mask to its ink. -> (mask, dx, dy) or (None, 0, 0) if empty."""
    ys, xs = np.nonzero(sub)
    if len(xs) == 0:
        return None, 0, 0
    return sub[ys.min():ys.max() + 1, xs.min():xs.max() + 1], int(xs.min()), int(ys.min())

def _make(sub, x, y, hmax):
    h, w = sub.shape
    g = cv2.resize(sub.astype(np.uint8) * 255, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    return {"img": g, "rel": h / hmax, "ar": w / h, "x": x, "box": (x, y, w, h), "mask": sub, "hmax": hmax}

def segment(img):
    """-> glyphs left to right: dicts with a normalised image, height relative to the tallest, aspect."""
    m = white_mask(img)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    comps = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in st[i])
        if a < 5 or h / max(w, 1) > 8:        # specks and thin panel borders
            continue
        comps.append((x, y, w, h, i))
    if not comps:
        return []
    hmax = max(c[3] for c in comps)
    out = []
    for x, y, w, h, i in comps:
        if h < 0.5 * hmax:
            continue
        sub = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        out.append(_make(sub, x, y, hmax))
    return sorted(out, key=lambda g: g["x"])

def load(force=False):
    global _lib
    if _lib is None or force:
        _lib = []
        for p in glob.glob(os.path.join(config.GLYPH_DIR, "*.png")):
            m = _NAME.match(os.path.basename(p))
            if m:
                g = cv2.imread(p, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
                _lib.append((m.group(1), g, float(m.group(3)), float(m.group(4))))
    return _lib

def dist(g, t):
    return float(np.abs(g["img"] - t[1]).mean()) + config.GLYPH_W_REL * abs(g["rel"] - t[2]) \
        + config.GLYPH_W_AR * abs(g["ar"] - t[3])

def classify(g, lib=None):
    best = (9.9, "?")
    for t in (lib if lib is not None else load()):
        d = dist(g, t)
        if d < best[0]:
            best = (d, t[0])
    return best[1], best[0]

def _read_blob(sub, x, y, hmax, depth=0):
    """Read one blob. If it matches nothing, it may be neighbours fused together (no dark outline between them):
    try every cut position and keep the one where BOTH halves read as real characters. -> (text, distance)"""
    ch, d = classify(_make(sub, x, y, hmax))
    if d <= config.GLYPH_MAX_DIST:
        return ch, d
    if depth >= 2:
        return "?", d
    h, w = sub.shape
    best = None
    for c in range(2, w - 1):                          # cut between column c-1 and c
        parts = []
        for part, px in ((sub[:, :c], x), (sub[:, c:], x + c)):
            t, dx, dy = _tight(part)
            if t is None or t.shape[1] < 3 or t.shape[0] < 0.4 * hmax:
                parts = None
                break
            parts.append((t, px + dx, y + dy))
        if not parts:
            continue
        res = [_read_blob(t, px, py, hmax, depth + 1) for t, px, py in parts]
        if all("?" not in r[0] for r in res):
            score = max(r[1] for r in res)
            if best is None or score < best[1]:
                best = ("".join(r[0] for r in res), score)
    return best if best else ("?", d)

def read_text(img):
    """-> (text, worst_distance). Characters that don't match anything well come back as '?'."""
    text, worst = "", 0.0
    for gl in segment(img):
        ch, d = classify(gl)
        if d > config.GLYPH_MAX_DIST and gl["box"][2] >= 0.9 * gl["hmax"]:     # wide enough to be two characters
            ch, d = _read_blob(gl["mask"], gl["x"], gl["box"][1], gl["hmax"])
        worst = max(worst, d)
        text += ch if d <= config.GLYPH_MAX_DIST else "?"
    return text, worst

def read_time(img):
    """-> (text, seconds or None, worst_distance)"""
    text, worst = read_text(img)
    return text, parse_time(text), worst

def save_glyphs(img, chars):
    """Used by learn_glyphs.py: store each segmented glyph under its character. Returns count saved."""
    gl = segment(img)
    if len(gl) != len(chars):
        return -1
    os.makedirs(config.GLYPH_DIR, exist_ok=True)
    for g, ch in zip(gl, chars):
        k = len(glob.glob(os.path.join(config.GLYPH_DIR, f"{ch}_*.png")))
        name = f"{ch}_{k}_{g['rel']:.2f}_{g['ar']:.2f}.png"
        cv2.imwrite(os.path.join(config.GLYPH_DIR, name), (g["img"] * 255).astype(np.uint8))
    load(force=True)
    return len(gl)
