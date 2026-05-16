#!/usr/bin/env python3
"""ghost//snail — full-screen braille tamagotchi"""
import os, sys, time, json, subprocess, termios, tty, select, random, math, re

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

GHOST_IMG  = "/Users/cehring/.claude/image-cache/f9276175-ce15-4894-93b6-0e4a48dc9120/1.png"
CIRCUITPY  = "/Volumes/CIRCUITPY"
STAGES     = 6
XP_STAGE   = 100
STAGE_NAMES = ["Hatchling","Wandering Shell","Phantom Crawler",
               "Data Drifter","Ghost Protocol","Apex Phantom"]
DEFAULT = {"stage":0,"hunger":80,"energy":90,"mood":70,
           "xp":0,"born":int(time.time()),"last":int(time.time())}

# ── ANSI ──────────────────────────────────────────────────────────────────────
def fg(r,g,b):  return "\033[38;2;%d;%d;%dm"%(r,g,b)
def bg_(r,g,b): return "\033[48;2;%d;%d;%dm"%(r,g,b)
def rst():      return "\033[0m"
def hide():     return "\033[?25l"
def show():     return "\033[?25h"
def home():     return "\033[H"
def clr():      return "\033[2J\033[H"
_RE = re.compile(r'\033\[[^m]*m')
def vlen(s):    return len(_RE.sub("",s))

def pad(s, w):
    v = vlen(s)
    return s + " " * max(0, w - v)

# ── Braille conversion ────────────────────────────────────────────────────────
# dot layout within a 2-wide × 4-tall pixel block
_DOTS = [(0,0,0x01),(0,1,0x02),(0,2,0x04),(0,3,0x40),
         (1,0,0x08),(1,1,0x10),(1,2,0x20),(1,3,0x80)]

def build_braille(path, cols, rows, threshold=55):
    """Return 2-D list of (codepoint, alpha_frac) for braille rendering."""
    pw, ph = cols*2, rows*4
    img = Image.open(path).convert("RGBA")
    img = img.resize((pw, ph), Image.LANCZOS)
    rpix = img.load()
    grid = []
    for br in range(rows):
        row = []
        for bc in range(cols):
            bits = 0
            alpha_sum = 0
            for dx, dy, bit in _DOTS:
                x, y = bc*2+dx, br*4+dy
                if x < pw and y < ph:
                    r2,g2,b2,a = rpix[x, y]
                    alpha_sum += a
                    lum = (r2+g2+b2)//3
                    if a > 30 and lum > threshold:
                        bits |= bit
            row.append((0x2800+bits, alpha_sum / (8*255)))
        grid.append(row)
    return grid

# ── Matrix rain ───────────────────────────────────────────────────────────────
_RC = list("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklm0123456789@#$%*!/\\|ｱｲｳｴｵｶｷｸｹｺ")

