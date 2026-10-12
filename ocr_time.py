"""Read remaining-time text like '2d 3h', '5h 12m', '40m 10s' from a cropped screenshot (needs Tesseract)."""
import re, cv2, numpy as np
import config

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
except ImportError:
    pytesseract = None

_ok = None
UNITS = {"d": 86400, "h": 3600, "m": 60, "s": 1}
LIMITS = {"d": 90, "h": 23, "m": 59, "s": 59}
ORDER = "dhms"
# Characters this font/OCR commonly returns in place of a digit
DIGITLIKE = {"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "Z": "2", "z": "2", "e": "2", "E": "2", "B": "8"}
_N = r"[0-9OoIl|ZzeEB]{1,2}"
# The WHOLE line must be one or two time tokens, e.g. "55s", "2m 51s", "5h 12m", "2d 3h" (that is how the game prints them)
STRICT = re.compile(rf"^\s*({_N})\s*([dhmsDHMS])(?:\s*({_N})\s*([dhmsDHMS]))?\s*$")

def available():
    global _ok
    if _ok is None:
        try:
            pytesseract.get_tesseract_version()
            _ok = True
        except Exception:
            _ok = False
    return _ok

def parse_time(line):
    m = STRICT.match(line)
    if not m:
        return None
    pairs = [(m.group(1), m.group(2))]
    if m.group(3):
        pairs.append((m.group(3), m.group(4)))
    if not any(ch.isdigit() for n, _ in pairs for ch in n):
        return None                      # only look-alike letters, no real digit
    total, prev = 0, None
    for n, u in pairs:
        u = u.lower()
        n = "".join(DIGITLIKE.get(ch, ch) for ch in n)
        if not n.isdigit() or int(n) > LIMITS[u]:
            return None                  # e.g. "120m" or "75s" never appear in the game
        if prev is not None and ORDER.index(u) != ORDER.index(prev) + 1:
            return None                  # must be consecutive units: d h / h m / m s
        prev = u
        total += int(n) * UNITS[u]
    return total if total > 0 else None

def _prep(img, mode):
    if mode == "white":        # bright, unsaturated pixels = white text
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        m = ((hsv[..., 2] > 190) & (hsv[..., 1] < 70)).astype(np.uint8) * 255
        m = cv2.resize(m, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        return 255 - m
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    return cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

def find_times(img):
    """-> (found [(line, seconds)], raw_lines, preprocessed_image)
    Reads only the right-hand time column, digits + d/h/m/s allowed, and keeps lines that are purely a time."""
    W = img.shape[1]
    col = img[:, int(W * config.TIME_COLUMN_START):]
    lines, prep = [], None
    for mode in ("white", "gray"):
        prep = _prep(col, mode)
        text = pytesseract.image_to_string(prep, config="--psm 6 -c tessedit_char_whitelist=0123456789dhmsDHM")
        lines = [l for l in text.splitlines() if l.strip()]
        found = [(l, parse_time(l)) for l in lines]
        found = [(l, t) for l, t in found if t is not None]
        if found:
            return found, lines, prep
    return [], lines, prep


def fmt(secs):
    d, r = divmod(int(secs), 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return " ".join(f"{v}{u}" for v, u in ((d, "d"), (h, "h"), (m, "m"), (s, "s")) if v) or "0s"
