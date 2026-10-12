import ctypes

# Stop Windows display scaling from skewing capture/click coordinates
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

WINDOW_TITLE = "Clash of Clans"   # part of the Google Play Games window title
TEMPLATE_DIR = "templates"
THRESHOLD = 0.82                  # template match confidence (0-1). Lower = looser
KILL_KEY = "f12"                  # hotkey to stop the bot

# Floating "collect" bubbles above full collectors/mines/drills
def variants(prefix, n):
    """prefix, prefix1, prefix2 ... prefixN (templates you haven't captured are simply skipped)"""
    return [prefix] + [f"{prefix}{i}" for i in range(1, n + 1)]

LOOT_TYPES = ["gold", "elixir", "dark"]
LOOT_GROUPS = {t: variants(f"loot_{t}", 9) for t in LOOT_TYPES}      # loot_gold, loot_gold1 ... loot_gold9
LOOT_ICONS = [n for g in LOOT_GROUPS.values() for n in g]
COLLECT_ONE_PER_TYPE = True   # tap one bubble per type (game collects all of that type). False = tap every bubble

# Entries in the builder's list that you can afford (use the affordable styling)
UPGRADE_ITEMS = [n for t in ["gold", "elixir"] for n in variants(f"list_{t}", 3)]   # list_gold, list_gold1..3, list_elixir...

MAX_UPGRADE_ATTEMPTS = 6          # per cycle
CYCLE_SLEEP = (240, 420)          # seconds between cycles (random in range)
CLICK_JITTER = 4                  # px of random offset on clicks

# ---- Building new structures ----
MAX_BUILDS_PER_CYCLE = 3
SHOP_TABS = ["shop_tab_resources", "shop_tab_defense", "shop_tab_army", "shop_tab_traps"]
SHOP_BUY_BUTTONS = ["shop_buy_gold", "shop_buy_elixir", "shop_buy_dark"]  # affordable, non-gem only
SHOP_SCROLLS = 6                       # horizontal list swipes per tab
SHOP_DRAG = ((0.75, 0.55), (0.25, 0.55))   # swipe from -> to, as fractions of the window

# Where to try dragging a new building if it spawns on an invalid spot (fractions of window).
# Pick empty ground in YOUR base, then tweak these.
PLACE_SPOTS = [(0.30, 0.45), (0.70, 0.45), (0.30, 0.65), (0.70, 0.65), (0.50, 0.30)]

# Screens the bot must never confirm: gem purchases ("builder busy", "buy resources with gems")
GEM_GUARDS = ["confirm_gem"]   # add any other gem-spend screens here (e.g. "gem_dialog")

# Optional step 2: a separate Upgrade button in the building info bar (leave [] if the list entry goes straight to the confirm dialog)
UPGRADE_BTNS = ["upgrade_gold", "upgrade_elixir"]
# Step 3: the confirm dialog buttons (gold/elixir only, never gems)
CONFIRM_BTNS = ["confirm_gold", "confirm_elixir"]
CANCEL_BTN = "cancel_btn"

# ---- Matching tweaks ----
# Per-template confidence overrides (default is THRESHOLD)
THRESHOLDS = {"loot_gold": 0.70, "loot_elixir": 0.70, "loot_dark": 0.70}
# Templates matched at several sizes (for things that scale with zoom)
MULTI_SCALE = ["loot_gold", "loot_elixir", "loot_dark"]
SCALES = [0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4]

# Any "X" buttons the bot may press to back out of screens (capture shop_close etc. and add them)
CLOSE_BTNS = ["close_btn", "gem_close", "shop_close"]
# Save screenshots + template scores to ./debug while upgrading/building
DEBUG = True

# Affordability check for builder-list entries: a box (x1, x2, y1, y2) relative to the matched
# icon's centre, covering the cost NUMBER. Red text there = can't afford -> skipped.
# The number usually sits to the LEFT of the icon. Check the boxes drawn in debug/1_builder_list.png
LIST_TEXT_BOX = (6, 62, -10, 10)   # number sits to the RIGHT of the icon
RED_RATIO = 0.02          # fraction of red pixels in that box that counts as "unaffordable"

# ---- Gem safety ----
GEM_THRESHOLD = 0.70   # a gem template scoring this high is treated as "gem screen present" (deliberately loose)
CONFIRM_MIN = 0.88     # confirm buttons must match at least this well to be clicked (deliberately strict)

# Last-resort fallback if no X template matches: tap here (fractions of the window) to dismiss a popup,
# e.g. (0.03, 0.5) taps the dimmed area at the far left. None = disabled.
OUTSIDE_TAP = None

# ---- Builder counter (the "free/total" text near the builder icon) ----
# Box (x1, x2, y1, y2) in pixels relative to the builder_btn match centre, covering the counter text.
# Check debug/0_home.png (a box is drawn) and adjust until it sits tightly on the text.
BUILDER_COUNT_BOX = (28, 72, -14, 14)   # the 'free/total' text just right of the builder icon, left of the green +
COUNTER_DIFF = 6          # mean grey-level change that counts as "the counter changed"
# Optional template: crop of the counter when ALL builders are busy (e.g. "0/5"). Enables skipping upgrades early.
BUSY_TEMPLATE = "builders_none"

# Affordability box for SHOP items: (x1, x2, y1, y2) relative to the matched shop_buy_* icon, covering the price number.
# Check debug/..._shop_items.png (green = affordable, red = skipped) and adjust.
SHOP_TEXT_BOX = (-70, -6, -10, 10)   # price sits to the LEFT of the icon in the shop

