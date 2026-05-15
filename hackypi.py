# ghost//snail - shared display module (CircuitPython)
import board, busio, displayio, pwmio, terminalio, time, math
from adafruit_display_text import label
from adafruit_st7789 import ST7789

BG     = 0x00000A
CYAN   = 0x00FFFF
GREEN  = 0x00FF88
STAGES = 6

_dsp = _spl = _bl = None


def setup():
    global _dsp, _spl, _bl
    displayio.release_displays()
    spi = busio.SPI(clock=board.GP10, MOSI=board.GP11)
    bus = displayio.FourWire(spi, command=board.GP8, chip_select=board.GP9, reset=board.GP12)
    _dsp = ST7789(bus, rotation=270, width=240, height=135, rowstart=40, colstart=53)
    _bl  = pwmio.PWMOut(board.GP13, frequency=1000, duty_cycle=65535)
    _spl = displayio.Group()
    _dsp.show(_spl)
    return _dsp, _spl


def load_level():
    try:
        with open("/state.txt") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def save_level(n):
    try:
        with open("/state.txt", "w") as f:
            f.write(str(min(n, STAGES - 1)))
    except Exception:
        pass


def show_stage(level):
    while len(_spl):
        _spl.pop()
    path = "/images/snail_{}.bmp".format(min(level, STAGES - 1))
    try:
        f   = open(path, "rb")
        bmp = displayio.OnDiskBitmap(f)
        _spl.append(displayio.TileGrid(
            bmp, pixel_shader=getattr(bmp, "pixel_shader", displayio.ColorConverter())
        ))
    except Exception:
        _fallback(level)


def _fallback(level):
    bg  = displayio.Bitmap(_dsp.width, _dsp.height, 1)
    pal = displayio.Palette(1)
    pal[0] = BG
    _spl.append(displayio.TileGrid(bg, pixel_shader=pal))
    _label("ghost//snail", 10, 30, GREEN, 2)
    _label("stage {}".format(level), 10, 80, CYAN, 2)


def _label(msg, x, y, color, scale):
    a = label.Label(terminalio.FONT, text=msg, color=color)
    g = displayio.Group(scale=scale, x=x, y=y)
    g.append(a)
    _spl.append(g)


def overlay(msg, x=10, y=110, color=CYAN, scale=1):
    _label(msg, x, y, color, scale)


def glow(duration=2.5, pulses=2):
    """PWM sine-wave backlight pulse."""
    steps = int(duration / 0.02)
    for i in range(steps):
        t = i / steps * 2 * math.pi * pulses
        v = int((math.sin(t) + 1) / 2 * 55000 + 10000)
        _bl.duty_cycle = v
        time.sleep(0.02)
    _bl.duty_cycle = 65535


def flash(n=3, delay=0.08):
    for _ in range(n):
        _bl.duty_cycle = 0
        time.sleep(delay)
        _bl.duty_cycle = 65535
        time.sleep(delay)
