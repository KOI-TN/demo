"""STAR VEIL - minimal bullet hell. Arrows/WASD move, Shift focus, Z shoot, X bomb."""
import asyncio
import math
from typing import Callable, NamedTuple

import pygame

FPS = 60
FIELD_W, FIELD_H = 480, 660
WINDOW_W, WINDOW_H = 760, 700
MARGIN = 20
HUD_X = MARGIN + FIELD_W + 24
BLACK, WHITE, GRAY = (0, 0, 0), (255, 255, 255), (130, 130, 130)
TAU = math.tau

PLAYER_SPEED = 4.4
FOCUS_SPEED = 1.9
HIT_RADIUS = 2.0
GRAZE_RADIUS = 15.0
START_LIVES = 3
START_BOMBS = 2
MAX_BOMBS = 5
SHOT_INTERVAL = 3
RESPAWN_INVINCIBLE = 150
BOMB_FRAMES = 45
BOMB_INVINCIBLE = 90
BOMB_DAMAGE = 3

GRAZE_POINTS = 50
CHAIN_POINTS = 10
CHAIN_CAP = 20
CHAIN_FRAMES = 45
GRAZES_PER_BOMB = 200
SHOT_POINTS = 10
CAPTURE_BONUS = 20000
CAPTURE_PER_GRAZE = 200
OPENING_BONUS = 5000
LIFE_BONUS = 10000

INTRO_FRAMES = 90
TRANSITION_FRAMES = 100
ATTACK_DELAY = 45
VULNERABLE_AFTER = 60
BOSS_Y = 120
BOSS_SPEED = 1.2                             # px per frame, side to side
BOSS_MIN_X, BOSS_MAX_X = 120, FIELD_W - 120
BOSS_HALF_W, BOSS_HALF_H = 30, 26

BULLET_SIZES = {"s": (4, 2.6), "m": (6, 4.2), "l": (11, 8.0)}   # drawn radius, hit radius
MAX_BULLETS = 1500
OFFSCREEN = 25
SPRITES: dict = {}


def make_sprites():
    for size, (radius, _) in BULLET_SIZES.items():
        image = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(image, WHITE, (radius, radius), radius)
        SPRITES[size] = (image.convert_alpha(), radius)


class Bullet:
    __slots__ = ("x", "y", "vx", "vy", "size", "hit_sq", "graze_sq", "grazed")

    def __init__(self, x, y, angle, speed, size):
        self.x, self.y = x, y
        self.vx, self.vy = math.cos(angle) * speed, math.sin(angle) * speed
        self.size = size
        radius = BULLET_SIZES[size][1]
        self.hit_sq = (radius + HIT_RADIUS) ** 2
        self.graze_sq = (radius + GRAZE_RADIUS) ** 2
        self.grazed = False


class Shot:
    __slots__ = ("x", "y", "vx", "vy")

    def __init__(self, x, y, vx, vy):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy


