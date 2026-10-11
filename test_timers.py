"""Open the builder list yourself (with upgrades running), then run this to see what the OCR reads."""
import os, time, cv2
import config
from capture import GameWindow
from vision import Vision
import ocr_time

if not ocr_time.available():
    raise SystemExit("Tesseract not found. Install it (UB-Mannheim build), `pip install pytesseract`, "
                     "and set TESSERACT_CMD in config.py")
gw = GameWindow(config.WINDOW_TITLE)
vis = Vision(config.TEMPLATE_DIR)
input("Open the builder list (with upgrades in progress), then press Enter here...")
for i in range(5, 0, -1):
    print(f"Capturing in {i}...", end="\r"); time.sleep(1)
frame = gw.grab()
pt = vis.find(frame, "builder_btn")
if not pt:
    raise SystemExit("builder_btn not visible")
x1, x2, y1, y2 = config.LIST_PANEL_BOX
H, W = frame.shape[:2]
crop = frame[max(0, pt[1] + y1):min(H, pt[1] + y2), max(0, pt[0] + x1):min(W, pt[0] + x2)]
found, lines, prep = ocr_time.find_times(crop)
os.makedirs("debug", exist_ok=True)
cv2.imwrite("debug/timers_panel.png", crop)
cv2.imwrite("debug/timers_prep.png", prep)
print("\nRaw OCR lines:")
for l in lines:
    print("   ", repr(l))
print("\nParsed times:")
for l, t in found:
    print(f"    {l!r} -> {t}s ({t // 3600}h {t % 3600 // 60}m)")
print("\nSaved debug/timers_panel.png and debug/timers_prep.png")