# ---- Shop behaviour ----
# The builder list already offers "New ..." buildings, so the shop is optional. False = never open it.
USE_SHOP = False
SHOP_COOLDOWN = 1800      # seconds before re-scanning the shop after finding nothing affordable
SHOP_END_DIFF = 2.5       # if a swipe changes the shop view less than this, the tab has ended

# ---- Timers / background mode ----
NUM_BUILDERS = 2
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# Builder list panel, relative to the builder_btn centre: (x1, x2, y1, y2). Covers the whole list so timers are found wherever they sit.
LIST_PANEL_BOX = (-100, 200, 45, 440)
# Optional template: the "Suggested upgrades:" title. Lets the bot know whether the list is open.
LIST_HEADER = "list_header"
LIST_CLOSE_TAP = (0.25, 0.5)      # tapped to dismiss the list if clicking the builder icon again doesn't

LAUNCH_TARGET = r"C:\Users\YOU\Desktop\Clash of Clans.lnk"   # shortcut or exe that starts the game: SET THIS
LOAD_TIMEOUT = 180                # seconds to wait for the game to reach the village
WAKE_MARGIN = 90                  # start a session this long after an upgrade is due
MAX_SLEEP = 4 * 3600              # never sleep longer than this (collectors fill up)
DEFAULT_SLEEP = 3600              # when no timers are known
CLOSE_AFTER_SESSION = True

# ---- "New" entries open the shop with a bouncing arrow over the item ----
# Capture the arrow as shop_arrow (it bounces, so it is matched loosely and at several sizes).
THRESHOLDS["shop_arrow"] = 0.70
MULTI_SCALE.append("shop_arrow")

# Timers sit in the right-hand part of the builder list. The first OCR pass only looks at this part of the panel
# (fraction of its width, measured from the left) and only allows digits and d/h/m/s, which stops 2 -> Z/e mix-ups.
TIME_COLUMN_START = 0.55

# Detecting whether the builder list is open. Best: capture the list title ("Suggested upgrades:" or
# "Upgrades in progress:") as list_header / list_header1 / list_header2. Without them the bot compares the
# panel area against a snapshot taken just before opening; PANEL_DIFF is the change that counts as "open".
LIST_HEADERS = variants("list_header", 2)
PANEL_DIFF = 12

# Capture the title "Upgrades in progress:" as list_progress. If it is NOT on screen when the list is open,
# nothing is running, so the bot records no timers. If it is, only the rows between it and the next
# header (list_header = "Suggested upgrades:") are read, which keeps costs from being mistaken for times.
PROGRESS_HEADER = "list_progress"

# Looser thresholds for templates that sit just under the default (0.82) in practice. Numbered variants
# (list_elixir1 ...) inherit these. list_* is only ever searched inside the builder-list panel, so a
# lower bar can't hit the HUD resource icons.
THRESHOLDS.update({
    "list_gold": 0.74, "list_elixir": 0.74, "list_dark": 0.74,
    "upgrade_gold": 0.72, "upgrade_elixir": 0.72,
})

# ---- Reading the game's font (glyphs.py) ----
import os as _os
GLYPH_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "glyphs")
GLYPH_MAX_DIST = 0.42     # a character matching worse than this reads as '?'
GLYPH_W_REL = 0.5         # weight of "height relative to the tallest character" (tells 5 from s)
GLYPH_W_AR = 0.3          # weight of width/height ratio

# ---- Upgrade time shown on the confirm dialog ("Upgrade time  9m", right of the Confirm button) ----
# Box (x1, x2, y1, y2) relative to the matched confirm_gold / confirm_elixir ICON centre, covering only the value line
# (not the words "Upgrade time"). Check debug/..._confirm_time.png and adjust.
UPGRADE_TIME_BOX = (50, 185, -18, 24)
INSTANT_SECS = 30         # upgrades this short may finish before the builder counter visibly changes
READ_LIST_TIMERS = False  # the old list OCR (Tesseract can't read the game's font reliably); dialog times replace it

# Where the "Upgrade time" VALUE sits on the confirm dialog, as fractions of the window: (x1, y1, x2, y2).
# The dialog is always in the same place, so this doesn't depend on how the confirm templates were cropped.
# Covers only the value (e.g. "9m"), not the words "Upgrade time". Check debug/..._confirm_time.png.
UPGRADE_TIME_REGION = (0.733, 0.868, 0.815, 0.926)
# Optional, more robust to a resized window: capture the words "Upgrade time" as upgrade_time_label. When it is found,
# the value box is measured from it instead: (x1, x2, y1, y2) relative to the label's centre.
UPGRADE_TIME_LABEL = "upgrade_time_label"
UPGRADE_TIME_FROM_LABEL = (-62, 73, 13, 55)

# ---- Background mode ----
# INPUT_MODE:   "postmessage" = taps are posted straight to the game window: your mouse cursor never moves and the
#               window doesn't need focus.   "cursor" = the old behaviour (real mouse movement).
# CAPTURE_MODE: "mss" = screen pixels (the game must be visible, nothing covering it)
#               "printwindow" / "wgc" = read the window itself, so it can be covered by other windows.
#               (wgc needs: pip install windows-capture. printwindow needs: pip install pywin32.)
# The game window must NOT be minimised in any mode: Android stops drawing it.
# Run probe_background.py to find out what works on your machine.
INPUT_MODE = "CROSVM_1"
CAPTURE_MODE = "mss"
TARGET_CLASS = None     # window class that should receive clicks; None = auto (the probe tells you what worked)
