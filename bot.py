import logging, os, random, re, time
import cv2
import numpy as np
import keyboard
import config
from capture import GameWindow
from vision import Vision
from actions import Input
import ocr_time, state, glyphs

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

    def read_upgrade_time(self, frame, pt=None):
        """Read the 'Upgrade time' value on the confirm dialog with the glyph reader (the game's own font)."""
        H, W = frame.shape[:2]
        label = self.vis.find(frame, config.UPGRADE_TIME_LABEL) if self.vis.has(config.UPGRADE_TIME_LABEL) else None
        if label:
            x1, x2, y1, y2 = config.UPGRADE_TIME_FROM_LABEL
            ax, bx, ay, by = label[0] + x1, label[0] + x2, label[1] + y1, label[1] + y2
        else:
            fx1, fy1, fx2, fy2 = config.UPGRADE_TIME_REGION
            ax, bx, ay, by = int(W * fx1), int(W * fx2), int(H * fy1), int(H * fy2)
        ax, bx, ay, by = max(0, ax), min(W, bx), max(0, ay), min(H, by)
        crop = frame[ay:by, ax:bx]
        if crop.size == 0:
            return None
        if config.DEBUG:
            os.makedirs("debug", exist_ok=True)
            cv2.imwrite(os.path.join("debug", f"{time.strftime('%H%M%S')}_confirm_time.png"), crop)
        if not glyphs.load():
            log.info("Upgrade time: no glyph library found (glyphs folder), skipping")
            return None
        text, secs, worst = glyphs.read_time(crop)
        if secs is None:
            log.info(f"Upgrade time: couldn't read it (saw {text!r}, worst match {worst:.2f}). "
                     f"Check debug/*_confirm_time.png shows just the value; teach it with learn_glyphs.py")
            return None
        log.info(f"Upgrade time on dialog: {ocr_time.fmt(secs)}  (read {text!r}, match {worst:.2f})")
        return secs

    def safe_confirm(self):
        """Click a gold/elixir confirm only if it clearly beats the gem template, then verify it worked."""
        self._last_secs = None
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
        self._last_secs = self.read_upgrade_time(frame, best_pt)
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
            if not names:
                continue
            if config.COLLECT_ONE_PER_TYPE:
                pt, sc, which = self.vis.best_of(frame, names, stop_at=config.LOOT_STOP)
                pts = [pt] if pt else []
                if pt:
                    log.info(f"  {kind}: matched {which} ({sc:.2f})")
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
        ax, ay, bx, by = self._frac_box(config.SIDEBAR_COST_STRIP, frame)
        panel = frame[ay:by, ax:bx]
        for name in config.UPGRADE_ITEMS:
            pts += [(x + ax, y + ay) for x, y in self.vis.find_all(panel, name)]
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
        """Is the 'Upgrade X to Level N?' dialog up? The confirm buttons or the 'Upgrade time' label say so."""
        f = self.look()
        names = list(config.CONFIRM_BTNS)
        if self.vis.has(config.UPGRADE_TIME_LABEL):
            names.append(config.UPGRADE_TIME_LABEL)
        return any(self.vis.find(f, n) for n in names if self.vis.has(n))

    # ---- builder counter ----
    # ---- builder counter ("free/total", read with the glyph reader) ----
    @staticmethod
    def _frac_box(region, frame):
        H, W = frame.shape[:2]
        x1, y1, x2, y2 = region
        return int(W * x1), int(H * y1), int(W * x2), int(H * y2)

    def free_builders(self, kind="builder"):
        """(free, total) from the on-screen counter, e.g. '1/2' -> (1, 2). kind: "builder" or "lab".
        None if it can't be read."""
        frame = self.look()
        region = (config.COUNT_SIDEBAR if self.list_is_open() else config.COUNT_HOME)[kind]
        ax, ay, bx, by = self._frac_box(region, frame)
        text, worst = glyphs.read_text(frame[ay:by, ax:bx])
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})", text)
        if not m or int(m.group(1)) > int(m.group(2)):
            if not getattr(self, "_warned_count", False):
                log.info(f"Can't read the {kind} counter (saw {text!r}). Teach it with learn_glyphs.py "
                         f"(type e.g. 2/2) or check COUNT_HOME / COUNT_SIDEBAR in config.py")
                self._warned_count = True
            return None
        return int(m.group(1)), int(m.group(2))

    def counter_sig(self, kind="builder"):
        """What the counter shows now: ('free', n) if readable, else a picture of it."""
        cnt = self.free_builders(kind)
        if cnt is not None:
            return ("free", cnt[0])
        frame = self.look()
        ax, ay, bx, by = self._frac_box(config.COUNT_HOME[kind], frame)
        g = cv2.cvtColor(frame[ay:by, ax:bx], cv2.COLOR_BGR2GRAY)
        return ("img", cv2.resize(g, (60, 20)).astype(np.float32))

    def no_builders_free(self, kind="builder"):
        cnt = self.free_builders(kind)
        return cnt is not None and cnt[0] == 0

    def verify_started(self, before, secs=None, kind="builder"):
        """An upgrade counts if a builder became busy, or if it is so short that it may already be done."""
        if not self.recover():
            return False
        self.close_list()                      # the sidebar can stay open after tapping an entry
        time.sleep(1.0)
        after = self.counter_sig(kind)
        if before is None or after is None or before[0] != after[0]:
            log.info("Can't compare the builder counter before/after, trusting the dialog check only")
            return True
        if before[0] == "free":
            log.info(f"Free {kind} slots: {before[1]} -> {after[1]}")
            changed = after[1] < before[1]
        else:
            diff = float(np.abs(before[1] - after[1]).mean())
            log.info(f"Builder counter change: {diff:.1f} (needs >= {config.COUNTER_DIFF})")
            changed = diff >= config.COUNTER_DIFF
        if changed:
            return True
        if secs is not None and secs <= config.INSTANT_SECS:
            log.info(f"Counter unchanged, but this upgrade only takes {ocr_time.fmt(secs)} so it was probably "
                     f"already finished: counting it as started")
            return True
        log.info("Counter unchanged (very short or instant upgrades may not register on the counter)")
        return False

    def select_tab(self, kind):
        """Tap the sidebar tile for this tab ("builder" or "lab"). Only call this while the sidebar is open."""
        self.inp.click(*self.inp.frac(*config.TAB_POS[kind]))
        time.sleep(1.0)

    def _upgrade_loop(self, kind="builder"):
        skip = 0  # list entries that failed this cycle (e.g. can't afford)
        attempts = config.LAB_ATTEMPTS if kind == "lab" else config.MAX_UPGRADE_ATTEMPTS
        for _ in range(attempts):
            if not self.running:
                log.info("Upgrade loop: bot stopped")
                return
            if self.no_builders_free(kind):
                log.info(f"No free {kind} slot, skipping")
                return
            frame = self.look()
            self.snap(f"0_{kind}_home", [(*self._frac_box(config.COUNT_HOME[kind], frame), True)])
            before = self.counter_sig(kind)
            self._last_secs = None
            if not self.open_list():
                return
            self.select_tab(kind)
            cands = self.upgrade_candidates()
            self.snap(f"1_{kind}_list", getattr(self, "_boxes", None))
            log.info(f"[{kind}] list scores {self.scores(config.UPGRADE_ITEMS)}; {len(cands)} candidate(s), skip={skip}")
            if skip >= len(cands):
                self.close_list()
                log.info(f"[{kind}] no more upgradeable items")
                return
            self.inp.click(*cands[skip])
            self._list_open, self._closed_sig = False, None   # tapping an entry closes the list
            time.sleep(1.8)
            self.snap(f"2_{kind}_after_list_click")
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
                    self.snap(f"3_{kind}_after_upgrade_btn")
                names = config.UPGRADE_BTNS + config.CONFIRM_BTNS + config.GEM_GUARDS
                log.info(f"Dialog scores {self.scores(names)}")
                if self.gems_prompt():
                    log.info("Gem prompt detected, backing out")
                    self.snap("gem_prompt")
                    ok = False
                else:
                    ok = self.safe_confirm()
            secs = getattr(self, "_last_secs", None)
            if ok:
                ok = self.verify_started(before, secs, kind)
            if ok:
                if secs:
                    state.add_timer(secs)
                    log.info(f"[{kind}] upgrade started, finishes in {ocr_time.fmt(secs)}")
                else:
                    log.info(f"[{kind}] upgrade started")
            else:
                log.info(f"[{kind}] upgrade did not start, trying next")
                self.snap(f"fail_{kind}")
                skip += 1
            if not self.recover():
                return

    # ---- timers / sessions ----
    def panel_sig(self):
        frame = self.look()
        ax, ay, bx, by = self._frac_box(config.SIDEBAR_BOX, frame)
        crop = frame[ay:by, ax:bx]
        if crop.size == 0:
            return None
        return cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (50, 60)).astype(np.float32)

    def list_is_open(self):
        """Is the 'Buildings & Heroes' sidebar showing? Best signal: the sidebar_title template."""
        headers = [n for n in config.LIST_HEADERS if self.vis.has(n)]
        if headers:
            frame = self.look()
            return any(self.vis.find(frame, n) for n in headers)
        base, sig = getattr(self, "_closed_sig", None), self.panel_sig()
        if base is None or sig is None:
            return getattr(self, "_list_open", False)
        return float(np.abs(base - sig).mean()) > config.PANEL_DIFF

    def open_list(self):
        """Open the sidebar, but never click again if it is already open."""
        if self.list_is_open():
            return True
        self._closed_sig = self.panel_sig()
        if not self.click_tpl(config.OPEN_BTN, 1.3):
            log.info(f"Can't open the sidebar: {config.OPEN_BTN} not found "
                     f"(best score {self.vis.score(self.look(), config.OPEN_BTN):.2f}, "
                     f"needs {self.vis.thr(config.OPEN_BTN):.2f}). Recapture it, or add variants "
                     f"{config.OPEN_BTN}1, {config.OPEN_BTN}2")
            self.snap("no_open_btn")
            return False
        self._list_open = True
        return True

    def close_list(self):
        for i in range(3):
            if not self.list_is_open():
                break
            if not self.click_any(config.LIST_CLOSE_BTNS, 0.9):
                self.inp.click(*self.inp.frac(*config.LIST_CLOSE_TAP))   # no X template matched: tap the village
                time.sleep(0.9)
            self._list_open = False
        self._closed_sig = None
        self.recover()

    def builders_busy(self):
        cnt = self.free_builders()
        if cnt is not None:
            return cnt[0] == 0
        return state.active_count() >= config.NUM_BUILDERS

    def upgrade(self):
        cnt = self.free_builders()
        if cnt is not None:
            log.info(f"Free builders: {cnt[0]}/{cnt[1]}")
        if self.builders_busy():
            log.info("All builders busy, skipping building upgrades")
        else:
            self._upgrade_loop("builder")
        if config.LAB_UPGRADES and self.running:
            self.lab_upgrade()

    def lab_upgrade(self):
        """Laboratory tab: same entries and dialog as upgrades, but its own slot (only one runs at a time)."""
        cnt = self.free_builders("lab")
        if cnt is None:
            log.info("Skipping lab upgrades: can't read the lab counter (the '1/1' next to the Build button)")
            return
        log.info(f"Free lab slots: {cnt[0]}/{cnt[1]}")
        if cnt[0] == 0:
            log.info("Laboratory busy, skipping")
            return
        self._upgrade_loop("lab")

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
            if self.vis.find(self.look(), config.HOME_ANCHOR):
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
