import ctypes, random, time
from ctypes import wintypes
import config

user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, MK_LBUTTON = 0x0200, 0x0201, 0x0202, 0x0001

class _Pt(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def _setup():
    if user32 is None:
        return
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(_Pt)]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_setup()

def make_lparam(x, y):
    return ((int(y) & 0xFFFF) << 16) | (int(x) & 0xFFFF)

def class_name(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, buf, 256)
    return buf.value

def list_windows(top):
    """The top-level window and all its child windows: [(hwnd, class, width, height, visible)]."""
    out = []
    def row(h):
        r = wintypes.RECT()
        user32.GetClientRect(h, ctypes.byref(r))
        return (h, class_name(h), r.right, r.bottom, bool(user32.IsWindowVisible(h)))
    out.append(row(top))
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(top, CB(lambda h, _: out.append(row(h)) or True), 0)
    return out

def pick_target(top):
    """Window that should receive clicks: TARGET_CLASS if set, else the biggest visible child (the render surface)."""
    wins = list_windows(top)
    if config.TARGET_CLASS:
        for h, cls, w, hgt, vis in wins:
            if cls == config.TARGET_CLASS:
                return h
    kids = [x for x in wins[1:] if x[4] and x[2] * x[3] >= 0.25 * wins[0][2] * wins[0][3]]
    return max(kids, key=lambda x: x[2] * x[3])[0] if kids else top

class Input:
    """INPUT_MODE "postmessage": posts mouse messages straight to the game window. The cursor never moves and the
    window doesn't need focus. "cursor": the old behaviour (real mouse movement)."""

    def __init__(self, window, mode=None, target=None):
        self.win = window
        self.mode = mode or config.INPUT_MODE
        self.target = None
        self._pdi = None
        if self.mode == "cursor":
            import pydirectinput
            pydirectinput.PAUSE = 0.03
            self._pdi = pydirectinput
        else:
            self.target = target or pick_target(self.win.hwnd)

    # ---- geometry ----
    def size(self):
        if self.win.last_shape:
            return self.win.last_shape[1], self.win.last_shape[0]
        return self.win.win.width, self.win.win.height

    def frac(self, fx, fy):
        w, h = self.size()
        return int(w * fx), int(h * fy)

    def _client(self, x, y):
        """Frame pixel -> client coordinates of the target window (no cursor involved)."""
        ox, oy = self.win.frame_origin()
        pt = _Pt(int(ox + x), int(oy + y))
        user32.ScreenToClient(self.target, ctypes.byref(pt))
        return pt.x, pt.y

    def _post(self, msg, wparam, x, y):
        user32.PostMessageW(self.target, msg, wparam, make_lparam(x, y))

    # ---- actions ----
    def click(self, x, y):
        j = config.CLICK_JITTER
        x, y = x + random.randint(-j, j), y + random.randint(-j, j)
        if self.mode == "cursor":
            ox, oy = self.win.origin()
            self._pdi.moveTo(ox + x, oy + y)
            time.sleep(random.uniform(0.05, 0.15))
            self._pdi.click()
            return
        cx, cy = self._client(x, y)
        self._post(WM_MOUSEMOVE, 0, cx, cy)
        time.sleep(random.uniform(0.03, 0.08))
        self._post(WM_LBUTTONDOWN, MK_LBUTTON, cx, cy)
        time.sleep(random.uniform(0.05, 0.12))
        self._post(WM_LBUTTONUP, 0, cx, cy)

    def drag(self, x1, y1, x2, y2, duration=0.5, steps=12):
        if self.mode == "cursor":
            ox, oy = self.win.origin()
            self._pdi.moveTo(ox + x1, oy + y1)
            time.sleep(0.1)
            self._pdi.mouseDown()
            for i in range(1, steps + 1):
                self._pdi.moveTo(int(ox + x1 + (x2 - x1) * i / steps), int(oy + y1 + (y2 - y1) * i / steps))
                time.sleep(duration / steps)
            self._pdi.mouseUp()
            return
        cx, cy = self._client(x1, y1)
        self._post(WM_MOUSEMOVE, 0, cx, cy)
        time.sleep(0.05)
        self._post(WM_LBUTTONDOWN, MK_LBUTTON, cx, cy)
        for i in range(1, steps + 1):
            px, py = self._client(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
            self._post(WM_MOUSEMOVE, MK_LBUTTON, px, py)
            time.sleep(duration / steps)
        self._post(WM_LBUTTONUP, 0, px, py)
