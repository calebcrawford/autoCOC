import logging, os, random, time
import cv2
import numpy as np
import keyboard
import config
from capture import GameWindow
from vision import Vision
from actions import Input
import ocr_time, state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bot")

class Bot:
    def __init__(self):
        self.win = GameWindow(config.WINDOW_TITLE)
        self.vis = Vision(config.TEMPLATE_DIR)
        self.inp = Input(self.win)
        self.running = True

    def stop(self):
        log.info("Kill switch pressed, stopping...")
        self.running = False

    # ---- helpers ----
    def look(self):
        return self.win.grab()

    def click_tpl(self, name, wait=1.0):
        pt = self.vis.find(self.look(), name)
        if pt:
            self.inp.click(*pt)
            time.sleep(wait + random.uniform(0, 0.4))
            return True
        return False

    def click_any(self, names, wait=1.0):
        """Click the best-scoring visible template among names."""
        frame = self.look()
        best, best_sc = None, -1.0
        for n in names:
            pt = self.vis.find(frame, n)
            if pt:
                sc = self.vis.score(frame, n)
                if sc > best_sc:
                    best, best_sc = pt, sc
        if best:
            self.inp.click(*best)
            time.sleep(wait + random.uniform(0, 0.4))
            return True
        return False

    def wait_for(self, name, timeout=5):
        end = time.time() + timeout
        while time.time() < end and self.running:
            if self.vis.find(self.look(), name):
                return True
            time.sleep(0.3)
        return False

    def idle(self, seconds):
        end = time.time() + seconds
        while self.running and time.time() < end:
            time.sleep(1)

    # ---- behaviours ----
    def snap(self, label, boxes=None):
        if not config.DEBUG:
            return
        os.makedirs("debug", exist_ok=True)
        frame = self.look()
        for (x1, y1, x2, y2, ok) in (boxes or []):
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0) if ok else (0, 0, 255), 2)
        cv2.imwrite(os.path.join("debug", f"{time.strftime('%H%M%S')}_{label}.png"), frame)

    def scores(self, names):
        f = self.look()
        return {n: round(self.vis.score(f, n), 2) for n in names if self.vis.has(n)}

    def recover(self):
        """Close popups / dialogs and reload if the game dropped.
        Returns False (and stops the bot) if a dialog can't be dismissed."""
        for _ in range(4):
            if self.click_tpl("reload_btn", 5):
                continue
            if not self.click_any(config.CLOSE_BTNS, 0.8):
                break
        if self.dialog_open():
            if config.OUTSIDE_TAP:
                self.inp.click(*self.inp.frac(*config.OUTSIDE_TAP))
                time.sleep(1.0)
            if self.dialog_open():
                self.snap("stuck")
                log.info("STUCK on a dialog the bot can't close. Capture its X as gem_close "
                         "(or set OUTSIDE_TAP). Stopping for safety.")
                self.running = False
                return False
        return True

    def gems_prompt(self):
        """True if any gem-spend screen is probably on screen (loose threshold on purpose)."""
        frame = self.look()
        return any(self.vis.score(frame, g) >= config.GEM_THRESHOLD
                   for g in config.GEM_GUARDS if self.vis.has(g))

    def dialog_open(self):
        """True if a confirm or gem dialog is still showing."""
        frame = self.look()
        names = config.CONFIRM_BTNS + config.GEM_GUARDS
        return any(self.vis.find(frame, n) for n in names if self.vis.has(n)) or self.gems_prompt()

    def safe_confirm(self):
        """Click a gold/elixir confirm only if it clearly beats the gem template, then verify it worked."""
        frame = self.look()
        gem = max((self.vis.score(frame, g) for g in config.GEM_GUARDS if self.vis.has(g)), default=0.0)
        best_pt, best_sc, best_name = None, 0.0, None
        for n in config.CONFIRM_BTNS:
            if not self.vis.has(n):
                continue
            sc = self.vis.score(frame, n)
            pt = self.vis.find(frame, n, config.CONFIRM_MIN)
            if pt and sc > best_sc:
                best_pt, best_sc, best_name = pt, sc, n
        log.info(f"Confirm check: best={best_name} {best_sc:.2f}, gem={gem:.2f}")
        if best_pt is None:
            log.info("No confident confirm button, not clicking")
            return False
        if gem >= config.GEM_THRESHOLD or gem >= best_sc - 0.03:
            log.info("Gem screen looks as likely as a normal confirm, refusing to click")
            self.snap("gem_refused")
            return False
        self.inp.click(*best_pt)
        time.sleep(2.0)
        if self.dialog_open():
            log.info("Dialog still open after click, upgrade did NOT start")
            self.snap("still_open")
            return False
        return True

    def shop_candidates(self):
        """Shop items whose price is NOT red, left to right."""
        frame = self.look()
        pts = []
        for name in config.SHOP_BUY_BUTTONS:
            pts += self.vis.find_all(frame, name)
        good, boxes = [], []
        for pt in self.dedupe(sorted(pts)):
            ratio, (ax, ay, bx, by) = self.red_ratio(frame, pt, config.SHOP_TEXT_BOX)
            ok = ratio < config.RED_RATIO
            boxes.append((ax, ay, bx, by, ok))
            log.info(f"  shop item at {pt}: red ratio {ratio:.3f} -> {'affordable' if ok else 'skip (red)'}")
            if ok:
                good.append(pt)
        if boxes:
            self.snap("shop_items", boxes)
        return good

    def shop_sig(self):
        f = self.look()
        H, W = f.shape[:2]
        g = cv2.cvtColor(f[int(H * 0.3):int(H * 0.8), int(W * 0.1):int(W * 0.9)], cv2.COLOR_BGR2GRAY)
        return cv2.resize(g, (80, 30)).astype(np.float32)

    def pick_from_shop(self):
        if time.time() < getattr(self, "_shop_cooldown", 0):
            return False
        if not self.click_tpl("shop_btn", 1.5):
            return False
        for tab in config.SHOP_TABS:
            if not self.running:
                break
            if not self.click_tpl(tab, 1.0):
                continue
            for _ in range(config.SHOP_SCROLLS):
                if not self.running:
                    break
                cands = self.shop_candidates()
                if cands:
                    self.inp.click(*cands[0])
                    time.sleep(1.5)
                    if self.gems_prompt():
                        log.info("Gem prompt after shop buy, backing out")
                        self.recover()
                        return False
                    return True
                before = self.shop_sig()
                (x1, y1), (x2, y2) = config.SHOP_DRAG
                self.inp.drag(*self.inp.frac(x1, y1), *self.inp.frac(x2, y2))
                time.sleep(0.8)
                if float(np.abs(before - self.shop_sig()).mean()) < config.SHOP_END_DIFF:
                    log.info(f"End of {tab}, next tab")
                    break
        if self.running:
            self._shop_cooldown = time.time() + config.SHOP_COOLDOWN
            log.info(f"No affordable shop item, not checking again for {config.SHOP_COOLDOWN // 60} min")
        self.recover()
        return False

    def shop_open(self):
        """True if the shop window is showing (arrow, a category tab, or its X is visible)."""
        frame = self.look()
        names = ["shop_arrow", "shop_close"] + config.SHOP_TABS
        return any(self.vis.find(frame, n) for n in names if self.vis.has(n))

    def buy_highlighted(self):
        """The shop opens with an arrow over the item. Buy the affordable item nearest that arrow."""
        frame = self.look()
        arrow = self.vis.find(frame, "shop_arrow") if self.vis.has("shop_arrow") else None
        cands = self.shop_candidates()
        if not cands:
            log.info("No affordable buy button visible in the opened shop")
            return False
        if arrow:
            below = [p for p in cands if p[1] > arrow[1]] or cands
            pt = min(below, key=lambda p: abs(p[0] - arrow[0]))
        else:
            pt = cands[0]
            log.info("No shop_arrow found, taking the first affordable item")
        self.inp.click(*pt)
        time.sleep(1.5)
        if self.gems_prompt():
            log.info("Gem prompt after shop buy, backing out")
            return False
        return True

    def place_building(self):
        """New buildings spawn at screen centre. Drag to empty ground until a strict tick match appears."""
        cx, cy = self.inp.frac(0.5, 0.5)
        for spot in [None] + config.PLACE_SPOTS:
            if spot is not None:
                tx, ty = self.inp.frac(*spot)
                self.inp.drag(cx, cy, tx, ty)
                cx, cy = tx, ty
                time.sleep(0.7)
            frame = self.look()
            pt = self.vis.find(frame, "place_confirm", config.CONFIRM_MIN)
            log.info(f"place_confirm score {self.vis.score(frame, 'place_confirm'):.2f}")
            if pt and not self.gems_prompt():
                self.inp.click(*pt)
                time.sleep(1.5)
                log.info("Placement confirmed, verifying...")
                return True
        log.info("No valid spot found, cancelling placement")
        self.click_tpl(config.CANCEL_BTN, 1.0)
        return False

    def build_ready(self):
        problems = []
        if not self.vis.has("shop_btn"): problems.append("shop_btn")
        if not any(self.vis.has(n) for n in config.SHOP_TABS): problems.append("a shop tab")
        if not any(self.vis.has(n) for n in config.SHOP_BUY_BUTTONS): problems.append("a shop_buy_* button")
        if not self.vis.has("place_confirm"): problems.append("place_confirm")
        if not self.vis.has(config.CANCEL_BTN): problems.append(config.CANCEL_BTN)
        if problems:
            if not getattr(self, "_warned_build", False):
                log.info("Skipping building, missing templates: " + ", ".join(problems))
                self._warned_build = True
            return False
        return True

    def build_new(self):
        if not config.USE_SHOP:
            return
        if not self.build_ready():
            return
        for _ in range(config.MAX_BUILDS_PER_CYCLE):
            if not self.running:
                return
            if self.no_builders_free():
                log.info("All builders busy, skipping building")
                return
            before = self.counter_sig()
            if not self.pick_from_shop():
                return
            if not self.place_building():
                self.recover()
                return
            if self.verify_started(before):
                log.info("Building started (builder counter changed)")
            else:
                log.info("Building did NOT start (counter unchanged)")
                self.snap("build_fail")
                self.recover()
                return

    @staticmethod
    def dedupe(pts, r=20):
        out = []
        for p in pts:
            if all(abs(p[0] - q[0]) > r or abs(p[1] - q[1]) > r for q in out):
                out.append(p)
        return out

    def collect(self):
        frame = self.look()
        n = 0
        for kind, names in config.LOOT_GROUPS.items():
            names = [x for x in names if self.vis.has(x)]
            if config.COLLECT_ONE_PER_TYPE:
                best_pt, best_sc = None, 0.0
                for name in names:
                    pt = self.vis.find(frame, name)
                    if pt:
                        sc = self.vis.score(frame, name)
                        if sc > best_sc:
                            best_pt, best_sc = pt, sc
                pts = [best_pt] if best_pt else []
            else:
                pts = []
                for name in names:
                    pts += self.vis.find_all(frame, name)
                pts = self.dedupe(pts)
            for pt in pts:
                self.inp.click(*pt)
                n += 1
                log.info(f"Collected {kind} at {pt}")
                time.sleep(random.uniform(0.4, 0.8))
        log.info(f"Collect done: {n} tap(s)")

    def red_ratio(self, frame, pt, box=None):
        x1, x2, y1, y2 = box or config.LIST_TEXT_BOX
        x, y = pt
        H, W = frame.shape[:2]
        ax, bx = max(0, x + x1), min(W, x + x2)
        ay, by = max(0, y + y1), min(H, y + y2)
        roi = frame[ay:by, ax:bx]
        if roi.size == 0:
            return 0.0, (ax, ay, bx, by)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        red = ((hsv[..., 0] < 10) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 120) & (hsv[..., 2] > 120)
        return float(red.mean()), (ax, ay, bx, by)

    def upgrade_candidates(self):
        """Affordable builder-list entries, top of the list first."""
        frame = self.look()
        pts = []
        bpt = self.vis.find(frame, "builder_btn")
        if bpt:
            x1, x2, y1, y2 = config.LIST_PANEL_BOX
            H, W = frame.shape[:2]
            ax, ay = max(0, bpt[0] + x1), max(0, bpt[1] + y1)
            panel = frame[ay:min(H, bpt[1] + y2), ax:min(W, bpt[0] + x2)]
            for name in config.UPGRADE_ITEMS:
                pts += [(x + ax, y + ay) for x, y in self.vis.find_all(panel, name)]
        else:
            log.info("builder_btn not visible, can't locate the list panel")
        good, boxes = [], []
        for pt in self.dedupe(sorted(pts, key=lambda p: p[1])):
            ratio, (ax, ay, bx, by) = self.red_ratio(frame, pt)
            ok = ratio < config.RED_RATIO
            boxes.append((ax, ay, bx, by, ok))
            log.info(f"  entry at {pt}: red ratio {ratio:.3f} -> {'affordable' if ok else 'skip (red)'}")
            if ok:
                good.append(pt)
        self._boxes = boxes
        return good

    def confirm_visible(self):
        f = self.look()
        return any(self.vis.find(f, n) for n in config.CONFIRM_BTNS)

    # ---- builder counter ----
    def counter_box(self, frame):
        pt = self.vis.find(frame, "builder_btn")
        if not pt:
            return None
        x1, x2, y1, y2 = config.BUILDER_COUNT_BOX
        H, W = frame.shape[:2]
        ax, bx = max(0, pt[0] + x1), min(W, pt[0] + x2)
        ay, by = max(0, pt[1] + y1), min(H, pt[1] + y2)
        if bx <= ax or by <= ay:
            return None
        return ax, ay, bx, by

    def counter_sig(self):
        frame = self.look()
        box = self.counter_box(frame)
        if not box:
            return None
        ax, ay, bx, by = box
        g = cv2.cvtColor(frame[ay:by, ax:bx], cv2.COLOR_BGR2GRAY)
        return cv2.resize(g, (60, 20)).astype(np.float32)

    def no_builders_free(self):
        return (self.vis.has(config.BUSY_TEMPLATE)
                and self.vis.find(self.look(), config.BUSY_TEMPLATE) is not None)

    def verify_started(self, before):
        """An upgrade only counts if the builder counter actually changed."""
        if not self.recover():
            return False
        time.sleep(1.0)
        after = self.counter_sig()
        if before is None or after is None:
            log.info("Can't read builder counter (builder_btn not visible?), trusting dialog check only")
            return True
        diff = float(np.abs(before - after).mean())
        log.info(f"Builder counter change: {diff:.1f} (needs >= {config.COUNTER_DIFF})")
        return diff >= config.COUNTER_DIFF

    def _upgrade_loop(self):
        skip = 0  # list entries that failed this cycle (e.g. can't afford)
        for _ in range(config.MAX_UPGRADE_ATTEMPTS):
            if not self.running:
                log.info("Upgrade loop: bot stopped")
                return
            if self.no_builders_free():
                log.info("All builders busy, skipping upgrades")
                return
            frame = self.look()
            box = self.counter_box(frame)
            self.snap("0_home", [(*box, True)] if box else None)
            before = self.counter_sig()
            if not self.open_list():
                return
            cands = self.upgrade_candidates()
            self.snap("1_builder_list", getattr(self, "_boxes", None))
            log.info(f"List scores {self.scores(config.UPGRADE_ITEMS)}; {len(cands)} candidate(s), skip={skip}")
            if skip >= len(cands):
                self.close_list()
                log.info("No more upgradeable items")
                return
            self.inp.click(*cands[skip])
            self._list_open, self._closed_sig = False, None   # tapping an entry closes the list
            time.sleep(1.8)
            self.snap("2_after_list_click")
            # "New ..." entries drop straight into placement mode (red cancel X, no confirm dialog)
            if self.shop_open():
                log.info("Entry is a NEW building: shop opened, buying the highlighted item")
                ok = self.buy_highlighted() and self.place_building()
            elif (self.vis.find(self.look(), config.CANCEL_BTN) is not None
                  and not self.confirm_visible()):
                log.info("Entry is a NEW building, placing it")
                ok = self.place_building()
            else:
                # If the confirm dialog isn't up yet, we're on the info bar: press Upgrade first
                if not self.confirm_visible():
                    self.click_any(config.UPGRADE_BTNS, 1.8)
                    self.snap("3_after_upgrade_btn")
                names = config.UPGRADE_BTNS + config.CONFIRM_BTNS + config.GEM_GUARDS
                log.info(f"Dialog scores {self.scores(names)}")
                if self.gems_prompt():
                    log.info("Gem prompt detected, backing out")
                    self.snap("gem_prompt")
                    ok = False
                else:
                    ok = self.safe_confirm()
            if ok:
                ok = self.verify_started(before)
            if ok:
                log.info("Upgrade started (builder counter changed)")
            else:
                log.info("Upgrade did not start, trying next")
                self.snap("fail")
                skip += 1
            if not self.recover():
                return

    # ---- timers / sessions ----
    def panel_sig(self):
        frame = self.look()
        pt = self.vis.find(frame, "builder_btn")
        if not pt:
            return None
        x1, x2, y1, y2 = config.LIST_PANEL_BOX
        H, W = frame.shape[:2]
        crop = frame[max(0, pt[1] + y1):min(H, pt[1] + y2), max(0, pt[0] + x1):min(W, pt[0] + x2)]
        if crop.size == 0:
            return None
        return cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (50, 60)).astype(np.float32)

    def list_is_open(self):
        headers = [n for n in config.LIST_HEADERS if self.vis.has(n)]
        if headers:
            frame = self.look()
            return any(self.vis.find(frame, n) for n in headers)
        base, sig = getattr(self, "_closed_sig", None), self.panel_sig()
        if base is None or sig is None:
            return getattr(self, "_list_open", False)
        return float(np.abs(base - sig).mean()) > config.PANEL_DIFF

    def open_list(self):
        """Open the builder list, but never toggle it closed if it's already open."""
        if self.list_is_open():
            return True
        self._closed_sig = self.panel_sig()
        if not self.click_tpl("builder_btn", 1.3):
            log.info(f"Can't open the builder list: builder_btn not found "
                     f"(best score {self.vis.score(self.look(), 'builder_btn'):.2f}, "
                     f"needs {self.vis.thr('builder_btn'):.2f}). Recapture it as the icon only, "
                     f"or add variants builder_btn1, builder_btn2")
            self.snap("no_builder_btn")
            return False
        self._list_open = True
        return True

    def close_list(self):
        for i in range(3):
            if not self.list_is_open():
                break
            if i == 0:
                self.click_tpl("builder_btn", 0.9)          # the icon toggles the list
            else:
                self.inp.click(*self.inp.frac(*config.LIST_CLOSE_TAP))   # fall back to tapping outside
                time.sleep(0.9)
            self._list_open = False
        self._closed_sig = None
        self.recover()

    def refresh_timers(self):
        """Open the builder list, OCR the remaining times, save them to state.json."""
        if not ocr_time.available():
            if not getattr(self, "_warned_ocr", False):
                log.info("OCR unavailable (install Tesseract + pip install pytesseract): timers not tracked")
                self._warned_ocr = True
            return None
        if not self.open_list():
            return None
        frame = self.look()
        pt = self.vis.find(frame, "builder_btn")
        if not pt:
            log.info("Timers: list open but builder_btn not visible, can't place the panel crop")
            self.close_list()
            return None
        x1, x2, y1, y2 = config.LIST_PANEL_BOX
        H, W = frame.shape[:2]
        ay, by = max(0, pt[1] + y1), min(H, pt[1] + y2)
        ax, bx = max(0, pt[0] + x1), min(W, pt[0] + x2)
        crop = frame[ay:by, ax:bx]
        band, found = crop, []
        hdr = config.PROGRESS_HEADER
        if self.vis.has(hdr):
            hp = self.vis.find(frame, hdr)
            if hp is None:
                log.info("No 'Upgrades in progress' section, so nothing is running")
                band = None
            else:
                top = hp[1] + self.vis.t[hdr].shape[0] // 2 - ay
                ends = []
                for n in config.LIST_HEADERS:
                    p = self.vis.find(frame, n) if self.vis.has(n) else None
                    if p and p[1] > hp[1] + 10:
                        ends.append(p[1] - ay - 6)
                bottom = min(ends) if ends else top + config.NUM_BUILDERS * 45 + 20
                if bottom <= top:
                    bottom = top + config.NUM_BUILDERS * 45 + 20
                band = crop[max(0, top):min(crop.shape[0], bottom)]
        elif not getattr(self, "_warned_hdr", False):
            log.info("Tip: capture the 'Upgrades in progress:' title as list_progress for more reliable timers")
            self._warned_hdr = True
        if band is not None and band.size:
            found, lines, _ = ocr_time.find_times(band)
            if config.DEBUG:
                os.makedirs("debug", exist_ok=True)
                cv2.imwrite(os.path.join("debug", f"{time.strftime('%H%M%S')}_timers_band.png"), band)
        secs = [t for _, t in found][:config.NUM_BUILDERS]
        log.info(f"Timers read: {[(l.strip(), t) for l, t in found]}")
        state.set_timers(secs)
        self.close_list()
        return secs

    def builders_busy(self):
        if self.no_builders_free():
            return True
        return state.active_count() >= config.NUM_BUILDERS

    def upgrade(self):
        self.refresh_timers()
        if self.builders_busy():
            log.info("All builders busy, skipping upgrades")
            return
        self._upgrade_loop()
        self.refresh_timers()

    def session(self):
        log.info("Phase: recover")
        self.recover()
        log.info("Phase: collect")
        self.collect()
        self.build_new()
        log.info("Phase: upgrade")
        self.upgrade()
        log.info("Session finished")

    def wait_until_home(self, timeout=180):
        end = time.time() + timeout
        last = 0
        while time.time() < end and self.running:
            if self.vis.find(self.look(), "builder_btn"):
                time.sleep(2.0)       # let the village settle
                return True
            if time.time() - last > 10:   # dismiss login/reward popups while loading
                self.click_any(config.CLOSE_BTNS, 0.8)
                last = time.time()
            time.sleep(2)
        return False

    def close_game(self):
        try:
            self.win.win.close()
            log.info("Closed the game window")
        except Exception:
            log.exception("Couldn't close the game window")

    def run(self):
        keyboard.add_hotkey(config.KILL_KEY, self.stop)
        log.info(f"Running. Press {config.KILL_KEY.upper()} to stop.")
        while self.running:
            try:
                self.session()
            except Exception:
                log.exception("Cycle error")
            self.idle(random.uniform(*config.CYCLE_SLEEP))

if __name__ == "__main__":
    Bot().run()
