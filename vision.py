import os, re, cv2, numpy as np
import config

class Vision:
    def __init__(self, folder):
        os.makedirs(folder, exist_ok=True)
        self.t = {}
        for f in os.listdir(folder):
            if f.lower().endswith(".png") and not f.startswith("_"):
                self.t[f[:-4]] = cv2.imread(os.path.join(folder, f))
        print(f"Loaded {len(self.t)} templates: {sorted(self.t)}")

    def has(self, name):
        return name in self.t

    @staticmethod
    def base(name):
        return re.sub(r"\d+$", "", name)   # loot_gold3 -> loot_gold

    def thr(self, name, override=None):
        t = config.THRESHOLDS
        return override or t.get(name, t.get(self.base(name), config.THRESHOLD))

    def _gray(self, frame):
        """Grayscale copy of the frame, cached so many templates can share it."""
        if getattr(self, "_gframe", None) is not frame:
            self._gframe, self._ggray = frame, cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return self._ggray

    def _match(self, frame, name):
        """Best match map over the allowed scales -> (result_map, template_used, score)."""
        tpl = self.t.get(name)
        if tpl is None:
            return None, None, 0.0
        if any(name.startswith(p) for p in config.GRAY_MATCH):       # ~3x cheaper, shapes are what matter
            frame, tpl = self._gray(frame), cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
        scales = config.SCALES if (name in config.MULTI_SCALE or self.base(name) in config.MULTI_SCALE) else [1.0]
        best = (None, None, -1.0)
        for s in scales:
            t = tpl if s == 1.0 else cv2.resize(
                tpl, None, fx=s, fy=s,
                interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
            if t.shape[0] >= frame.shape[0] or t.shape[1] >= frame.shape[1] or min(t.shape[:2]) < 6:
                continue
            res = cv2.matchTemplate(frame, t, cv2.TM_CCOEFF_NORMED)
            m = float(res.max())
            if m > best[2]:
                best = (res, t, m)
        return best

    def match_one(self, frame, name):
        """Exactly this template (no variant expansion), searched once: -> (point or None, score)."""
        res, t, _ = self._match(frame, name)
        if res is None:
            return None, 0.0
        _, mx, _, loc = cv2.minMaxLoc(res)
        pt = (loc[0] + t.shape[1] // 2, loc[1] + t.shape[0] // 2)
        return (pt if mx >= self.thr(name) else None), float(mx)

    def best_of(self, frame, names, stop_at=None):
        """Best match among exactly these templates, each searched once. Stops early once one scores >= stop_at.
        -> (point, score, template_name); point is None if nothing matched."""
        best = (None, 0.0, None)
        for n in names:
            if n not in self.t:
                continue
            pt, sc = self.match_one(frame, n)
            if pt and sc > best[1]:
                best = (pt, sc, n)
                if stop_at and sc >= stop_at:
                    break
        return best

    def group(self, name):
        """name plus any captured name1..name9 variants."""
        return [n for n in [name] + [f"{name}{i}" for i in range(1, 10)] if n in self.t]

    def score(self, frame, name):
        return max((self._match(frame, n)[2] for n in self.group(name)), default=0.0)

    def find(self, frame, name, thresh=None):
        best, best_sc = None, -1.0
        for n in self.group(name):
            res, t, _ = self._match(frame, n)
            if res is None:
                continue
            _, sc, _, loc = cv2.minMaxLoc(res)
            if sc >= self.thr(n, thresh) and sc > best_sc:
                best, best_sc = (loc[0] + t.shape[1] // 2, loc[1] + t.shape[0] // 2), sc
        return best

    def find_all(self, frame, name, thresh=None):
        res, t, _ = self._match(frame, name)
        if res is None:
            return []
        ys, xs = np.where(res >= self.thr(name, thresh))
        h, w = t.shape[:2]
        pts = []
        for x, y in sorted(zip(xs, ys), key=lambda p: -res[p[1], p[0]]):
            cx, cy = x + w // 2, y + h // 2
            if all(abs(cx - px) > w // 2 or abs(cy - py) > h // 2 for px, py in pts):
                pts.append((cx, cy))
        return pts
