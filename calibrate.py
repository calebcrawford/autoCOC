"""Capture templates from the live game window.
Run it, switch to the game, wait for the countdown, then drag a box around
an icon, press ENTER, and name it (e.g. loot_gold, builder_btn)."""
import os, time, cv2
import config
from capture import GameWindow

def main():
    gw = GameWindow(config.WINDOW_TITLE)
    os.makedirs(config.TEMPLATE_DIR, exist_ok=True)
    while True:
        input("\nGet the game to the screen you want, then press Enter here (Ctrl+C quits)...")
        for i in range(1, 0, -1):
            print(f"Capturing in {i}...", end="\r"); time.sleep(1)
        frame = gw.grab()
        while True:
            x, y, w, h = cv2.selectROI("Drag a box, ENTER=confirm, C=cancel", frame, showCrosshair=False)
            if w == 0 or h == 0:
                break
            name = input("Template name (blank to skip): ").strip()
            if name:
                cv2.imwrite(os.path.join(config.TEMPLATE_DIR, f"{name}.png"), frame[y:y+h, x:x+w])
                print(f"Saved {name}.png")
            if input("Crop another from this frame? (y/n): ").lower() != "y":
                break
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
