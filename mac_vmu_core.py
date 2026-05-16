#!/usr/bin/env python3
"""
ghost//snail — M5 VMU Contraction Chamber
Mac orchestrator: serial engine + keyboard telemetry + Pygame retro UI
"""
import os, sys, json, time, math, threading, random
import pygame

try:
    import serial, serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    print("[WARN] pyserial not installed — running standalone (pip3 install --user pyserial)")

try:
    from pynput import keyboard as pynput_kb
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False
    print("[WARN] pynput not installed — keyboard tracking disabled (pip3 install --user pynput)")

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "images")
CIRCUITPY  = "/Volumes/CIRCUITPY"
LOCAL_JSON = os.path.join(SCRIPT_DIR, "pet.json")

def state_path():
    cp = os.path.join(CIRCUITPY, "pet.json")
    return cp if os.path.exists(CIRCUITPY) else LOCAL_JSON

# ── Constants ─────────────────────────────────────────────────────────────────
BAUD        = 115200
FPS         = 30
WIN_W       = 1000
WIN_H       = 640
STAGES      = 6
XP_STAGE    = 100
DECAY_SECS  = 10
STAGE_NAMES = ["Hatchling","Wandering Shell","Phantom Crawler",
               "Data Drifter","Ghost Protocol","Apex Phantom"]

# Retro phosphor palette
C_BG    = (  8,  14,  10)
C_PANEL = ( 11,  20,  14)
C_BORD  = (  0,  55,  38)
C_TEXT  = (  0, 220, 100)
C_AMBER = (255, 165,   0)
C_DIM   = (  0,  75,  40)
C_WHITE = (210, 255, 210)
C_RED   = (220,  40,  20)
C_CYAN  = (  0, 200, 200)

