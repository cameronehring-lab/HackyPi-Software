#!/usr/bin/env python3
"""
ghost//snail — BASE_LINK  //  32-BIT VIRTUAL ARCHIVE
Hardware-gated Pygame canvas. Locks when M5Stick disconnects.
"""
import sys, os, json, time, math, threading
import pygame

try:
    import serial, serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False
    print("[WARN] pyserial missing — pip3 install --user pyserial")

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "images")

# ── Config ────────────────────────────────────────────────────────────────────
SERIAL_BAUD = 115200
GAME_RES    = (960, 720)
TARGET_FPS  = 60

# ── Hardware Gateway ──────────────────────────────────────────────────────────
class HardwareGateway:
    def __init__(self):
        self.authenticated = False
        self.active_port   = None
        self.ser           = None
        self.lock          = threading.Lock()

    def _find_port(self):
        if not HAS_SERIAL:
            return None
        for p in serial.tools.list_ports.comports():
            if "cu.usbserial" in p.device or "cu.usbmodem" in p.device:
                return p.device
        return None

    def runtime_check_loop(self):
        while True:
            time.sleep(0.5)
            port = self._find_port()
            with self.lock:
                if not port:
                    if self.authenticated:
                        print("\n[GATE_WARN] HARDWARE TERMINATED MID-SESSION. LOCKING ENGINE.")
                        self.authenticated = False
                        if self.ser:
                            try: self.ser.close()
                            except Exception: pass
                            self.ser = None
                else:
                    if not self.authenticated:
                        try:
                            self.ser         = serial.Serial(port, SERIAL_BAUD, timeout=0.1)
                            self.active_port = port
                            self.authenticated = True
                            print(f"\n[GATE_OK] HANDSHAKE CONFIRMED AT {port}")
                        except Exception:
                            pass

# ── Ghost-snail renderer ──────────────────────────────────────────────────────
_snail_cache = {}

def load_snail(stage: int, w: int, h: int) -> pygame.Surface:
    key = (stage, w, h)
    if key not in _snail_cache:
        path = os.path.join(ASSETS_DIR, f"snail_{stage}.bmp")
        if not os.path.exists(path):
            path = os.path.join(ASSETS_DIR, "snail_0.bmp")
        raw = pygame.image.load(path).convert()
        _snail_cache[key] = pygame.transform.smoothscale(raw, (w, h))
    return _snail_cache[key].copy()

