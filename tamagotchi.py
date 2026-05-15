#!/usr/bin/env python3
# ghost//snail tamagotchi — runs on Mac, launched by the device
import os, sys, time, json, subprocess, math, termios, tty

CIRCUITPY   = "/Volumes/CIRCUITPY"
STATE_FILE  = os.path.join(CIRCUITPY, "pet.json")
STAGES      = 6
XP_PER_STAGE = 100

STAGE_NAMES = [
    "Hatchling",
    "Wandering Shell",
    "Phantom Crawler",
    "Data Drifter",
    "Ghost Protocol",
    "Apex Phantom",
]

ASCII_SNAIL = [
    # stage 0
    [
        "    o o    ",
        "   (| |)   ",
        "    \\|/    ",
    ],
    # stage 1
    [
        "    o o  @ ",
        "   (| |)_/ ",
        "    \\|/    ",
    ],
    # stage 2
    [
        "    o o  (@)",
        "   (| |)_/ |",
        "    \\|/  ~~~ ",
    ],
    # stage 3
    [
        "    o o  (@@) ",
        "   (| |)_/  \\ ",
        "    \\|/   ~~~~ ",
    ],
    # stage 4
    [
        "    o o  /@@@@\\  ",
        "   (| |)/      \\ ",
        "    \\|/ \\@@@@~/  ",
    ],
    # stage 5
    [
        "    o o  (@@@@@)  ",
        "   (| |)/        \\",
        "    \\|/ \\@@@@@~/  ",
        "          ~~~~~~  ",
    ],
]

# ── ANSI helpers ─────────────────────────────────────────────────────────────

def clr():    print("\033[2J\033[H", end="")
def cyan(s):  return f"\033[96m{s}\033[0m"
def green(s): return f"\033[92m{s}\033[0m"
def dim(s):   return f"\033[2m{s}\033[0m"
def bold(s):  return f"\033[1m{s}\033[0m"
def red(s):   return f"\033[91m{s}\033[0m"
def yellow(s):return f"\033[93m{s}\033[0m"

def bar(pct, width=20, fill="█", empty="░"):
    filled = int(pct / 100 * width)
    return fill * filled + empty * (width - filled)

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1).lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

# ── State ─────────────────────────────────────────────────────────────────────

DEFAULT_STATE = {
    "stage":  0,
    "hunger": 80,
    "energy": 90,
    "mood":   70,
    "xp":     0,
    "born":   int(time.time()),
    "last":   int(time.time()),
}

def load_state():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
            for k, v in DEFAULT_STATE.items():
                s.setdefault(k, v)
            return s
    except Exception:
        return dict(DEFAULT_STATE)

def save_state(s):
    s["last"] = int(time.time())
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(s, f)
        # also update the simple stage file for the device display
        with open(os.path.join(CIRCUITPY, "state.txt"), "w") as f:
            f.write(str(s["stage"]))
    except Exception:
        pass

def decay(s):
    """Apply time-based stat decay since last interaction."""
    elapsed = max(0, int(time.time()) - s.get("last", int(time.time())))
    mins    = elapsed / 60
    s["hunger"] = max(0, s["hunger"] - mins * 0.8)
    s["energy"] = max(0, s["energy"] - mins * 0.4)
    s["mood"]   = max(0, s["mood"]   - mins * 0.3)
    return s

def age_str(born):
    secs  = int(time.time()) - born
    days  = secs // 86400
    hours = (secs % 86400) // 3600
    mins  = (secs % 3600) // 60
    return f"{days}d {hours}h {mins}m"

# ── Render ────────────────────────────────────────────────────────────────────

W = 56

def divider(ch="━"):
    print(cyan(ch * W))

def draw(s):
    clr()
    stage = s["stage"]
    name  = STAGE_NAMES[stage]
    xp    = s["xp"]
    xp_next = XP_PER_STAGE - (xp % XP_PER_STAGE)

    divider()
    title = "g h o s t / / s n a i l"
    print(cyan(bold(title.center(W))))
    divider()
    print()

    # Stage info
    print(f"  {green(bold(f'Stage {stage}: {name}'))}".ljust(W+10) +
          dim(f"Age: {age_str(s['born'])}"))
    print()

    # ASCII art (green glow)
    art = ASCII_SNAIL[stage]
    for line in art:
        print(green("  " + line))
    print()

    # Stats
    h, e, m = s["hunger"], s["energy"], s["mood"]
    print(f"  {cyan('HUNGER')}  [{yellow(bar(h))}] {h:3.0f}%   {_hunger_msg(h)}")
    print(f"  {cyan('ENERGY')}  [{yellow(bar(e))}] {e:3.0f}%   {_energy_msg(e)}")
    print(f"  {cyan('MOOD  ')}  [{yellow(bar(m))}] {m:3.0f}%   {_mood_msg(m)}")

    xp_pct = (xp % XP_PER_STAGE) / XP_PER_STAGE * 100
    if stage < STAGES - 1:
        print(f"  {cyan('GROWTH')}  [{green(bar(xp_pct))}] {xp_pct:3.0f}%   "
              f"{dim(f'{xp_next:.0f} XP to evolve')}")
    else:
        print(f"  {cyan('GROWTH')}  [{green(bar(100))}] {dim('MAX — apex phantom')}")

    print()
    divider()
    print(f"  {cyan('[f]')} Feed    {cyan('[p]')} Play    "
          f"{cyan('[t]')} Test    {cyan('[s]')} Status")
    print(f"  {cyan('[e]')} Evolve  {cyan('[r]')} Reset   {cyan('[q]')} Quit")
    divider()
    print(f"\n  > ", end="", flush=True)

