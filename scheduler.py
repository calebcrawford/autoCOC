"""Background runner: sleep until the next upgrade finishes, launch CoC, run one session, close it, repeat."""
import logging, os, time
import keyboard
import config, state
from bot import Bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("sched")
stop = False
current = None

def on_kill():
    global stop
    stop = True
    if current:
        current.stop()
    log.info("Kill switch pressed, stopping scheduler...")

def sleep_until(ts):
    while not stop and time.time() < ts:
        time.sleep(1)

def next_wake():
    now = time.time()
    nf = state.next_finish()
    if nf is None:
        return now + config.DEFAULT_SLEEP
    return min(max(nf + config.WAKE_MARGIN, now + 60), now + config.MAX_SLEEP)

def get_bot():
    try:
        return Bot()                       # game already open
    except RuntimeError:
        pass
    if not os.path.exists(config.LAUNCH_TARGET):
        log.info(f"LAUNCH_TARGET not found: {config.LAUNCH_TARGET}  (set it in config.py)")
        return None
    log.info("Launching Clash of Clans")
    os.startfile(config.LAUNCH_TARGET)
    end = time.time() + config.LOAD_TIMEOUT
    while time.time() < end and not stop:
        time.sleep(3)
        try:
            return Bot()
        except RuntimeError:
            continue
    return None

def run_session():
    global current
    bot = get_bot()
    if not bot:
        log.info("Could not get a game window, will retry next wake")
        return
    current = bot
    try:
        if bot.wait_until_home(config.LOAD_TIMEOUT):
            bot.session()
        else:
            log.info("Game never reached the home screen")
        if config.CLOSE_AFTER_SESSION and not stop:
            bot.close_game()
    finally:
        current = None
        try:
            bot.win.close()          # stops the background capture thread, if one is running
        except Exception:
            pass

if __name__ == "__main__":
    keyboard.add_hotkey(config.KILL_KEY, on_kill)
    log.info(f"Scheduler running. Press {config.KILL_KEY.upper()} to stop.")
    while not stop:
        try:
            run_session()
        except Exception:
            log.exception("Session error")
        wake = next_wake()
        log.info("Next session at " + time.strftime("%H:%M:%S", time.localtime(wake)))
        sleep_until(wake)