# Boss attacks. t = frames since the attack began.
# ring: bullets in a circle (shifted = half a step, so rings alternate). fan: aimed at the player.
def normal(game, t):
    if t % 30 == 0:
        game.ring(16, 1.6, shifted=t // 30 % 2)
    if t % 70 == 35:
        game.fan(5, 0.16, 2.6, "m")


def card1(game, t):
    if t % 8 == 0:
        game.ring(16, 1.9, shifted=t // 8 % 2)
    if t % 120 == 90:
        game.fan(5, 0.22, 2.2, "l")


def card2(game, t):
    if t % 10 == 0:
        game.ring(20, 1.8, shifted=t // 10 % 2)
    if t % 45 == 20:
        game.fan(7, 0.15, 2.4, "m")


def card3(game, t):
    if t % 8 == 0:
        game.ring(12, 1.6, shifted=t // 8 % 2)
    if t % 100 == 60:
        for i, speed in enumerate((2.4, 2.9, 3.4)):
            game.ring(40, speed, "m", shifted=i == 1)
    if t % 24 == 12:
        game.fan(3, 0.12, 3.4)


class Phase(NamedTuple):
    hp: int
    seconds: int
    pattern: Callable


PHASES = [Phase(450, 40, normal), Phase(700, 45, card1),
          Phase(900, 50, card2), Phase(1100, 60, card3)]    # 0 = normal attack, 1-3 = spell cards


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.field = pygame.Surface((FIELD_W, FIELD_H))
        self.font = pygame.font.Font(None, 24)
        self.big_font = pygame.font.Font(None, 48)
        self.state = "title"                 # title / play / gameover / clear
        self.reset()

    def reset(self):
        self.score = 0
        self.graze = 0
        self.chain = 0
        self.chain_timer = 0
        self.lives = START_LIVES
        self.bombs = START_BOMBS
        self.px, self.py = FIELD_W / 2, FIELD_H - 70
        self.focused = False
        self.invincible = 0
        self.bomb_timer = 0
        self.shot_timer = 0
        self.bullets = []
        self.shots = []
        self.boss_x, self.boss_dir = FIELD_W / 2, 1
        self.boss_y = -60.0
        self.phase = -1
        self.transition = INTRO_FRAMES
        self.phase_time = 0
        self.timer = 0
        self.boss_hp = self.boss_max_hp = 1
        self.clean = True                    # no hit, no bomb this phase
        self.phase_grazes = 0
        self.message = None

    def start(self):
        self.reset()
        self.state = "play"

    def update(self, actions):
        if self.state != "play":
            return
        self.update_player(actions)
        self.update_boss()
        self.update_bullets()
        if self.state != "play":
            return
        self.update_shots()
        self.check_phase_end()
        if self.message:
            text, frames = self.message
            self.message = (text, frames - 1) if frames > 1 else None

    def update_player(self, actions):
        self.move_player(actions)
        self.invincible = max(0, self.invincible - 1)
        if "bomb" in actions:
            self.start_bomb()
        self.tick_bomb()
        self.shoot(actions)
        if self.chain_timer > 0:
            self.chain_timer -= 1
        else:
            self.chain = 0

    def move_player(self, actions):
        self.focused = "focus" in actions
        speed = FOCUS_SPEED if self.focused else PLAYER_SPEED
        dx = ("right" in actions) - ("left" in actions)
        dy = ("down" in actions) - ("up" in actions)
        if dx and dy:
            speed *= 0.7071
        self.px = min(max(self.px + dx * speed, 8), FIELD_W - 8)
        self.py = min(max(self.py + dy * speed, 12), FIELD_H - 12)

    def start_bomb(self):
        if self.bombs > 0 and self.bomb_timer <= 0:
            self.bombs -= 1
            self.bomb_timer = BOMB_FRAMES
            self.invincible = max(self.invincible, BOMB_INVINCIBLE)
            self.clean = False

    def tick_bomb(self):
        if self.bomb_timer > 0:
            self.bomb_timer -= 1
            if self.boss_vulnerable():
                self.boss_hp -= BOMB_DAMAGE

    def shoot(self, actions):
        if self.shot_timer > 0:
            self.shot_timer -= 1
        if "shoot" not in actions or self.shot_timer > 0:
            return
        self.shot_timer = SHOT_INTERVAL
        x, y = self.px, self.py - 10
        if self.focused:
            for dx in (-9, -3, 3, 9):
                self.shots.append(Shot(x + dx, y, 0, -17))
        else:
            for dx in (-10, 0, 10):
                self.shots.append(Shot(x + dx, y, 0, -15))
            for vx in (-2.6, 2.6):
                self.shots.append(Shot(x, y, vx, -15))

    def player_hit(self):
        self.lives -= 1
        self.clean = False
        self.chain = 0
        self.bullets.clear()
        if self.lives <= 0:
            self.state = "gameover"
            return
        self.bombs = START_BOMBS
        self.invincible = RESPAWN_INVINCIBLE
        self.px, self.py = FIELD_W / 2, FIELD_H - 60

    def update_boss(self):
        self.boss_y += (BOSS_Y - self.boss_y) * 0.04
        self.boss_x += BOSS_SPEED * self.boss_dir
        if not BOSS_MIN_X < self.boss_x < BOSS_MAX_X:
            self.boss_dir = -self.boss_dir
        if self.transition > 0:
            self.transition -= 1
            if self.transition == 0:
                self.start_phase(self.phase + 1)
            return
        self.phase_time += 1
        self.timer -= 1
        if self.phase_time >= ATTACK_DELAY:
            PHASES[self.phase].pattern(self, self.phase_time - ATTACK_DELAY)

    def boss_vulnerable(self):
        return self.transition <= 0 and self.phase_time >= VULNERABLE_AFTER

    def start_phase(self, index):
        if index >= len(PHASES):
            self.score += self.lives * LIFE_BONUS
            self.state = "clear"
            return
        self.phase = index
        self.phase_time = 0
        self.boss_hp = self.boss_max_hp = PHASES[index].hp
        self.timer = PHASES[index].seconds * FPS
        self.clean = True
        self.phase_grazes = 0
        self.bullets.clear()

    def check_phase_end(self):
        if self.transition > 0 or self.phase < 0:
            return
        if self.boss_hp <= 0:
            self.end_phase(captured=True)
        elif self.timer <= 0:
            self.end_phase(captured=False)

    def end_phase(self, captured):
        if self.phase == 0:
            self.score += OPENING_BONUS
        elif captured and self.clean:
            bonus = CAPTURE_BONUS + self.phase_grazes * CAPTURE_PER_GRAZE
            self.score += bonus
            self.message = (f"CAPTURED +{bonus}", 120)
        elif captured:
            self.message = ("BROKEN", 100)
        else:
            self.message = ("TIME OUT", 100)
        self.bullets.clear()
        self.transition = TRANSITION_FRAMES

    def fire(self, angle, speed, size="s"):
        if len(self.bullets) < MAX_BULLETS:
            self.bullets.append(Bullet(self.boss_x, self.boss_y, angle, speed, size))

    def ring(self, count, speed, size="s", shifted=False):
        offset = TAU / count / 2 if shifted else 0
        for i in range(count):
            self.fire(offset + i * TAU / count, speed, size)

    def fan(self, count, gap, speed, size="s"):
        center = math.atan2(self.py - self.boss_y, self.px - self.boss_x)
        for i in range(count):
            self.fire(center + (i - (count - 1) / 2) * gap, speed, size)

    def update_bullets(self):
        if self.bomb_timer > 0:
            self.bullets = []
            return
        can_be_hit = self.invincible <= 0
        alive = []
        grazes = 0
        hit = False
        for b in self.bullets:
            b.x += b.vx
            b.y += b.vy
            if (b.x < -OFFSCREEN or b.x > FIELD_W + OFFSCREEN or
                    b.y < -OFFSCREEN or b.y > FIELD_H + OFFSCREEN):
                continue
            if can_be_hit:
                dx, dy = b.x - self.px, b.y - self.py
                dist_sq = dx * dx + dy * dy
                if dist_sq < b.hit_sq:
                    hit = True
                elif dist_sq < b.graze_sq and not b.grazed:
                    b.grazed = True
                    grazes += 1
            alive.append(b)
        self.bullets = alive
        if grazes:
            self.add_graze(grazes)
        if hit:
            self.player_hit()

    def add_graze(self, count):
        for _ in range(count):
            self.chain += 1
            self.score += GRAZE_POINTS + CHAIN_POINTS * min(self.chain, CHAIN_CAP)
            self.graze += 1
            if self.graze % GRAZES_PER_BOMB == 0:
                self.bombs = min(MAX_BOMBS, self.bombs + 1)
        self.phase_grazes += count
        self.chain_timer = CHAIN_FRAMES

    def update_shots(self):
        boss_active = self.transition <= 0
        kept = []
        for s in self.shots:
            s.x += s.vx
            s.y += s.vy
            if s.y < -20 or s.x < -20 or s.x > FIELD_W + 20:
                continue
            if (boss_active and abs(s.x - self.boss_x) < BOSS_HALF_W
                    and abs(s.y - self.boss_y) < BOSS_HALF_H):
                if self.boss_vulnerable():
                    self.boss_hp -= 1
                    self.score += SHOT_POINTS
                continue
            kept.append(s)
        self.shots = kept

    def draw(self):
        self.field.fill(BLACK)
        if self.state == "title":
            self.draw_title()
        else:
            self.draw_play()
        self.screen.fill(BLACK)
        self.screen.blit(self.field, (MARGIN, MARGIN))
        if self.state != "title":
            self.draw_hud()
        pygame.display.flip()

    def text(self, surface, string, pos, color=WHITE, align="left", big=False):
        image = (self.big_font if big else self.font).render(string, True, color)
        rect = image.get_rect()
        setattr(rect, {"left": "topleft", "center": "center", "right": "topright"}[align], pos)
        surface.blit(image, rect)

    def draw_title(self):
        center = FIELD_W // 2
        self.text(self.field, "STAR VEIL", (center, 200), big=True, align="center")
        lines = ["Arrows / WASD  move", "Shift  focus (slow, shows hitbox)",
                 "Z  shoot     X  bomb", "Graze bullets for points"]
        for i, line in enumerate(lines):
            self.text(self.field, line, (center, 300 + i * 26), GRAY, align="center")
        self.text(self.field, "Press Z or Enter", (center, 480), align="center")

    def draw_play(self):
        f = self.field
        boss_pos = (int(self.boss_x), int(self.boss_y))
        pygame.draw.circle(f, WHITE, boss_pos, 28, 2)
        pygame.draw.circle(f, WHITE, boss_pos, 6)
        for s in self.shots:
            pygame.draw.line(f, GRAY, (s.x, s.y - 8), (s.x, s.y + 8), 2)
        if self.bomb_timer > 0:
            progress = 1 - self.bomb_timer / BOMB_FRAMES
            pygame.draw.circle(f, WHITE, (int(self.px), int(self.py)),
                               int(20 + progress * 420), 2)
        for b in self.bullets:
            sprite, radius = SPRITES[b.size]
            f.blit(sprite, (int(b.x) - radius, int(b.y) - radius))
        self.draw_player()
        self.draw_boss_bar()
        if self.message and self.state == "play":
            self.text(f, self.message[0], (FIELD_W // 2, 260), align="center")
        if self.state in ("gameover", "clear"):
            title = "GAME OVER" if self.state == "gameover" else "ALL CLEAR"
            self.text(f, title, (FIELD_W // 2, 270), big=True, align="center")
            self.text(f, f"Score {self.score}   Graze {self.graze}",
                      (FIELD_W // 2, 320), align="center")
            self.text(f, "Press Z or Enter to play again",
                      (FIELD_W // 2, 360), GRAY, align="center")

    def draw_player(self):
        f = self.field
        x, y = int(self.px), int(self.py)
        if self.invincible <= 0 or (self.invincible // 4) % 2 == 0:
            ship = [(x, y - 13), (x - 9, y + 9), (x, y + 4), (x + 9, y + 9)]
            pygame.draw.polygon(f, BLACK, ship)
            pygame.draw.polygon(f, WHITE, ship, 1)
        if self.focused:
            pygame.draw.circle(f, GRAY, (x, y), int(GRAZE_RADIUS), 1)
        pygame.draw.circle(f, BLACK, (x, y), 4)
        pygame.draw.circle(f, WHITE, (x, y), 2)

    def draw_boss_bar(self):
        if self.transition > 0 or self.phase < 0:
            return
        f = self.field
        if self.boss_vulnerable():
            fill = max(0.0, self.boss_hp / self.boss_max_hp)
        else:
            fill = self.phase_time / VULNERABLE_AFTER
        pygame.draw.rect(f, WHITE, (10, 8, int((FIELD_W - 70) * fill), 4))
        seconds = max(0, math.ceil(self.timer / FPS))
        self.text(f, f"{seconds:02d}", (FIELD_W - 10, 2), align="right")
        if self.phase > 0:
            self.text(f, str(self.phase), (10, 18), GRAY)

    def draw_hud(self):
        rows = [("SCORE", self.score), ("GRAZE", self.graze),
                ("LIFE", self.lives), ("BOMB", self.bombs)]
        if self.chain > 1:
            rows.append(("CHAIN", f"x{self.chain}"))
        for i, (label, value) in enumerate(rows):
            y = 30 + i * 30
            self.text(self.screen, label, (HUD_X, y), GRAY)
            self.text(self.screen, str(value), (HUD_X + 80, y))


KEY_ACTIONS = {
    "left": (pygame.K_LEFT, pygame.K_a),
    "right": (pygame.K_RIGHT, pygame.K_d),
    "up": (pygame.K_UP, pygame.K_w),
    "down": (pygame.K_DOWN, pygame.K_s),
    "shoot": (pygame.K_z,),
    "focus": (pygame.K_LSHIFT, pygame.K_RSHIFT),
}


def held_actions():
    keys = pygame.key.get_pressed()
    return {name for name, group in KEY_ACTIONS.items() if any(keys[k] for k in group)}


async def main():   
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("STAR VEIL")
    make_sprites()
    clock = pygame.time.Clock()
    game = Game(screen)

    while True:
        bomb_pressed = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_x:
                    bomb_pressed = True
                if event.key in (pygame.K_z, pygame.K_RETURN) and game.state != "play":
                    game.start()

        actions = held_actions()
        if bomb_pressed:
            actions.add("bomb")
        game.update(actions)
        game.draw()
        clock.tick(FPS)
        await asyncio.sleep(0)               # lets the browser run (pygbag)


if __name__ == "__main__":
    asyncio.run(main())
