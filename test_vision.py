"""Shows what the bot sees: scores every template against a live screenshot
and saves debug.png with boxes around matches."""
import time
import cv2
import config
from capture import GameWindow
from vision import Vision

gw = GameWindow(config.WINDOW_TITLE)
vis = Vision(config.TEMPLATE_DIR)
input("Get the game on the screen you want to test, then press Enter here (5s delay)...")
for i in range(5, 0, -1):
    print(f"Capturing in {i}...", end="\r")
    time.sleep(1)
frame = gw.grab()

print()
for name, tpl in sorted(vis.t.items()):
    h, w = tpl.shape[:2]
    if h > frame.shape[0] or w > frame.shape[1]:
        print(f"{name}: template bigger than window, recapture it")
        continue
    matches = vis.find_all(frame, name)
    print(f"{name:20s} best score {vis.score(frame, name):.2f}   matches: {len(matches)}")
    for (x, y) in matches:
        cv2.rectangle(frame, (x - w // 2, y - h // 2), (x + w // 2, y + h // 2), (0, 255, 0), 2)
        cv2.putText(frame, name, (x - w // 2, y - h // 2 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

cv2.imwrite("debug.png", frame)
print("\nSaved debug.png in the folder you ran this from. Open it to see the matches.")
