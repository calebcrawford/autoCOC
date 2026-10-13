"""Find out what works on this PC for running the bot in the background.

Part 1: lists the game's windows.
Part 2: grabs a frame with each capture method (once visible, once with something covering the game).
Part 3: tries posting a click to each candidate window and sees if the sidebar opens. Your cursor must not move.

Before you start: game open on the village (home screen), sidebar CLOSED, window not minimised."""
import ctypes, os, time
import cv2, numpy as np
import config
import actions
from capture import GameWindow
from vision import Vision

def cursor():
    p = actions._Pt()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y

def panel_sig(frame):
    H, W = frame.shape[:2]
    x1, y1, x2, y2 = config.SIDEBAR_BOX
    crop = frame[int(H * y1):int(H * y2), int(W * x1):int(W * x2)]
    return cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (50, 60)).astype(np.float32)

def countdown(msg, n=8):
    print(msg)
    for i in range(n, 0, -1):
        print(f"  {i}...", end="\r"); time.sleep(1)
    print()

def capture_test(tag):
    os.makedirs("debug", exist_ok=True)
    for mode in ("mss", "printwindow", "wgc"):
        try:
            g = GameWindow(config.WINDOW_TITLE, mode=mode)
            time.sleep(0.8)
            f = g.grab()
            g.close()
            path = f"debug/probe_{mode}_{tag}.png"
            cv2.imwrite(path, f)
            note = "  <-- all black, this method doesn't work" if f.mean() < 3 else ""
            print(f"  {mode:12} {f.shape[1]}x{f.shape[0]}  brightness {f.mean():5.1f}  saved {path}{note}")
        except Exception as e:
            print(f"  {mode:12} FAILED: {type(e).__name__}: {e}")

def main():
    gw = GameWindow(config.WINDOW_TITLE, mode="mss")
    vis = Vision(config.TEMPLATE_DIR)
    print(f"\nWindow: hwnd={gw.hwnd}  rect={gw.region()}")
    wins = actions.list_windows(gw.hwnd)
    print("\nPART 1: windows inside the game window (hwnd, class, client w x h, visible)")
    for h, cls, w, hgt, v in wins:
        print(f"  {h:>10}  {cls:40} {w}x{hgt}  {'visible' if v else 'hidden'}")
    print(f"  -> auto-picked target: {actions.class_name(actions.pick_target(gw.hwnd))}")

    print("\nPART 2: capture methods")
    print(" with the game visible:")
    capture_test("visible")
    countdown("Now put another window ON TOP of the game (e.g. Notepad, maximised). Do not minimise the game.", 10)
    print(" with the game covered:")
    capture_test("covered")
    print(" Open debug/probe_*_covered.png. A method works if it shows the GAME, not the window on top.")
    print(" ('mss' showing the other window is expected: it reads screen pixels.)")

    countdown("Bring the game back on top, home screen, sidebar closed.", 8)
    print("\nPART 3: background clicks (watch your mouse: it must NOT move)")
    frame = gw.grab()
    bpt = vis.find(frame, config.OPEN_BTN)
    if not bpt:
        raise SystemExit(f"{config.OPEN_BTN} not found on screen, can't run the click test.")
    base = panel_sig(frame)
    cands = [w for w in wins if w[4] or w[0] == gw.hwnd]
    cands.sort(key=lambda w: -(w[2] * w[3]))
    seen, worked = set(), None
    for h, cls, w, hgt, v in cands:
        if h in seen:
            continue
        seen.add(h)
        before = cursor()
        inp = actions.Input(gw, mode="postmessage", target=h)
        inp.click(*bpt)
        time.sleep(1.6)
        diff = float(np.abs(panel_sig(gw.grab()) - base).mean())
        moved = cursor() != before
        print(f"  target {cls:38} sidebar opened: {'YES' if diff > config.PANEL_DIFF else 'no ':3} (change {diff:5.1f})  cursor moved: {'YES' if moved else 'no'}")
        if diff > config.PANEL_DIFF:
            worked = (h, cls)
            frame = gw.grab()
            xpt = next((vis.find(frame, n) for n in config.LIST_CLOSE_BTNS if vis.has(n) and vis.find(frame, n)), None)
            if xpt:
                inp.click(*xpt)                  # close the sidebar again with its X
                time.sleep(1.2)
            else:
                print("  (no sidebar_close / close_btn template yet, please close the sidebar yourself)")
            break
    print()
    if worked:
        print(f"Clicks work via window class '{worked[1]}'.")
        print(f"If that isn't what auto-pick chose, set  TARGET_CLASS = \"{worked[1]}\"  in config.py.")
    else:
        print("None of the windows accepted a posted click. Options: keep INPUT_MODE = \"cursor\", or tell me the")
        print("class names from PART 1 and what the game window is (Google Play Games version) and I'll try another route.")

if __name__ == "__main__":
    main()
