#!/usr/bin/env python3
"""
http://localhost:8000
Arrows / WASD = move     Shift = focus
Z = shoot (hold)         X = bomb          Esc = quit
"""
import asyncio
import math
import os
import random
import sys

if "--selftest" in sys.argv:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame

#
# Constants

FW, FH = 480, 660            # playfield size
WIN_W, WIN_H = 760, 700
FX, FY = 20, 20              # playfield position
FPS = 60
TAU = math.tau

PLAYER_SPEED = 4.4
PLAYER_FOCUS = 1.9
HIT_R = 2.0                  # player hitbox radius
GRAZE_R = 15.0               # graze radius
MAX_BULLETS = 1500

COLORS = {
    "red": (255, 70, 70),
    "blue": (90, 150, 255),
    "yellow": (255, 230, 80),
    "green": (90, 235, 130),
    "purple": (205, 100, 255),
    "white": (235, 235, 255),
    "cyan": (90, 235, 255),
}
# size name -> (sprite radius, hit radius)
SIZES = {"s": (4, 2.6), "m": (6, 4.2), "l": (11, 8.0)}
PALETTE = ["blue", "cyan", "green", "purple"]

BINFO = {}   # (color, size) -> (sprite, offset, hit_sq, graze_sq)
PBUL_SPR = None


def init_sprites():
    global PBUL_SPR
    for cname, col in COLORS.items():
        for sname, (r, hr) in SIZES.items():
            c = r + 3
            s = pygame.Surface((c * 2, c * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*col, 70), (c, c), r + 2)
            pygame.draw.circle(s, col, (c, c), r)
            pygame.draw.circle(s, (255, 255, 255), (c, c), max(1, int(r * 0.6)))
            BINFO[(cname, sname)] = (s.convert_alpha(), c, (hr + HIT_R) ** 2, (hr + GRAZE_R) ** 2)
    p = pygame.Surface((6, 16), pygame.SRCALPHA)
    pygame.draw.rect(p, (140, 220, 255, 200), (0, 0, 6, 16), border_radius=3)
    pygame.draw.rect(p, (255, 255, 255, 230), (2, 1, 2, 14))
    PBUL_SPR = p.convert_alpha()



# Bullets
class Bullet:
    """a = angle, s = speed. For `fx` frames, da (turn rate) and ds apply."""
    __slots__ = ("x", "y", "vx", "vy", "a", "s", "da", "ds", "fx",
                 "spr", "off", "hs", "gs", "gz")

    def __init__(self, x, y, a, s, col, size, da, ds, fx):
        self.x, self.y, self.a, self.s = x, y, a, s
        self.da, self.ds, self.fx = da, ds, fx
        self.vx = math.cos(a) * s
        self.vy = math.sin(a) * s
        self.spr, self.off, self.hs, self.gs = BINFO[(col, size)]
        self.gz = False



# Boss patterns
def pat_opening(g, t):
    b = g.boss
    b.tx, b.ty = FW / 2 + math.sin(t * 0.012) * 120, 115
    if t % 8 == 0:
        n, off = 18, t * 0.09
        for i in range(n):
            g.fire(b.x, b.y, off + i * TAU / n, 2.0, "blue", "s")
    if t % 70 == 35:
        a = g.aim()
        for i in range(-2, 3):
            g.fire(b.x, b.y, a + i * 0.16, 3.2, "red", "m")


def pat_spiral(g, t):
    b = g.boss
    b.tx, b.ty = FW / 2, 125
    if t % 3 == 0:
        base = t * 0.0215 + 0.6 * math.sin(t * 0.013)
        for k in range(5):
            g.fire(b.x, b.y, base + k * TAU / 5, 2.4, "blue", "s")
    if t % 5 == 0:
        base = -t * 0.017
        for k in range(5):
            g.fire(b.x, b.y, base + k * TAU / 5, 1.9, "red", "s")
    if t % 120 == 90:
        a = g.aim()
        for i in range(-2, 3):
            g.fire(b.x, b.y, a + i * 0.22, 2.8, "yellow", "l")