class Col:
    __slots__ = ("h","pos","spd","ln","chars")
    def __init__(self, h):
        self.h     = h
        self.pos   = random.uniform(-h, 0)
        self.spd   = random.uniform(0.3, 2.2)
        self.ln    = random.randint(4, 20)
        self.chars = [random.choice(_RC) for _ in range(h+24)]
    def tick(self):
        self.pos += self.spd
        if self.pos - self.ln > self.h:
            self.pos = random.uniform(-self.h//2, -2)
            self.spd = random.uniform(0.3, 2.2)
            self.ln  = random.randint(4, 20)
        if random.random() < 0.04:
            self.chars[random.randint(0, len(self.chars)-1)] = random.choice(_RC)
    def cell(self, y):
        d = y - self.pos
        if d < 0 or d > self.ln: return None, 0.0
        return self.chars[y % len(self.chars)], max(0.0, 1.0 - d/self.ln)

class Rain:
    def __init__(self, w, h):
        self.cols = [Col(h) for _ in range(w)]
        self.w, self.h = w, h
    def tick(self):
        for c in self.cols: c.tick()
    def cell(self, x, y):
        return self.cols[x].cell(y) if 0 <= x < self.w else (None, 0)

def rain_char(ch, br):
    if br > 0.88: return fg(230,255,230) + ch + rst()
    if br > 0.45: return fg(0, int(200*br), int(40*br)) + ch + rst()
    if br > 0.0:  return fg(0, int(80*br),  0           ) + ch + rst()
    return " "

# ── Ghost-snail glow color ────────────────────────────────────────────────────
def glow(frame, row, col, bw, bh, alpha):
    """True-color RGB for a braille cell based on position + frame."""
    t  = frame * 0.07
    rp = row  / max(1, bh)
    cp = col  / max(1, bw)

    # Horizontal split: left=ghost (white-green), right=shell (green)
    shell = max(0.0, (cp - 0.42) / 0.58)

    wave  = math.sin(t + rp*3.5 + cp*2.1)
    pulse = (wave + 1) / 2          # 0→1

    # Ghost: pale white pulsing toward cyan
    gr = int((1-shell) * (180 + pulse*75) + shell * (0  + pulse*20))
    gg = int(            (190 + pulse*65)                            )
    gb = int((1-shell) * (200 + pulse*55) + shell * (80 + pulse*60) )

    # Dim by alpha (transparent parts stay dim)
    dim = 0.3 + alpha * 0.7
    return fg(max(0,min(255,int(gr*dim))),
              max(0,min(255,int(gg*dim))),
              max(0,min(255,int(gb*dim))))

# ── Header ────────────────────────────────────────────────────────────────────
def header(frame, tw):
    title = "g h o s t / / s n a i l"
    t = frame * 0.05
    out = ""
    for i, ch in enumerate(title):
        p = t - i*0.11
        r = max(20, min(255, int(70  + 80 *math.sin(p      ))))
        g = max(20, min(255, int(200 + 55 *math.sin(p+1.2  ))))
        b = max(20, min(255, int(130 + 125*math.sin(p+2.5  ))))
        out += fg(r,g,b) + ch
    out += rst()
    lpad = (tw - len(title)) // 2
    border = fg(0,55,75) + "═"*tw + rst()
    mid    = " "*lpad + out + " "*max(0, tw - lpad - len(title))
    return [border, mid, border]

# ── Side panel ────────────────────────────────────────────────────────────────
SIDE_W = 30

def sbar(label, pct, frame, w=SIDE_W):
    bw = w - len(label) - 8
    fi = max(0, min(bw, int(pct/100*bw)))
    em = max(0, bw - fi)
    if pct > 60:   rc,gc,bc = 0,   200, 100
    elif pct > 30: rc,gc,bc = 200, 200,   0
    else:
        p = (math.sin(frame*0.25)+1)/2
        rc,gc,bc = int(220+p*35), 30, 0
    bar = fg(rc,gc,bc)+"█"*fi+rst()+fg(45,45,45)+"░"*em+rst()
    return " "+fg(0,200,220)+label+rst()+" ["+bar+"] "+str(int(pct))+"%"

def age_str(born):
    s = int(time.time()) - born
    return "%dd %dh %dm"%(s//86400,(s%86400)//3600,(s%3600)//60)

def side_panel(s, frame, h):
    stage = s["stage"]
    xp    = s["xp"]
    xp_p  = (xp % XP_STAGE) / XP_STAGE * 100
    sep   = fg(0,55,75) + "─"*SIDE_W + rst()
    M = []
    def a(ln): M.append(ln)

    a(sep)
    name = ("Stg "+str(stage)+": "+STAGE_NAMES[stage])[:SIDE_W-2]
    a(" "+fg(0,255,160)+name+rst())
    a(sep); a("")
    a(sbar("HUNGER", s["hunger"], frame))
    a(sbar("ENERGY", s["energy"], frame))
    a(sbar("MOOD  ", s["mood"],   frame))
    a(sbar("GROWTH", xp_p if stage<STAGES-1 else 100, frame))
    a(""); a(sep)
    a(" "+fg(100,220,220)+"XP:  "+str(xp)+rst())
    a(" "+fg(100,220,220)+"AGE: "+age_str(s["born"])+rst())
    a(""); a(sep)
    for k,lbl in [("f","Feed"),("p","Play"),("t","Test Data"),
                  ("e","Evolve"),("s","Status"),("r","Reset"),("q","Quit")]:
        a(" "+fg(0,200,220)+"["+k+"]"+rst()+" "+lbl)
    a(""); a(sep)

    while len(M) < h: M.append("")
    return [pad(ln, SIDE_W) for ln in M[:h]]

# ── Full-frame render ─────────────────────────────────────────────────────────
HDR = 3; FTR = 2

def render(s, frame, rain, braille, tw, th):
    mw  = max(4, tw - SIDE_W - 1)
    ch  = max(4, th - HDR - FTR)
    bw  = len(braille[0]) if braille else 0
    bh  = len(braille)    if braille else 0
    sep = fg(0,55,75)+"│"+rst()

    rain.tick()
    buf = [hide(), home()]

    for hl in header(frame, tw):
        buf.append(hl+"\n")

    sl = side_panel(s, frame, ch)

    for row in range(ch):
        line = ""
        for col in range(mw):
            rain_ch, rain_br = rain.cell(col, row)

            if braille and row < bh and col < bw:
                cp, alpha = braille[row][col]
                if cp != 0x2800:
                    # Braille glyph with glow color, bg tinted from rain
                    color = glow(frame, row, col, bw, bh, alpha)
                    # Subtle rain-tinted background
                    rbr = rain_br * 0.25
                    bg_r = int(rbr*0)
                    bg_g = int(rbr*60)
                    bg_b = int(rbr*15)
                    line += bg_(bg_r,bg_g,bg_b) + color + chr(cp) + rst()
                else:
                    # Transparent braille cell → show rain
                    line += rain_char(rain_ch, rain_br) if rain_ch else " "
            else:
                line += rain_char(rain_ch, rain_br) if rain_ch else " "

        side = sl[row] if row < len(sl) else " "*SIDE_W
        buf.append(line + sep + side + "\n")

    buf.append(fg(0,55,75)+"═"*tw+rst()+"\n")
    buf.append(fg(0,130,130)+"  > "+rst()+" "*(tw-4)+"\n")
    buf.append(show())
    sys.stdout.write("".join(buf))
    sys.stdout.flush()

# ── Rain takeover (test action) ───────────────────────────────────────────────
def rain_takeover(tw, th, duration=2.5):
    full = Rain(tw, th)
    t0 = time.time()
    sys.stdout.write(hide())
    while time.time()-t0 < duration:
        full.tick()
        buf = [home()]
        for row in range(th):
            line = ""
            for col in range(tw):
                ch2, br2 = full.cell(col, row)
                line += rain_char(ch2, br2) if ch2 else " "
            buf.append(line+"\n")
        sys.stdout.write("".join(buf))
        sys.stdout.flush()
        time.sleep(0.04)
    sys.stdout.write(show())

# ── Evolve flash ──────────────────────────────────────────────────────────────
def evolve_flash(stage, tw, th):
    sys.stdout.write(hide())
    for i in range(8):
        sys.stdout.write(clr())
        if i % 2 == 0:
            for r2 in range(min(th, 24)):
                frac = r2/24
                sys.stdout.write(fg(int(frac*20),int(frac*255),int(frac*160))+"█"*tw+rst()+"\n")
        sys.stdout.flush()
        time.sleep(0.07)
    sys.stdout.write(clr())
    ctr = lambda s2: s2.center(tw)
    print(fg(0,255,160)+"═"*tw+rst())
    print(fg(255,255,255)+ctr("!! E V O L V E D !!")+rst())
    print(fg(0,255,160)+ctr("→  "+STAGE_NAMES[stage])+rst())
    print(fg(0,255,160)+"═"*tw+rst())
    sys.stdout.write(show())
    sys.stdout.flush()
    time.sleep(3.0)

# ── State ─────────────────────────────────────────────────────────────────────
def load_state():
    try:
        with open(os.path.join(CIRCUITPY,"pet.json")) as f:
            d=json.load(f)
            for k,v in DEFAULT.items(): d.setdefault(k,v)
            return d
    except: return dict(DEFAULT)

def save_state(s):
    s["last"]=int(time.time())
    try:
        with open(os.path.join(CIRCUITPY,"pet.json"),"w") as f: json.dump(s,f)
        with open(os.path.join(CIRCUITPY,"state.txt"),"w") as f: f.write(str(s["stage"]))
    except: pass

def decay(s):
    el=max(0,int(time.time())-s.get("last",int(time.time())))
    m=el/60
    s["hunger"]=max(0,s["hunger"]-m*0.8)
    s["energy"]=max(0,s["energy"]-m*0.4)
    s["mood"]  =max(0,s["mood"]  -m*0.3)
    return s

# ── Input ─────────────────────────────────────────────────────────────────────
def poll(timeout=0.067):
    fd=sys.stdin.fileno()
    old=termios.tcgetattr(fd)
    tty.setraw(fd)
    try:
        r,_,_=select.select([sys.stdin],[],[],timeout)
        if r: return sys.stdin.read(1).lower()
        return None
    finally: termios.tcsetattr(fd,termios.TCSADRAIN,old)

# ── Actions ───────────────────────────────────────────────────────────────────
def do_feed(s):
    s["hunger"]=min(100,s["hunger"]+30); s["mood"]=min(100,s["mood"]+5); s["xp"]+=5

def do_play(s):
    s["mood"]=min(100,s["mood"]+25); s["energy"]=max(0,s["energy"]-10); s["xp"]+=10

def do_test(s, tw, th):
    rain_takeover(tw, th, duration=2.2)
    sys.stdout.write(clr())
    try:
        r2=subprocess.run(["ifconfig","en0"],capture_output=True,text=True,timeout=5)
        for ln in [l for l in r2.stdout.splitlines() if l.strip()][:8]:
            print("  "+fg(0,220,110)+ln+rst())
    except Exception as e: print("  "+fg(220,50,0)+str(e)+rst())
    print("\n  "+fg(0,255,140)+"consumed.  +25 XP  -20 energy"+rst())
    sys.stdout.flush()
    s["energy"]=max(0,s["energy"]-20); s["mood"]=min(100,s["mood"]+15); s["xp"]+=25
    time.sleep(2.5)

def do_status(s):
    sys.stdout.write(clr())
    print(fg(0,200,200)+"  XP:    "+rst()+str(s["xp"]))
    print(fg(0,200,200)+"  Stage: "+rst()+str(s["stage"])+"/"+str(STAGES-1)+" — "+STAGE_NAMES[s["stage"]])
    print(fg(0,200,200)+"  Age:   "+rst()+age_str(s["born"]))
    sys.stdout.flush()
    time.sleep(2.0)

def do_evolve(s, tw, th):
    st=s["stage"]; need=(st+1)*XP_STAGE
    if st>=STAGES-1: return
    if s["xp"]>=need:
        s["stage"]+=1; s["mood"]=100
        evolve_flash(s["stage"], tw, th)
    # else silently ignore (user sees growth bar)

def do_reset(s, tw, th):
    sys.stdout.write(clr()+fg(220,50,0)+"  Reset all progress? (y/N) "+rst())
    sys.stdout.flush()
    ch2=poll(timeout=10)
    if ch2=="y":
        b=int(time.time()); s.clear(); s.update(DEFAULT); s["born"]=b

# ── Braille loader ────────────────────────────────────────────────────────────
def load_braille(tw, th):
    if not HAS_PIL: return None
    mw = max(4, tw - SIDE_W - 1)
    ch = max(4, th - HDR - FTR)
    try:
        return build_braille(GHOST_IMG, mw, ch)
    except: return None

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    s=load_state(); s=decay(s)
    tw,th=os.get_terminal_size()
    braille=load_braille(tw,th)
    rain=Rain(max(4,tw-SIDE_W-1), max(4,th-HDR-FTR))
    frame=0

    sys.stdout.write(clr())
    try:
        while True:
            ntw,nth=os.get_terminal_size()
            if (ntw,nth)!=(tw,th):
                tw,th=ntw,nth
                braille=load_braille(tw,th)
                rain=Rain(max(4,tw-SIDE_W-1), max(4,th-HDR-FTR))

            render(s, frame, rain, braille, tw, th)
            frame+=1

            ch=poll(0.067)
            if ch is None: continue

            if   ch=="f": do_feed(s)
            elif ch=="p": do_play(s)
            elif ch=="t": do_test(s, tw, th)
            elif ch=="s": do_status(s)
            elif ch=="e": do_evolve(s, tw, th)
            elif ch=="r": do_reset(s, tw, th)
            elif ch in ("q","\x03"):
                save_state(s)
                sys.stdout.write(clr()+show()+fg(0,200,150)+"  ghost//snail saved.\n"+rst())
                break
            save_state(s)
    except KeyboardInterrupt:
        sys.stdout.write(clr()+show())

if __name__=="__main__":
    main()
