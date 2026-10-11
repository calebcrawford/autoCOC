import cv2, mss, numpy as np
import pygetwindow as gw

class GameWindow:
    def __init__(self, title):
        wins = [w for w in gw.getWindowsWithTitle(title) if w.title.strip()]
        if not wins:
            raise RuntimeError(f"No window found with title containing '{title}'")
        self.win = wins[0]
        self.sct = mss.mss()

    def region(self):
        w = self.win
        return {"left": w.left, "top": w.top, "width": w.width, "height": w.height}

    def origin(self):
        return self.win.left, self.win.top

    def grab(self):
        img = np.array(self.sct.grab(self.region()))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
