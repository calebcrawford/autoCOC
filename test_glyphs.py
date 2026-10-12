"""Check what the glyph reader makes of some text.
  python test_glyphs.py                -> live game window
  python test_glyphs.py screenshot.png -> saved screenshot
Drag a box around white text and press ENTER; C finishes."""
import sys, time
import cv2
import config, glyphs, ocr_time

def get_frame():
    if len(sys.argv) > 1:
        img = cv2.imread(sys.argv[1])
        if img is None:
            raise SystemExit(f"Can't read {sys.argv[1]}")
        return img
    from capture import GameWindow
    gw = GameWindow(config.WINDOW_TITLE)
    input("Show the text in the game, then press Enter here...")
    for i in range(5, 0, -1):
        print(f"Capturing in {i}...", end="\r"); time.sleep(1)
    return gw.grab()

frame = get_frame()
print(f"{len(glyphs.load())} reference glyphs loaded")
while True:
    x, y, w, h = cv2.selectROI("Drag a box around the text. ENTER = read it, C = finish", frame, showCrosshair=False)
    if w == 0 or h == 0:
        break
    text, secs, worst = glyphs.read_time(frame[y:y + h, x:x + w])
    print(f"read {text!r}  ->  {ocr_time.fmt(secs) if secs else 'not a valid time'}   (worst char match {worst:.2f}, limit {config.GLYPH_MAX_DIST})")
cv2.destroyAllWindows()
