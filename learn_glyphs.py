"""Teach the bot the game's font. The more examples of each character it has, the more reliable it reads times.

  python learn_glyphs.py                  -> grabs the live game window (5s countdown)
  python learn_glyphs.py screenshot.png   -> uses a saved screenshot instead (a full-window one)

Drag a box tightly around some white text (a time like '2h 30m', or any white number such as a cost), press ENTER,
then type what it says. Spaces are ignored. Use d h m s for units. Repeat; press C (or ESC) to finish."""
import sys, time
import cv2, numpy as np
import config, glyphs

def get_frame():
    if len(sys.argv) > 1:
        img = cv2.imread(sys.argv[1])
        if img is None:
            raise SystemExit(f"Can't read {sys.argv[1]}")
        return img
    from capture import GameWindow
    gw = GameWindow(config.WINDOW_TITLE)
    input("Get the game onto the screen that shows the text, then press Enter here...")
    for i in range(5, 0, -1):
        print(f"Capturing in {i}...", end="\r"); time.sleep(1)
    return gw.grab()

def preview(crop, gl):
    s = 6
    big = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
    for i, g in enumerate(gl):
        x, y, w, h = g["box"]
        cv2.rectangle(big, (x * s, y * s), ((x + w) * s, (y + h) * s), (0, 255, 0), 2)
        cv2.putText(big, str(i + 1), (x * s, max(12, y * s - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.imshow("What the bot sees (green boxes = characters)", big)
    cv2.waitKey(400)

def main():
    frame = get_frame()
    glyphs.load(force=True)
    print(f"{len(glyphs.load())} reference glyphs loaded.")
    while True:
        x, y, w, h = cv2.selectROI("Drag a box around the text. ENTER = confirm, C = finish", frame, showCrosshair=False)
        if w == 0 or h == 0:
            break
        crop = frame[y:y + h, x:x + w]
        gl = glyphs.segment(crop)
        preview(crop, gl)
        print(f"Found {len(gl)} character shape(s). Current reading: {glyphs.read_text(crop)[0]!r}")
        txt = input("Type what it really says (blank = skip): ").replace(" ", "").lower()
        if not txt:
            continue
        n = glyphs.save_glyphs(crop, txt)
        if n < 0:
            print(f"Mismatch: {len(gl)} shapes but you typed {len(txt)} characters. "
                  f"If two characters are touching (no dark outline between them) they show as one green box. "
                  f"The reader can still split those when reading, but you can't teach from a fused pair, so "
                  f"pick another sample. Otherwise try a tighter box (no borders, bars or other text).")
        else:
            print(f"Saved {n} glyphs. Now reads as {glyphs.read_text(crop)[0]!r}")
        cv2.destroyAllWindows()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