def _hunger_msg(h):
    if h > 80: return dim("well fed")
    if h > 50: return dim("feels peckish")
    if h > 20: return yellow("hungry!")
    return red("starving!!")

def _energy_msg(e):
    if e > 80: return dim("full of energy")
    if e > 50: return dim("a bit tired")
    if e > 20: return yellow("drained")
    return red("exhausted!!")

def _mood_msg(m):
    if m > 80: return dim("thriving")
    if m > 50: return dim("content")
    if m > 20: return yellow("restless")
    return red("upset!!")

# ── Actions ───────────────────────────────────────────────────────────────────

def action_feed(s):
    s["hunger"] = min(100, s["hunger"] + 30)
    s["mood"]   = min(100, s["mood"]   + 5)
    s["xp"]    += 5
    _flash_msg(green("  Nom nom... +30 hunger, +5 XP"))

def action_play(s):
    s["mood"]   = min(100, s["mood"]   + 25)
    s["energy"] = max(0,   s["energy"] - 10)
    s["xp"]    += 10
    _flash_msg(cyan("  Playing! +25 mood, +10 XP"))

def action_test(s):
    """Run a real system test. Snail consumes the data and grows."""
    print(f"\n  {green('Running test...')}")
    try:
        result = subprocess.run(
            ["ifconfig", "en0"],
            capture_output=True, text=True, timeout=5
        )
        lines = [l for l in result.stdout.splitlines() if l.strip()][:6]
        print()
        for line in lines:
            print(f"  {dim(line)}")
        print()
    except Exception as exc:
        print(f"  {red(str(exc))}")

    s["energy"] = max(0,   s["energy"] - 20)
    s["mood"]   = min(100, s["mood"]   + 15)
    s["xp"]    += 25
    _flash_msg(green(f"  Data consumed! +25 XP, -20 energy"))
    time.sleep(2)

def action_status(s):
    print(f"\n  {cyan('Total XP:')} {s['xp']}")
    print(f"  {cyan('Stage:   ')} {s['stage']}/{STAGES-1} — {STAGE_NAMES[s['stage']]}")
    print(f"  {cyan('Age:     ')} {age_str(s['born'])}")
    _flash_msg("")
    time.sleep(1.5)

def action_evolve(s):
    stage   = s["stage"]
    xp_need = (stage + 1) * XP_PER_STAGE
    if stage >= STAGES - 1:
        _flash_msg(yellow("  Already at maximum stage."))
    elif s["xp"] >= xp_need:
        s["stage"] += 1
        s["mood"]   = 100
        _flash_msg(green(f"  !! EVOLVED to {STAGE_NAMES[s['stage']]} !!"))
        time.sleep(1.5)
    else:
        need = xp_need - s["xp"]
        _flash_msg(yellow(f"  Need {need} more XP to evolve."))

def action_reset(s):
    print(f"\n  {red('Reset all progress? (y/N) ')}", end="", flush=True)
    ch = getch()
    if ch == "y":
        s.update(DEFAULT_STATE)
        s["born"] = int(time.time())
        _flash_msg(red("  Reset. Back to hatchling."))
        time.sleep(1)

def _flash_msg(msg):
    print(f"\n{msg}", flush=True)

# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    s = load_state()
    s = decay(s)

    while True:
        draw(s)
        ch = getch()
        print(ch)

        if ch == "f":
            action_feed(s)
        elif ch == "p":
            action_play(s)
        elif ch == "t":
            action_test(s)
        elif ch == "s":
            action_status(s)
        elif ch == "e":
            action_evolve(s)
        elif ch == "r":
            action_reset(s)
        elif ch in ("q", "\x03"):   # q or ctrl-c
            save_state(s)
            clr()
            print(cyan("  ghost//snail saved. see you next time.\n"))
            break

        save_state(s)

if __name__ == "__main__":
    main()
