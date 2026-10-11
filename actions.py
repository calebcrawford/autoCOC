import random, time
import pydirectinput
import config

pydirectinput.PAUSE = 0.03

class Input:
    def __init__(self, window):
        self.win = window

    def size(self):
        return self.win.win.width, self.win.win.height

    def frac(self, fx, fy):
        w, h = self.size()
        return int(w * fx), int(h * fy)

    def click(self, x, y):
        ox, oy = self.win.origin()
        j = config.CLICK_JITTER
        pydirectinput.moveTo(ox + x + random.randint(-j, j), oy + y + random.randint(-j, j))
        time.sleep(random.uniform(0.05, 0.15))
        pydirectinput.click()

    def drag(self, x1, y1, x2, y2, duration=0.5, steps=12):
        ox, oy = self.win.origin()
        pydirectinput.moveTo(ox + x1, oy + y1)
        time.sleep(0.1)
        pydirectinput.mouseDown()
        for i in range(1, steps + 1):
            pydirectinput.moveTo(int(ox + x1 + (x2 - x1) * i / steps),
                                 int(oy + y1 + (y2 - y1) * i / steps))
            time.sleep(duration / steps)
        pydirectinput.mouseUp()