def pat_curve(g, t):
    b = g.boss
    b.tx, b.ty = FW / 2 + math.sin(t * 0.015) * 140, 130
    if t % 10 == 0:
        n, off = 14, t * 0.05
        for i in range(n):
            a = off + i * TAU / n
            g.fire(b.x, b.y, a, 2.2, "cyan", "s", da=0.014, fx=90)
            g.fire(b.x, b.y, a + TAU / n / 2, 2.2, "purple", "s", da=-0.014, fx=90)
    if t % 45 == 20:
        a = g.aim()
        for i in range(-3, 4):
            g.fire(b.x, b.y, a + i * 0.15, 3.0, "red", "m")


def pat_final(g, t):
    b = g.boss
    b.tx = FW / 2 + math.sin(t * 0.011) * 110
    b.ty = 130 + math.sin(t * 0.022) * 30
    if t % 4 == 0:
        base = t * 0.07 + 1.3 * math.sin(t * 0.02)
        sp = 1.9 + 0.9 * math.sin(t * 0.045)
        col = PALETTE[(t // 40) % 4]
        for k in range(3):
            g.fire(b.x, b.y, base + k * TAU / 3, sp, col, "s")
            g.fire(b.x, b.y, -base + k * TAU / 3, sp * 0.8, "white", "s")
    if t % 100 == 60:
        n = 40
        for ring, spd in enumerate((5.2, 6.0, 6.8)):
            off = ring * TAU / n / 3
            for i in range(n):
                g.fire(b.x, b.y, off + i * TAU / n, spd,
                       "yellow" if ring % 2 else "red", "m", ds=-0.075, fx=55)
    if t % 24 == 12:
        a = g.aim()
        for i in (-1, 0, 1):
            g.fire(b.x, b.y, a + i * 0.12, 4.2, "white", "s")


PHASES = [
    dict(name=None, hp=450, time=40 * FPS, fn=pat_opening),
    dict(name='Whirl Sign "Twin Spiral Bloom"', hp=700, time=45 * FPS, fn=pat_spiral),
    dict(name='Curve Sign "Tidal Lattice"', hp=900, time=50 * FPS, fn=pat_curve),
    dict(name='Final Sign "Infinite Petal Storm"', hp=1100, time=60 * FPS, fn=pat_final),
]


class Boss:
    def __init__(self):
        self.x, self.y = FW / 2, -60.0
        self.tx, self.ty = FW / 2, 110.0


class Inp:
    def __init__(self):
        self.left = self.right = self.up = self.down = False
        self.shoot = self.focus = self.bomb = False



# Game
class Game:
    def __init__(self, screen):
        self.screen = screen
        self.field = pygame.Surface((FW, FH))
        self.f_big = pygame.font.Font(None, 54)
        self.f_mid = pygame.font.Font(None, 30)
        self.f_small = pygame.font.Font(None, 22)
        self.stars = [[random.random() * FW, random.random() * FH,
                       random.uniform(0.5, 2.5), random.choice((1, 1, 2))] for _ in range(70)]
        self.hi = 0
        self.t_all = 0
        self.god = False
        self.state = "title"
        self.reset()

    #setup
    def reset(self):
        self.score = 0
        self.graze = 0
        self.combo = 0
        self.gz_timer = 0
        self.lives = 3
        self.bombs = 2
        self.px, self.py = FW / 2, FH - 70
        self.focus = False
        self.inv = 0
        self.bomb_t = 0
        self.shot_cd = 0
        self.bullets = []
        self.pbul = []
        self.boss = Boss()
        self.phase = -1
        self.trans = 90
        self.pt = 0
        self.timer = 0
        self.boss_hp = self.boss_max = 1
        self.phase_clean = True
        self.phase_graze = 0
        self.msg = None

    def start(self):
        self.reset()
        self.state = "play"

    def keydown(self, key):
        if self.state != "play" and key in (pygame.K_z, pygame.K_RETURN):
            self.start()

    # helps
    def fire(self, x, y, a, s, col="red", size="s", da=0.0, ds=0.0, fx=0):
        if len(self.bullets) < MAX_BULLETS:
            self.bullets.append(Bullet(x, y, a, s, col, size, da, ds, fx))

    def aim(self):
        return math.atan2(self.py - self.boss.y, self.px - self.boss.x)

    def add_graze(self, n):
        for _ in range(n):
            self.combo += 1
            self.score += 50 + 10 * min(self.combo, 20)
            self.graze += 1
            if self.graze % 200 == 0:
                self.bombs = min(5, self.bombs + 1)
        self.phase_graze += n
        self.gz_timer = 45

    #phases
    def start_phase(self, i):
        if i >= len(PHASES):
            self.score += self.lives * 10000
            self.hi = max(self.hi, self.score)
            self.state = "clear"
            return
        ph = PHASES[i]
        self.phase = i
        self.pt = 0
        self.boss_hp = self.boss_max = ph["hp"]
        self.timer = ph["time"]
        self.phase_clean = True
        self.phase_graze = 0
        self.bullets.clear()

    def end_phase(self, captured):
        ph = PHASES[self.phase]
        if ph["name"]:
            if captured and self.phase_clean:
                bonus = 20000 + self.phase_graze * 200
                self.score += bonus
                self.msg = ("SPELL CARD CAPTURED!  +%d" % bonus, 120)
            elif captured:
                self.msg = ("Spell card broken", 100)
            else:
                self.msg = ("Time out...", 100)
        else:
            self.score += 5000
        self.bullets.clear()
        self.trans = 100

    # frame updating
    def update(self, inp):
        self.t_all += 1
        for s in self.stars:
            s[1] += s[2]
            if s[1] > FH:
                s[1] = 0
                s[0] = random.random() * FW
        if self.state != "play":
            return
        self.update_player(inp)
        self.update_boss()
        self.update_bullets()
        if self.state != "play":
            return
        self.update_pbul()
        if self.trans <= 0 and self.phase >= 0:
            if self.boss_hp <= 0:
                self.end_phase(True)
            elif self.timer <= 0:
                self.end_phase(False)
        if self.msg:
            self.msg = (self.msg[0], self.msg[1] - 1) if self.msg[1] > 1 else None
        self.hi = max(self.hi, self.score)

    def update_player(self, inp):
        spd = PLAYER_FOCUS if inp.focus else PLAYER_SPEED
        dx = int(inp.right) - int(inp.left)
        dy = int(inp.down) - int(inp.up)
        if dx and dy:
            spd *= 0.7071
        self.px = min(max(self.px + dx * spd, 8), FW - 8)
        self.py = min(max(self.py + dy * spd, 12), FH - 12)
        self.focus = inp.focus
        if self.inv > 0:
            self.inv -= 1
        if inp.bomb and self.bombs > 0 and self.bomb_t <= 0:
            self.bombs -= 1
            self.bomb_t = 45
            self.inv = max(self.inv, 90)
            self.phase_clean = False
        if self.bomb_t > 0:
            self.bomb_t -= 1
            if self.trans <= 0 and self.pt >= 60:
                self.boss_hp -= 3
        if self.shot_cd > 0:
            self.shot_cd -= 1
        if inp.shoot and self.shot_cd <= 0:
            self.shot_cd = 3
            x, y = self.px, self.py - 10
            if self.focus:
                for ox in (-9, -3, 3, 9):
                    self.pbul.append([x + ox, y, 0.0, -17.0])
            else:
                for ox in (-10, 0, 10):
                    self.pbul.append([x + ox, y, 0.0, -15.0])
                for vx in (-2.6, 2.6):
                    self.pbul.append([x, y, vx, -15.0])
        if self.gz_timer > 0:
            self.gz_timer -= 1
        else:
            self.combo = 0

    def update_boss(self):
        b = self.boss
        b.x += (b.tx - b.x) * 0.04
        b.y += (b.ty - b.y) * 0.04
        if self.trans > 0:
            self.trans -= 1
            b.tx, b.ty = FW / 2, 110
            if self.trans == 0:
                self.start_phase(self.phase + 1)
            return
        self.pt += 1
        self.timer -= 1
        b.tx, b.ty = FW / 2, 120
        if self.pt >= 45:
            PHASES[self.phase]["fn"](self, self.pt - 45)

    def update_bullets(self):
        if self.bomb_t > 0:
            self.bullets = []
            return
        px, py = self.px, self.py
        vulnerable = self.inv <= 0
        can_die = vulnerable and not self.god
        alive = []
        app = alive.append
        cos, sin = math.cos, math.sin
        hit = False
        grazed = 0
        for b in self.bullets:
            if b.fx:
                b.fx -= 1
                b.a += b.da
                b.s += b.ds
                b.vx = cos(b.a) * b.s
                b.vy = sin(b.a) * b.s
            b.x += b.vx
            b.y += b.vy
            x, y = b.x, b.y
            if x < -25 or x > FW + 25 or y < -25 or y > FH + 25:
                continue
            if vulnerable:
                dx = x - px
                dy = y - py
                d2 = dx * dx + dy * dy
                if d2 < b.gs:
                    if d2 < b.hs and can_die:
                        hit = True
                    elif not b.gz:
                        b.gz = True
                        grazed += 1
            app(b)
        self.bullets = alive
        if grazed:
            self.add_graze(grazed)
        if hit:
            self.player_hit()

    def update_pbul(self):
        keep = []
        bx, by = self.boss.x, self.boss.y
        live = self.trans <= 0
        can_dmg = live and self.pt >= 60
        for p in self.pbul:
            p[0] += p[2]
            p[1] += p[3]
            if p[1] < -20 or p[0] < -20 or p[0] > FW + 20:
                continue
            if live and abs(p[0] - bx) < 30 and abs(p[1] - by) < 26:
                if can_dmg:
                    self.boss_hp -= 1
                    self.score += 10
                continue
            keep.append(p)
        self.pbul = keep

    def player_hit(self):
        self.lives -= 1
        self.phase_clean = False
        self.combo = 0
        self.bullets.clear()
        if self.lives <= 0:
            self.hi = max(self.hi, self.score)
            self.state = "gameover"
            return
        self.bombs = 2
        self.inv = 150
        self.px, self.py = FW / 2, FH - 60

    #drawing
    def text(self, surf, s, font, color, pos, anchor="left"):
        img = font.render(s, True, color)
        r = img.get_rect()
        setattr(r, {"left": "topleft", "center": "center", "right": "topright"}[anchor], pos)
        surf.blit(img, r)

    def draw(self):
        f = self.field
        f.fill((6, 6, 22))
        for x, y, sp, sz in self.stars:
            c = 60 + sz * 50
            pygame.draw.rect(f, (c, c, c + 30), (int(x), int(y), sz, sz))

        if self.state == "title":
            self.text(f, "BULLET", self.f_big, (255, 230, 120), (FW // 2, 200), "center")
            self.text(f, "a tiny bullet hell", self.f_mid, (170, 190, 255), (FW // 2, 245), "center")
            lines = ["Arrows / WASD  move", "Shift  focus (slow, shows hitbox)",
                     "Z  shoot (hold)      X  bomb",
                     "Graze bullets for points!"]
            for i, ln in enumerate(lines):
                self.text(f, ln, self.f_small, (210, 210, 230), (FW // 2, 330 + i * 26), "center")
            if (self.t_all // 30) % 2 == 0:
                self.text(f, "Press Z or Enter to start", self.f_mid, (255, 255, 255),
                          (FW // 2, 500), "center")
        else:
            self.draw_game(f)

        self.screen.fill((14, 14, 28))
        self.screen.blit(f, (FX, FY))
        pygame.draw.rect(self.screen, (120, 120, 200), (FX - 2, FY - 2, FW + 4, FH + 4), 2)
        self.draw_hud()
        pygame.display.flip()

    def draw_game(self, f):
        t = self.t_all
        # --- boss
        b = self.boss
        bx, by = int(b.x), int(b.y)
        if self.phase >= 0 or self.trans > 0:
            spell = self.phase >= 1 and PHASES[self.phase]["name"] and self.trans <= 0
            r = 46 + 3 * math.sin(t * 0.05)
            col = (255, 120, 200) if spell else (140, 140, 255)
            pygame.draw.circle(f, col, (bx, by), int(r), 1)
            for sgn in (1, -1):
                pts = [(bx + r * math.cos(sgn * t * 0.02 + i * TAU / 3),
                        by + r * math.sin(sgn * t * 0.02 + i * TAU / 3)) for i in range(3)]
                pygame.draw.polygon(f, col, pts, 1)
            pygame.draw.circle(f, (170, 80, 220), (bx, by), 17)
            pygame.draw.circle(f, (255, 240, 255), (bx, by), 10)

        #player shots
        for p in self.pbul:
            f.blit(PBUL_SPR, (int(p[0]) - 3, int(p[1]) - 8))

        #bomb ring
        if self.bomb_t > 0:
            k = 1 - self.bomb_t / 45
            pygame.draw.circle(f, (255, 255, 160), (int(self.px), int(self.py)),
                               int(20 + k * 420), 6)
            pygame.draw.circle(f, (160, 220, 255), (int(self.px), int(self.py)),
                               int(10 + k * 300), 3)

        #bullets
        blit = f.blit
        for bl in self.bullets:
            o = bl.off
            blit(bl.spr, (int(bl.x) - o, int(bl.y) - o))

        #player
        px, py = int(self.px), int(self.py)
        if self.inv <= 0 or (self.inv // 4) % 2 == 0:
            pygame.draw.polygon(f, (120, 200, 255), [(px, py - 13), (px - 9, py + 9), (px, py + 4), (px + 9, py + 9)])
            pygame.draw.polygon(f, (230, 245, 255), [(px, py - 13), (px - 9, py + 9), (px, py + 4), (px + 9, py + 9)], 1)
        if self.focus:
            pygame.draw.circle(f, (120, 160, 255), (px, py), int(GRAZE_R), 1)
        pygame.draw.circle(f, (255, 255, 255), (px, py), 3)
        pygame.draw.circle(f, (255, 50, 50), (px, py), 2)

        #boss HP bar, timer, spell name
        if self.trans <= 0 and self.phase >= 0:
            ratio = (self.pt / 60) if self.pt < 60 else max(0.0, self.boss_hp / self.boss_max)
            ratio = min(1.0, ratio)
            pygame.draw.rect(f, (50, 20, 30), (40, 8, FW - 100, 6))
            pygame.draw.rect(f, (255, 90, 110), (40, 8, int((FW - 100) * ratio), 6))
            left = len(PHASES) - self.phase - 1
            self.text(f, "x%d" % left, self.f_small, (255, 200, 200), (12, 5))
            secs = max(0, math.ceil(self.timer / FPS))
            self.text(f, "%02d" % secs, self.f_mid, (255, 90, 90) if secs <= 10 else (255, 255, 255),
                      (FW - 12, 2), "right")
            name = PHASES[self.phase]["name"]
            if name:
                self.text(f, name, self.f_small, (255, 220, 120), (FW - 12, 28), "right")
                if self.pt < 90:
                    img = self.f_mid.render(name, True, (255, 230, 140))
                    img.set_alpha(int(255 * min(1, (90 - self.pt) / 40)))
                    f.blit(img, img.get_rect(center=(FW // 2, 200)))

        if self.msg:
            self.text(f, self.msg[0], self.f_mid, (255, 255, 160), (FW // 2, 260), "center")

        if self.state == "gameover":
            self.text(f, "GAME OVER", self.f_big, (255, 90, 90), (FW // 2, 270), "center")
            self.text(f, "Score %d" % self.score, self.f_mid, (255, 255, 255), (FW // 2, 320), "center")
            self.text(f, "Press Z to retry", self.f_small, (220, 220, 220), (FW // 2, 360), "center")
        elif self.state == "clear":
            self.text(f, "ALL CLEAR!", self.f_big, (255, 235, 120), (FW // 2, 270), "center")
            self.text(f, "Score %d   Graze %d" % (self.score, self.graze), self.f_mid,
                      (255, 255, 255), (FW // 2, 320), "center")
            self.text(f, "Press Z or Enter to play again", self.f_small, (220, 220, 220), (FW // 2, 360), "center")

    def draw_hud(self):
        s = self.screen
        x = FX + FW + 24
        L, V = (150, 160, 220), (255, 255, 255)
        self.text(s, "HI-SCORE", self.f_small, L, (x, 30))
        self.text(s, "%09d" % self.hi, self.f_mid, V, (x, 50))
        self.text(s, "SCORE", self.f_small, L, (x, 90))
        self.text(s, "%09d" % self.score, self.f_mid, V, (x, 110))
        self.text(s, "GRAZE", self.f_small, L, (x, 160))
        self.text(s, "%d" % self.graze, self.f_big, (120, 220, 255), (x, 180))
        if self.combo > 1:
            self.text(s, "chain x%d" % self.combo, self.f_small, (255, 220, 120), (x, 225))
        self.text(s, "LIFE", self.f_small, L, (x, 270))
        for i in range(max(0, self.lives)):
            pygame.draw.circle(s, (255, 90, 120), (x + 10 + i * 24, 304), 8)
        self.text(s, "BOMB", self.f_small, L, (x, 335))
        for i in range(self.bombs):
            pygame.draw.circle(s, (90, 235, 130), (x + 10 + i * 24, 369), 8)
        if self.phase >= 0:
            self.text(s, "PHASE %d / %d" % (self.phase + 1, len(PHASES)), self.f_small, L, (x, 410))
        tips = ["Shift: focus", "Z: shoot  X: bomb", "graze = points!"]
        for i, tp in enumerate(tips):
            self.text(s, tp, self.f_small, (120, 125, 170), (x, 560 + i * 22))
        self.text(s, "Bullets %d" % len(self.bullets), self.f_small, (120, 125, 170), (x, 640))



#loop, self-test

IS_WEB = sys.platform == "emscripten"   # running in the browser


async def main(max_frames=None):
    """Async main loop."""
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("BULLET")
    init_sprites()
    clock = pygame.time.Clock()
    g = Game(screen)
    frame = 0
    while max_frames is None or frame < max_frames:
        frame += 1
        bomb = False
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE and not IS_WEB:   # no "quit" in a web page
                    return
                if e.key == pygame.K_x:
                    bomb = True
                g.keydown(e.key)
        k = pygame.key.get_pressed()
        inp = Inp()
        inp.left = k[pygame.K_LEFT] or k[pygame.K_a]
        inp.right = k[pygame.K_RIGHT] or k[pygame.K_d]
        inp.up = k[pygame.K_UP] or k[pygame.K_w]
        inp.down = k[pygame.K_DOWN] or k[pygame.K_s]
        inp.shoot = k[pygame.K_z]
        inp.focus = k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT]
        inp.bomb = bomb
        g.update(inp)
        g.draw()
        clock.tick(FPS)
        await asyncio.sleep(0)      #yield to the browser


def selftest():
    import time
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    init_sprites()

    #invincible bot shoots the boss
    g = Game(screen)
    g.start()
    g.god = True
    frames = maxb = 0
    tu = td = 0.0
    seen = []
    while g.state == "play" and frames < FPS * 400:
        inp = Inp()
        inp.shoot = True
        inp.left = g.px > g.boss.x + 3
        inp.right = g.px < g.boss.x - 3
        inp.focus = frames % 200 < 100
        t0 = time.perf_counter()
        g.update(inp)
        t1 = time.perf_counter()
        g.draw()
        t2 = time.perf_counter()
        tu += t1 - t0
        td += t2 - t1
        frames += 1
        maxb = max(maxb, len(g.bullets))
        if g.phase not in seen:
            seen.append(g.phase)
    print("[god bot] state=%s frames=%d (%.0fs) phases=%s score=%d graze=%d"
          % (g.state, frames, frames / FPS, seen, g.score, g.graze))
    print("[god bot] max bullets=%d  avg update=%.2fms  avg draw=%.2fms"
          % (maxb, tu / frames * 1000, td / frames * 1000))

    #hits, bombs, game over must work
    random.seed(1)
    g = Game(screen)
    g.start()
    frames = 0
    inp = Inp()
    while g.state == "play" and frames < FPS * 120:
        if frames % 20 == 0:
            inp = Inp()
            inp.left, inp.right = random.random() < .4, random.random() < .4
            inp.up, inp.down = random.random() < .3, random.random() < .3
            inp.shoot = True
            inp.focus = random.random() < .5
        inp.bomb = (frames % 400 == 399)
        g.update(inp)
        g.draw()
        frames += 1
    print("[mortal bot] state=%s frames=%d lives=%d bombs=%d graze=%d score=%d"
          % (g.state, frames, g.lives, g.bombs, g.graze, g.score))
    #Z to leave the title screen, run 300 frames
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z))
    asyncio.run(main(max_frames=300))
    print("[async main] ran 300 frames OK")
    print("SELFTEST OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        asyncio.run(main())
