import ctypes, time
from ctypes import wintypes
import cv2, mss, numpy as np
import pygetwindow as gw
import config

class GameWindow:
    """Finds the game window and grabs frames from it.
    CAPTURE_MODE: "mss" (screen pixels: window must be visible), "printwindow" or "wgc" (work while covered)."""

    def __init__(self, title, mode=None):
        wins = [w for w in gw.getWindowsWithTitle(title) if w.title.strip()]
        if not wins:
            raise RuntimeError(f"No window found with title containing '{title}'")
        self.win = wins[0]
        self.hwnd = self.win._hWnd
        self.mode = mode or config.CAPTURE_MODE
        self.sct = mss.mss()
        self.last_shape = None
        self._latest = None
        self._wgc = None
        if self.mode == "wgc":
            self._start_wgc()

    # ---- geometry ----
    def region(self):
        w = self.win
        return {"left": w.left, "top": w.top, "width": w.width, "height": w.height}

    def origin(self):
        return self.win.left, self.win.top

    def _ext_bounds(self):
        r = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(self.hwnd), 9, ctypes.byref(r), ctypes.sizeof(r))
        return r

    def frame_origin(self):
        """Screen position of the captured frame's top-left pixel (clicks are measured from here)."""
        if self.mode == "wgc" and self._latest is not None:
            try:
                r = self._ext_bounds()
                if (r.bottom - r.top, r.right - r.left) == self._latest.shape[:2]:
                    return r.left, r.top
            except Exception:
                pass
        return self.origin()

    # ---- capture ----
    def grab(self):
        if self.mode == "printwindow":
            img = self._printwindow()
        elif self.mode == "wgc":
            img = self._wgc_frame()
        else:
            img = cv2.cvtColor(np.array(self.sct.grab(self.region())), cv2.COLOR_BGRA2BGR)
        self.last_shape = img.shape[:2]
        return img

    def _printwindow(self):
        import win32gui, win32ui
        l, t, r, b = win32gui.GetWindowRect(self.hwnd)
        w, h = r - l, b - t
        hdc = win32gui.GetWindowDC(self.hwnd)
        mfc = win32ui.CreateDCFromHandle(hdc)
        save = mfc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc, w, h)
        save.SelectObject(bmp)
        ctypes.windll.user32.PrintWindow(self.hwnd, save.GetSafeHdc(), 2)   # 2 = PW_RENDERFULLCONTENT
        img = np.frombuffer(bmp.GetBitmapBits(True), np.uint8).reshape(h, w, 4).copy()
        win32gui.DeleteObject(bmp.GetHandle())
        save.DeleteDC(); mfc.DeleteDC(); win32gui.ReleaseDC(self.hwnd, hdc)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def _start_wgc(self):
        from windows_capture import WindowsCapture      # pip install windows-capture
        try:
            cap = WindowsCapture(cursor_capture=False, draw_border=False, window_name=self.win.title)
        except TypeError:                                # older versions don't have those options
            cap = WindowsCapture(window_name=self.win.title)

        @cap.event
        def on_frame_arrived(frame, control):
            self._latest = frame.frame_buffer.copy()

        @cap.event
        def on_closed():
            pass

        self._wgc = cap.start_free_threaded()

    def _wgc_frame(self):
        end = time.time() + 3
        while self._latest is None and time.time() < end:
            time.sleep(0.05)
        if self._latest is None:
            raise RuntimeError("No frame from Windows Graphics Capture (is the window minimized?)")
        return cv2.cvtColor(self._latest, cv2.COLOR_BGRA2BGR)

    def close(self):
        if self._wgc is not None:
            try:
                self._wgc.stop()
            except Exception:
                pass