def apply_glow(img: pygame.Surface, frame: int, z_force: float) -> pygame.Surface:
    t      = frame * 0.045
    pulse  = (math.sin(t) + 1) / 2
    # IMU z-force adds urgency to the glow
    boost  = max(0, (z_force - 1.0) * 30)
    s      = int(pulse * 40 + 10 + boost)
    overlay = pygame.Surface(img.get_size())
    overlay.fill((0, s, s // 3))
    img.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    # Slight vertical jitter from desk vibrations
    jitter = int((z_force - 1.0) * 12) if z_force > 1.1 else 0
    if jitter:
        jittered = pygame.Surface(img.get_size())
        jittered.fill((8, 12, 20))
        jittered.blit(img, (0, -jitter))
        return jittered
    return img

# ── Scanline surface (built once, alpha-correct) ──────────────────────────────
_scanlines = None

def get_scanlines(w: int, h: int) -> pygame.Surface:
    global _scanlines
    if _scanlines is None or _scanlines.get_size() != (w, h):
        _scanlines = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 4):
            pygame.draw.line(_scanlines, (0, 0, 0, 55), (0, y), (w, y), 2)
    return _scanlines

# ── Locked screen ─────────────────────────────────────────────────────────────
def draw_locked(screen: pygame.Surface, font_hud, font_log, frame: int):
    screen.fill((10, 10, 10))
    t  = frame * 0.04
    r  = max(40, int(60 + 20 * math.sin(t)))
    pygame.draw.rect(screen, (r, 15, 15), (80, 255, 800, 210), 3)
    screen.blit(
        font_hud.render("ACCESS DENIED  //  HARDWARE BUS DORMANT", True, (220, 50, 50)),
        (100, 300)
    )
    screen.blit(
        font_log.render(
            "Plug the M5Stick Plus2 into your Mac via USB to unlock the terminal bridge.",
            True, (160, 90, 90)
        ),
        (100, 360)
    )
    # Pulsing border on the whole window
    pb = max(0, int(30 * math.sin(t * 1.5)))
    pygame.draw.rect(screen, (pb, 0, 0), (0, 0, GAME_RES[0], GAME_RES[1]), 4)

# ── Active screen ─────────────────────────────────────────────────────────────
def draw_active(screen, font_hud, font_log, telemetry, gateway, frame):
    W, H = GAME_RES

    # GBA-era blue slate
    screen.fill((20, 24, 40))

    # Outer system bezel
    pygame.draw.rect(screen, (40, 50, 80), (28, 28, W-56, H-56), 5)

    # Panels
    CREATURE_RECT = pygame.Rect(58, 58, 420, 420)
    STATS_RECT    = pygame.Rect(498, 58, W-558, 420)
    TICKER_RECT   = pygame.Rect(58, 496, W-116, H-562)

    for r in (CREATURE_RECT, STATS_RECT, TICKER_RECT):
        pygame.draw.rect(screen, (8, 12, 20), r)
        pygame.draw.rect(screen, (40, 50, 80), r, 1)

    # ── Ghost-snail creature (replaces geometric placeholder) ──
    z = telemetry.get("IMU_Z_Force", 1.0)
    img = load_snail(0, CREATURE_RECT.w - 20, CREATURE_RECT.h - 50)
    img = apply_glow(img, frame, z)
    # Center in creature panel
    ix = CREATURE_RECT.x + (CREATURE_RECT.w - img.get_width())  // 2
    iy = CREATURE_RECT.y + (CREATURE_RECT.h - img.get_height()) // 2 - 10
    screen.blit(img, (ix, iy))

    # Stage label under creature
    lbl = font_log.render("HATCHLING  //  STAGE 0", True, (0, 200, 150))
    screen.blit(lbl, (CREATURE_RECT.x + (CREATURE_RECT.w - lbl.get_width())//2,
                      CREATURE_RECT.bottom - 28))

    # Scanlines over creature panel only
    screen.blit(get_scanlines(CREATURE_RECT.w, CREATURE_RECT.h), CREATURE_RECT.topleft)

    # ── Stats panel ──
    sx, sy = STATS_RECT.x + 14, STATS_RECT.y + 14
    port = gateway.active_port or "—"

    def stat(text, color=(240, 200, 80)):
        nonlocal sy
        screen.blit(font_log.render(text, True, color), (sx, sy))
        sy += 22

    stat("VMU CORE MATRIX ACTIVE", (0, 255, 200))
    sy += 8
    stat(f"HARDWARE ADDR  :  {port}")
    stat(f"ACCEL Z-FORCE  :  {z:.2f} G", (240, 240, 240))
    sy += 14
    stat("// BASELINE TELEMETRY", (100, 130, 200))
    stat(f"FRAME          :  {frame}")
    stat(f"Z PEAK         :  {telemetry.get('IMU_Z_Peak', z):.2f} G")
    sy += 14
    stat("// GHOST SNAIL STATUS", (100, 130, 200))
    stat("STAGE          :  0 / 5  (Hatchling)")
    stat("XP             :  0")
    stat("HUNGER         :  80%")
    stat("MOOD           :  70%")

    # IMU intensity bar
    sy += 10
    bw  = STATS_RECT.w - 28
    bh  = 12
    pct = min(100, (z - 0.8) / 2.2 * 100)
    pygame.draw.rect(screen, (20, 30, 50), (sx, sy, bw, bh))
    fw  = int(pct / 100 * bw)
    col = (0,200,100) if pct < 50 else ((255,165,0) if pct < 80 else (220,40,20))
    pygame.draw.rect(screen, col, (sx, sy, fw, bh))
    screen.blit(font_log.render(f"IMU INTENSITY  {int(pct):3}%", True, (8,12,20)), (sx+4, sy+1))

    # ── Scrolling ticker ──
    tx, ty = TICKER_RECT.x + 12, TICKER_RECT.y + 10
    scroll = (frame // 2) % (TICKER_RECT.w + 800)
    lines = [
        ("OS_DOCK_SYS  >  32-BIT RENDERING DRIVERS STABLE.  PIPELINE NOMINAL.",    (140, 160, 190)),
        ("OS_DOCK_SYS  >  GHOST-SNAIL VMU ENTITY LOADED.  AWAITING TELEMETRY.",     (100, 200, 120)),
        ("OS_DOCK_SYS  >  HARDWARE GATE CONFIRMED.  BIOMETRIC HANDSHAKE LIVE.",     (100, 200, 120)),
    ]
    for i, (text, col) in enumerate(lines):
        s = font_log.render(text, True, col)
        # Static lines top, scrolling bottom
        if i < 2:
            screen.blit(s, (tx, ty + i * 22))
        else:
            screen.blit(s, (TICKER_RECT.right - scroll, ty + i * 22))

    # Global scanlines
    screen.blit(get_scanlines(W, H), (0, 0))

# ── Main ──────────────────────────────────────────────────────────────────────
def execute_baseline_deck():
    pygame.init()
    screen = pygame.display.set_mode(GAME_RES)
    pygame.display.set_caption("BASE_LINK  //  32-BIT VIRTUAL ARCHIVE")
    clock = pygame.time.Clock()

    font_hud = pygame.font.SysFont("Courier", 18, bold=True)
    font_log = pygame.font.SysFont("Courier", 14, bold=True)

    gateway = HardwareGateway()
    threading.Thread(target=gateway.runtime_check_loop, daemon=True).start()

    print("=" * 52)
    print("  INITIALIZING TERMINAL BRIDGE: WAITING FOR DEVICE  ")
    print("=" * 52)

    telemetry = {"IMU_Z_Force": 1.0}
    frame     = 0
    running   = True

    while running:
        frame += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        # ── Hardware gate check ──
        with gateway.lock:
            ok  = gateway.authenticated
            ser = gateway.ser

        if not ok:
            draw_locked(screen, font_hud, font_log, frame)
            pygame.display.flip()
            clock.tick(15)   # low FPS while locked
            continue

        # ── Ingest serial telemetry ──
        if ser:
            try:
                while ser.in_waiting:
                    raw = ser.readline().decode("utf-8", errors="ignore").strip()
                    if raw.startswith("{"):
                        telemetry.update(json.loads(raw))
            except Exception:
                pass

        # ── Render active frame ──
        draw_active(screen, font_hud, font_log, telemetry, gateway, frame)
        pygame.display.flip()
        clock.tick(TARGET_FPS)

    pygame.quit()

if __name__ == "__main__":
    execute_baseline_deck()