# ── RPG State Engine ──────────────────────────────────────────────────────────
class GhostSnailRPG:
    def __init__(self):
        self.lock = threading.Lock()
        self._load()
        self.volatile = {
            "wpm":       0.0,
            "backspace": 0,
            "mod":       0,
            "deduction": "Dormant",
            "last_ts":   time.time(),
            "imu_z":     0.0,
            "imu_mag":   0.0,
            "i2c":       "STANDALONE",
            "shake":     False,
            "btn_a":     False,
        }
        self._kcount = 0
        self._flow_t = time.time()

    def _load(self):
        try:
            with open(state_path()) as f:
                d = json.load(f)
        except Exception:
            d = {}
        self.stats = d.get("rpg", {
            "STR":10.0,"VIT":10.0,"AGI":10.0,
            "DEX":10.0,"INT":10.0,"LCK":10.0
        })
        self.vitals = d.get("vitals", {"hunger":80.0,"energy":90.0,"mood":70.0})
        self.xp     = d.get("xp",    0)
        self.born   = d.get("born",  int(time.time()))
        self.stage  = min(STAGES-1, self.xp // XP_STAGE)

    def save(self):
        d = {"rpg":self.stats,"vitals":self.vitals,
             "xp":self.xp,"born":self.born,"stage":self.stage,
             "last":int(time.time())}
        for p in [state_path(), LOCAL_JSON]:
            try:
                with open(p,"w") as f: json.dump(d, f)
            except Exception:
                pass
        # Simple stage int for CircuitPython device to read
        for p in [os.path.join(CIRCUITPY,"state.txt") if os.path.exists(CIRCUITPY) else None,
                  os.path.join(SCRIPT_DIR,"state.txt")]:
            if p:
                try:
                    with open(p,"w") as f: f.write(str(self.stage))
                except Exception:
                    pass

    def on_key(self, key):
        with self.lock:
            self._kcount += 1
            self.volatile["last_ts"] = time.time()
            if HAS_PYNPUT:
                if key == pynput_kb.Key.backspace:
                    self.volatile["backspace"] += 1
                elif key in (pynput_kb.Key.cmd, pynput_kb.Key.alt,
                             pynput_kb.Key.ctrl, pynput_kb.Key.shift):
                    self.volatile["mod"] += 1

    def recalculate(self):
        with self.lock:
            elapsed = time.time() - self._flow_t
            if elapsed >= 5.0:
                self.volatile["wpm"] = (self._kcount / 5.0) / (elapsed / 60.0)
                self._kcount = 0
                self._flow_t = time.time()

            wpm = self.volatile["wpm"]
            bs  = self.volatile["backspace"]

            if wpm > 70 and bs < 3:
                self.volatile["deduction"] = "Hyper-Flow State"
                self.stats["INT"] += 0.008
                self.stats["DEX"] += 0.004
                self.xp += 1
            elif bs > 8:
                self.volatile["deduction"] = "Iterative Frustration"
                self.stats["VIT"] += 0.004
            elif 0 < wpm <= 30:
                self.volatile["deduction"] = "Deep Deliberation"
                self.stats["LCK"] += 0.002
                self.stats["INT"] += 0.002
            elif wpm == 0:
                self.volatile["deduction"] = "Idle / Dormant"
            else:
                self.volatile["deduction"] = "Standard Cognition"

            self.stage = min(STAGES - 1, self.xp // XP_STAGE)

    def on_hardware(self, data: dict):
        with self.lock:
            z   = float(data.get("imu_z", 0))
            x   = float(data.get("imu_x", 0))
            y   = float(data.get("imu_y", 0))
            mag = math.sqrt(x*x + y*y + z*z)
            self.volatile.update({
                "imu_z":   z,
                "imu_mag": mag,
                "i2c":     data.get("i2c",   "STANDALONE"),
                "shake":   bool(data.get("shake", False)),
                "btn_a":   bool(data.get("btn_a", False)),
            })
            if mag > 2.5:
                self.stats["STR"] += 0.5
                self.vitals["energy"] = max(0, self.vitals["energy"] - 2)
            elif mag > 1.5:
                self.stats["AGI"] += 0.08
            if data.get("shake", False):
                self.vitals["mood"] = min(100, self.vitals["mood"] + 5)
                self.xp += 2
            if data.get("btn_a", False):
                self.vitals["hunger"] = min(100, self.vitals["hunger"] + 10)
                self.xp += 3

    def decay_loop(self):
        while True:
            time.sleep(DECAY_SECS)
            with self.lock:
                self.volatile["backspace"] = max(0, self.volatile["backspace"] - 2)
                self.volatile["wpm"]      *= 0.7
                if self.volatile["wpm"] < 3:
                    self.volatile["wpm"]      = 0.0
                    self.volatile["deduction"] = "Forgotten / Settled"
                self.vitals["hunger"] = max(0, self.vitals["hunger"] - 1.5)
                self.vitals["energy"] = max(0, self.vitals["energy"] - 0.8)
                self.vitals["mood"]   = max(0, self.vitals["mood"]   - 0.5)
            self.save()

# ── Serial Engine ─────────────────────────────────────────────────────────────
class SerialEngine(threading.Thread):
    def __init__(self, rpg):
        super().__init__(daemon=True)
        self.rpg  = rpg
        self.ser  = None
        self.port = None
        self.ok   = False

    def run(self):
        while True:
            if not self.ok:
                self._connect()
            else:
                self._read()

    def _connect(self):
        if not HAS_SERIAL:
            time.sleep(5); return
        for p in serial.tools.list_ports.comports():
            if "cu.usbserial" in p.device or "cu.usbmodem" in p.device:
                try:
                    self.ser  = serial.Serial(p.device, BAUD, timeout=0.1)
                    self.port = p.device
                    self.ok   = True
                    print(f"[SERIAL] Connected → {p.device}")
                    return
                except Exception:
                    pass
        time.sleep(2)

    def _read(self):
        try:
            if self.ser.in_waiting:
                raw = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if raw.startswith("{"):
                    self.rpg.on_hardware(json.loads(raw))
                    self._send_down()
        except Exception:
            self.ok = False; self.ser = None

    def _send_down(self):
        with self.rpg.lock:
            pkt = {
                "stage":  self.rpg.stage,
                "str":    int(self.rpg.stats["STR"]),
                "intel":  int(self.rpg.stats["INT"]),
                "dex":    int(self.rpg.stats["DEX"]),
                "state":  self.rpg.volatile["deduction"][:22],
                "hunger": int(self.rpg.vitals["hunger"]),
                "xp":     self.rpg.xp,
            }
        try:
            self.ser.write((json.dumps(pkt) + "\n").encode())
        except Exception:
            pass

# ── Pygame rendering ──────────────────────────────────────────────────────────
_img_cache = {}
def stage_img(stage, w, h):
    key = (stage, w, h)
    if key not in _img_cache:
        p = os.path.join(ASSETS_DIR, f"snail_{stage}.bmp")
        if not os.path.exists(p):
            p = os.path.join(ASSETS_DIR, "snail_0.bmp")
        raw = pygame.image.load(p).convert()
        _img_cache[key] = pygame.transform.smoothscale(raw, (w, h))
    return _img_cache[key].copy()

def glow(img, frame, str_stat):
    t   = frame * 0.045
    p   = (math.sin(t) + 1) / 2
    s   = int(p * 55 + 8)
    ov  = pygame.Surface(img.get_size())
    ov.fill((0, s, s // 3))
    img.blit(ov, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    # Slight scale pulse with STR
    scale = 1.0 + (str_stat - 10) * 0.012 + math.sin(t*0.7)*0.01
    if abs(scale - 1.0) > 0.005:
        nw = max(1, int(img.get_width()  * scale))
        nh = max(1, int(img.get_height() * scale))
        img = pygame.transform.smoothscale(img, (nw, nh))
    return img

_scan = None
def scanlines(w, h):
    global _scan
    if _scan is None or _scan.get_size() != (w, h):
        _scan = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 2):
            pygame.draw.line(_scan, (0, 0, 0, 50), (0, y), (w, y))
    return _scan

def bar(surf, x, y, w, h, pct, label, font, frame, color=None):
    pygame.draw.rect(surf, (18, 38, 22), (x, y, w, h))
    fw = int(max(0, min(w, pct/100*w)))
    if color is None:
        if pct > 60:    color = C_TEXT
        elif pct > 30:  color = C_AMBER
        else:
            pulse = (math.sin(frame * 0.18) + 1) / 2
            color = (int(200+pulse*55), 30, 0)
    pygame.draw.rect(surf, color, (x, y, fw, h))
    lbl = font.render(f"{label:<8}{int(pct):3}%", True, (8, 14, 10))
    surf.blit(lbl, (x+4, y+1))

def hdr_sweep(title, frame, font, color_fn=None):
    t = frame * 0.055
    chars = []
    for i, ch in enumerate(title):
        p = t - i * 0.10
        if color_fn:
            col = color_fn(p)
        else:
            r = max(20, min(200, int(55  + 45*math.sin(p      ))))
            g = max(20, min(255, int(195 + 50*math.sin(p+1.2  ))))
            b = max(20, min(180, int(80  + 100*math.sin(p+2.4 ))))
            col = (r, g, b)
        chars.append(font.render(ch, True, col))
    total_w = sum(s.get_width() for s in chars)
    surf = pygame.Surface((total_w, chars[0].get_height()), pygame.SRCALPHA)
    cx = 0
    for s in chars:
        surf.blit(s, (cx, 0)); cx += s.get_width()
    return surf

def age_str(born):
    s = int(time.time()) - born
    return f"{s//86400}d {(s%86400)//3600}h {(s%3600)//60}m"

# ── Main render ───────────────────────────────────────────────────────────────
def draw(screen, rpg, frame, serial_eng, fonts):
    sm, md, lg = fonts["sm"], fonts["md"], fonts["lg"]
    W, H = screen.get_size()

    GHOST_W  = int(W * 0.42)
    SIDE_X   = GHOST_W + 12
    SIDE_W   = W - SIDE_X - 8
    HDR_H    = 36
    FTR_H    = 28
    CONT_Y   = HDR_H + 4
    CONT_H   = H - HDR_H - FTR_H - 8

    screen.fill(C_BG)

    with rpg.lock:
        st  = rpg.stage
        sta = dict(rpg.stats)
        vi  = dict(rpg.vitals)
        vo  = dict(rpg.volatile)
        xp  = rpg.xp
        born= rpg.born

    # ── Header ──────────────────────────────────────────────────────────────
    pygame.draw.rect(screen, (5, 16, 9), (0, 0, W, HDR_H))
    pygame.draw.line(screen, C_BORD, (0, HDR_H-1), (W, HDR_H-1))
    title_surf = hdr_sweep("M5-VMU  //  GHOST SNAIL  //  CONTRACTION CHAMBER", frame, md)
    screen.blit(title_surf, ((W - title_surf.get_width())//2, 8))

    # ── Ghost-snail panel ────────────────────────────────────────────────────
    gr = pygame.Rect(6, CONT_Y, GHOST_W - 6, CONT_H)
    pygame.draw.rect(screen, C_PANEL, gr)
    pygame.draw.rect(screen, C_BORD,  gr, 1)

    img_h = gr.h - 42
    img_w = gr.w - 12
    img   = stage_img(st, img_w, img_h)
    img   = glow(img, frame, sta["STR"])
    # Center the (possibly scaled) image
    ix = gr.x + 6 + (img_w - img.get_width())  // 2
    iy = gr.y + 6 + (img_h - img.get_height()) // 2
    screen.blit(img, (ix, iy))

    # Stage label
    s_name = lg.render(STAGE_NAMES[st], True, C_TEXT)
    screen.blit(s_name, (gr.x + (gr.w - s_name.get_width())//2, gr.bottom - 36))
    s_sub  = sm.render(f"STAGE {st}/{STAGES-1}  ·  XP {xp}", True, C_DIM)
    screen.blit(s_sub, (gr.x + (gr.w - s_sub.get_width())//2, gr.bottom - 18))

    screen.blit(scanlines(gr.w, gr.h), gr.topleft)

    # ── Right terminal panel ─────────────────────────────────────────────────
    py = CONT_Y + 2
    BW = SIDE_W - 6

    def h1(text, col=C_AMBER):
        nonlocal py
        s = sm.render(text, True, col)
        screen.blit(s, (SIDE_X, py)); py += s.get_height() + 2

    def ln(text, col=C_TEXT, indent=8):
        nonlocal py
        s = sm.render(text, True, col)
        screen.blit(s, (SIDE_X + indent, py)); py += s.get_height() + 1

    def sp(n=5): nonlocal py; py += n

    h1("// PHYSICAL DEVICE REGISTRY")
    port = serial_eng.port or "SEARCHING..."
    ln(f"UART  : {port}", C_TEXT if serial_eng.ok else C_RED)
    ln(f"IMU Z : {vo['imu_z']:+.2f}G   MAG:{vo['imu_mag']:.2f}G")
    ln(f"I2C   : {vo['i2c']}")
    ln(f"SHAKE : {'!! YES' if vo['shake'] else 'No'}", C_AMBER if vo['shake'] else C_DIM)
    sp()

    h1("// COGNITIVE TELEMETRY  (VOLATILE)")
    ln(f"WPM        : {int(vo['wpm'])}")
    ln(f"BACKSPACES : {vo['backspace']} strikes")
    ln(f"DEDUCTION  : {vo['deduction']}", C_AMBER)
    sp()

    h1("// PERMANENT RPG MATRIX")
    BAR_H = 14
    for sn in ("STR","VIT","AGI","DEX","INT","LCK"):
        pct = min(100, (sta[sn] - 10) / 90 * 80 + 20)
        bar(screen, SIDE_X+4, py, BW, BAR_H, pct, sn, sm, frame, C_TEXT)
        # Overlay actual value
        val_s = sm.render(f"{sta[sn]:6.1f}", True, C_WHITE)
        screen.blit(val_s, (SIDE_X + BW - val_s.get_width() - 2, py+1))
        py += BAR_H + 2
    sp()

    h1("// VITALS")
    for vn, vv in vi.items():
        bar(screen, SIDE_X+4, py, BW, BAR_H, vv, vn.upper(), sm, frame)
        py += BAR_H + 2

    # ── Footer ───────────────────────────────────────────────────────────────
    fy = H - FTR_H
    pygame.draw.line(screen, C_BORD, (0, fy), (W, fy))
    pygame.draw.rect(screen, (5, 16, 9), (0, fy, W, FTR_H))

    dot_col = C_TEXT if serial_eng.ok else C_RED
    pygame.draw.circle(screen, dot_col, (14, fy + FTR_H//2), 5)
    if serial_eng.ok and (frame // 8) % 2:
        pygame.draw.circle(screen, C_WHITE, (14, fy + FTR_H//2), 3)

    status = (f"  {'LIVE' if serial_eng.ok else 'STANDALONE'}  ·  "
              f"WPM:{int(vo['wpm'])}  ·  {vo['deduction']}  ·  "
              f"IMU:{vo['imu_mag']:.2f}G  ·  STAGE:{st}  ·  AGE:{age_str(born)}  ·  "
              f"[F] feed   [P] play")
    screen.blit(sm.render(status, True, C_DIM), (28, fy + (FTR_H - sm.get_height())//2))

    screen.blit(scanlines(W, H), (0, 0))
    pygame.display.flip()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
    pygame.display.set_caption("M5-VMU // GHOST SNAIL // 1994_VER_0.9")
    clock  = pygame.time.Clock()

    fonts = {
        "sm": pygame.font.SysFont("Courier", 12, bold=True),
        "md": pygame.font.SysFont("Courier", 14, bold=True),
        "lg": pygame.font.SysFont("Courier", 17, bold=True),
    }

    rpg = GhostSnailRPG()

    threading.Thread(target=rpg.decay_loop, daemon=True).start()

    ser = SerialEngine(rpg)
    ser.start()

    if HAS_PYNPUT:
        kb = pynput_kb.Listener(on_press=rpg.on_key)
        kb.start()

    frame = 0
    save_t = time.time()

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_f:
                    with rpg.lock:
                        rpg.vitals["hunger"] = min(100, rpg.vitals["hunger"] + 30)
                        rpg.xp += 5
                elif ev.key == pygame.K_p:
                    with rpg.lock:
                        rpg.vitals["mood"]   = min(100, rpg.vitals["mood"]   + 20)
                        rpg.vitals["energy"] = min(100, rpg.vitals["energy"] + 10)
                        rpg.xp += 10

        rpg.recalculate()

        if time.time() - save_t > 30:
            rpg.save(); save_t = time.time()

        draw(screen, rpg, frame, ser, fonts)
        frame += 1
        clock.tick(FPS)

    rpg.save()
    if HAS_PYNPUT: kb.stop()
    pygame.quit()

if __name__ == "__main__":
    main()
