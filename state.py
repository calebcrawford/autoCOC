"""Tiny persistent store (state.json) so upgrade finish times survive restarts."""
import json, os, time

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

def load():
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"timers": [], "updated": 0}

def save(d):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, PATH)

def set_timers(seconds_left):
    now = time.time()
    save({"timers": sorted(now + s for s in seconds_left), "updated": now})

def active_count():
    now = time.time()
    return sum(1 for t in load().get("timers", []) if t > now)

def next_finish():
    now = time.time()
    future = [t for t in load().get("timers", []) if t > now]
    return min(future) if future else None
