import pygame
import threading
import time as _time
import array
import math
from player import Player
from monster import Monster
from animals import Animal
from objects import Box
from title_screen import TitleScreen
from config import (SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, 
                    MAP_LEFT, MAP_TOP, ZONE_COUNT_X, ZONE_COUNT_Y, FPS,
                    ANIMAL_COUNT, RADIATION_RATE, FOOD_HUNGER_RESTORE, KEYBINDS)
from sounds import SFX, MUSIC, init_audio, SND_COLLECT, SND_HIDE, SND_UNHIDE, SND_BEEP, SND_DEATH, MUS_MENU, MUS_AMBIENT, MUS_TENSE
from map_data import (get_zone_type, get_items_in_zone,
                      get_zone_grid, get_zone_radiation,
                      TILE_EMPTY, TILE_WALL, TILE_OBJECT, UNIT_W, UNIT_H,
                      ZONE_TILE_WIDTH, ZONE_TILE_HEIGHT)
from sprites import ZONE_RENDERER, init_sprites
from bullets import BulletsManager
from bullets import Bullet
from food import Food
from inventory_screen import InventoryScreen
from pause_screen import PauseScreen
 
 

# ---------------------------------------------------------------------------
# Game Over screen
# --------------------------------------------------------------------------- 
class GameOverScreen:
   def __init__(self): 
       self.font = pygame.font.SysFont('Arial', 48)
       self.sub_font = pygame.font.SysFont('Arial', 28)
       self.title_surface = self.font.render("Game Over", True, (200, 0, 0))
       self.prompt_surface = self.sub_font.render("Press space to quit", True, (255, 255, 255))

   def run(self, screen, clock):
       while True:
           clock.tick(60)
           for event in pygame.event.get():
               if event.type == pygame.QUIT:
                   return
               if event.type == pygame.KEYDOWN:
                   if event.key == pygame.K_SPACE:
                       return
           screen.fill((0, 0, 0))
           screen.blit(self.title_surface, (340, 220))
           screen.blit(self.prompt_surface, (350, 300))
           pygame.display.flip()



# ---------------------------------------------------------------------------
# Main Game class
# ---------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 1, 512)
        pygame.init()
        init_audio()
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE | pygame.SCALED)
        pygame.display.set_caption("Project Orin")
        init_sprites()   # load all spritesheets after display is created

        self.clock = pygame.time.Clock()

        self.player = Player(MAP_WIDTH, MAP_HEIGHT, ZONE_COUNT_X, ZONE_COUNT_Y)
        self.monster = Monster(MAP_WIDTH, MAP_HEIGHT, ZONE_COUNT_X, ZONE_COUNT_Y)
        self.animals = [Animal(self.player.loadingzonex, self.player.loadingzoney,
                                MAP_WIDTH, MAP_HEIGHT, ZONE_COUNT_X, ZONE_COUNT_Y)
                        for _ in range(ANIMAL_COUNT)]
        self.game_surface = pygame.Surface((MAP_WIDTH, MAP_HEIGHT))
        self.food = []
        self.boxes = []
        for zone_y in range(ZONE_COUNT_Y):
            for zone_x in range(ZONE_COUNT_X):
                for item in get_items_in_zone(zone_x, zone_y):
                    x = item.get('x', 0)
                    y = item.get('y', 0)
                    if x > ZONE_TILE_WIDTH or y > ZONE_TILE_HEIGHT:
                        px = x
                        py = y
                    else:
                        px = x * UNIT_W
                        py = y * UNIT_H
                    self.boxes.append(Box(px, py, zone_x, zone_y, item=item))

        if not self.boxes:
            self.boxes = [
                Box(120, 120, 0, 0),
                Box(520,  90, 1, 0),
                Box(240, 420, 0, 1),
                Box(560, 360, 1, 1),
            ]

        self.font = pygame.font.SysFont('Arial', 20)

        self.title_screen     = TitleScreen()
        self.pause_screen     = PauseScreen()
        self.inventory_screen = InventoryScreen()
        self.game_over_screen = GameOverScreen()
        self.bullets = BulletsManager()
        self.last_mouse_pressed = False
        self.last_shoot_pressed = False

        self.running = False

        self._lock      = threading.Lock()
        self._ai_thread = None
        self._ai_running = False
        self._paused    = False   # True while pause/inventory screen is open

        self._beep_sound  = self._create_beep()
        self._drone_sound = self._create_drone()
        self._beep_timer    = 0.0
        self._beep_interval = None
        self._droning       = False

        self._last_zone  = (-1, -1)
        self._wall_rects = []

    # ---- audio synthesis ----

    @staticmethod
    def _create_beep(frequency=880, duration=0.045, sample_rate=44100, volume=0.35):
        n = int(sample_rate * duration)
        buf = array.array('h')
        fade_frames = max(1, int(n * 0.12))
        for i in range(n):
            t = i / sample_rate
            fade = min(i, n - i, fade_frames) / fade_frames
            val = int(32767 * volume * fade * math.sin(2 * math.pi * frequency * t))
            buf.append(val)
        return pygame.mixer.Sound(buffer=buf)

    @staticmethod
    def _create_drone(frequency=880, sample_rate=44100, volume=0.35):
        n_cycles = max(1, round(frequency * 1.0))
        n = int(sample_rate * n_cycles / frequency)
        buf = array.array('h')
        for i in range(n):
            t = i / sample_rate
            val = volume * math.sin(2 * math.pi * frequency * t)
            buf.append(int(32767 * val))
        return pygame.mixer.Sound(buffer=buf)

    # ---- firing ----

    def _try_fire(self):
        if pygame.mouse.get_pressed()[0] and not self.player.hiding:
            if self.player.ammo <= 0:
                return
            mx, my = pygame.mouse.get_pos()
            mx -= MAP_LEFT
            my -= MAP_TOP
            px, py = self.player.rect.center
            dx = mx - px
            dy = my - py
            self.bullets.fire(px, py, dx, dy, self.player.loadingzonex, self.player.loadingzoney)
            self.player.ammo -= 1

    # ---- AI thread ----

    def _ai_loop(self):
        interval = 1.0 / FPS
        last = _time.perf_counter()
        while self._ai_running:
            now = _time.perf_counter()
            dt  = min(now - last, 0.05)
            last = now
            if self._paused:
                _time.sleep(interval)
                continue
            with self._lock:
                if self.player.alive and self.running:
                    if self.player.hiding:
                        self.monster.update(None, None,
                                            self.player.loadingzonex, self.player.loadingzoney,
                                            dt, hiding=True)
                    else:
                        self.monster.update(self.player.x, self.player.y,
                                            self.player.loadingzonex, self.player.loadingzoney,
                                            dt, hiding=False)
                    for animal in self.animals:
                        animal.update(dt)
            sleep_for = interval - (_time.perf_counter() - now)
            if sleep_for > 0:
                _time.sleep(sleep_for)

    # ---- zone helpers ----

    def _in_player_zone(self, entity):
        return (entity.loading_zone_x == self.player.loadingzonex and
                entity.loading_zone_y == self.player.loadingzoney)

    def _build_wall_rects(self, zone_x, zone_y):
        rects = []
        grid = get_zone_grid(zone_x, zone_y)
        if not grid:
            return rects
        tile_w = MAP_WIDTH  // max(1, len(grid[0]))
        tile_h = MAP_HEIGHT // max(1, len(grid))
        for ty, row in enumerate(grid):
            for tx, tile in enumerate(row):
                if tile == TILE_WALL:
                    rects.append(pygame.Rect(tx * tile_w, ty * tile_h, tile_w, tile_h))
        return rects

    def _resolve_wall_collisions(self):
        pr = self.player.rect
        for wall in self._wall_rects:
            if not pr.colliderect(wall):
                continue
            left_overlap  = pr.right  - wall.left
            right_overlap = wall.right - pr.left
            top_overlap   = pr.bottom - wall.top
            bot_overlap   = wall.bottom - pr.top
            min_x = left_overlap  if left_overlap  < right_overlap else -right_overlap
            min_y = top_overlap   if top_overlap   < bot_overlap   else -bot_overlap
            if abs(min_x) < abs(min_y):
                self.player.x -= min_x
            else:
                self.player.y -= min_y
            self.player.rect.x = int(self.player.x)
            self.player.rect.y = int(self.player.y)

    def _render_tiles(self, surface):
        grid = get_zone_grid(self.player.loadingzonex, self.player.loadingzoney)
        if not grid:
            return
        tile_w = MAP_WIDTH  // max(1, len(grid[0]))
        tile_h = MAP_HEIGHT // max(1, len(grid))
        inner_pad_x = max(1, tile_w // 6)
        inner_pad_y = max(1, tile_h // 6)
        for ty, row in enumerate(grid):
            for tx, tile in enumerate(row):
                if tile == TILE_EMPTY:
                    continue
                rx = tx * tile_w
                ry = ty * tile_h
                if tile == TILE_WALL:
                    pygame.draw.rect(surface, (55, 55, 65),  (rx, ry, tile_w, tile_h))
                    pygame.draw.rect(surface, (80, 80, 95),  (rx, ry, tile_w, tile_h), 2)
                elif tile == TILE_OBJECT:
                    pygame.draw.rect(surface, (100, 70, 30),
                                        (rx + inner_pad_x, ry + inner_pad_y,
                                        tile_w - inner_pad_x * 2, tile_h - inner_pad_y * 2))
                    pygame.draw.rect(surface, (150, 110, 50),
                                        (rx + inner_pad_x, ry + inner_pad_y,
                                        tile_w - inner_pad_x * 2, tile_h - inner_pad_y * 2), 2)

    # ---- interaction helpers ----

    def is_in_range_of_box(self):
        for box in self.boxes:
            if self._in_player_zone(box) and not box.collected:
                if abs(self.player.x - box.x) < 60 and abs(self.player.y - box.y) < 60:
                    return True
        return False

    def food_items_in_player_zone(self):
        return [f for f in self.food if self._in_player_zone(f)]

    def is_in_range_of_food(self):
        for food_item in self.food_items_in_player_zone():
            if abs(self.player.x - food_item.x) < 60 and abs(self.player.y - food_item.y) < 60:
                return True
        return False

    def try_pickup_food(self):
        """Pick up the nearest food item and store it in inventory."""
        nearest, nearest_dist = None, None
        for food_item in self.food_items_in_player_zone():
            dx = self.player.x - food_item.x
            dy = self.player.y - food_item.y
            if abs(dx) < 60 and abs(dy) < 60:
                d = math.hypot(dx, dy)
                if nearest is None or d < nearest_dist:
                    nearest, nearest_dist = food_item, d
        if nearest is not None:
            self.player.inventory.append(nearest.item_id)
            self.food.remove(nearest)
            SFX.play(SND_COLLECT)
            return True
        return False

    def try_collect_object(self):
        for box in self.boxes:
            if self._in_player_zone(box) and not box.collected:
                if abs(self.player.x - box.x) < 60 and abs(self.player.y - box.y) < 60:
                    box.collect(self.player)
                    SFX.play(SND_COLLECT)
                    return True
        return False

    def try_use_action(self):
        food_avail = self.is_in_range_of_food()
        box_avail  = self.is_in_range_of_box()
        if food_avail and box_avail:
            nearest_food, nearest_box = None, None
            nfd, nbd = None, None
            for fi in self.food_items_in_player_zone():
                d = math.hypot(self.player.x - fi.x, self.player.y - fi.y)
                if nearest_food is None or d < nfd:
                    nearest_food, nfd = fi, d
            for box in self.boxes:
                if not self._in_player_zone(box) or box.collected:
                    continue
                d = math.hypot(self.player.x - box.x, self.player.y - box.y)
                if d < 60 and (nearest_box is None or d < nbd):
                    nearest_box, nbd = box, d
            if nearest_food is not None and (nearest_box is None or nfd <= nbd):
                self.player.inventory.append(nearest_food.item_id)
                self.food.remove(nearest_food)
                SFX.play(SND_COLLECT)
                return True
            if nearest_box is not None:
                nearest_box.collect(self.player)
                SFX.play(SND_COLLECT)
                return True
            return False
        if food_avail:
            return self.try_pickup_food()
        if box_avail:
            return self.try_collect_object()
        return False

    # ---- event handling ----

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._try_fire()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                if event.key == KEYBINDS['pause']:
                    self._paused = True
                    resume = self.pause_screen.run(self.screen, self.clock)
                    self._paused = False
                    self.clock.tick()  # discard accumulated time
                    if not resume:
                        self.running = False
                if event.key == KEYBINDS['hide']:
                    was_hiding = self.player.hiding
                    self.player.toggle_hiding(self.boxes)
                    if self.player.hiding != was_hiding:
                        SFX.play(SND_HIDE if self.player.hiding else SND_UNHIDE)
                if event.key == KEYBINDS['action']:
                    self.try_use_action()
                if event.key == KEYBINDS['inventory']:
                    self._paused = True
                    self.inventory_screen.run(self.screen, self.clock, self.player, self.boxes)
                    self._paused = False
                    self.clock.tick()  # discard accumulated time

    # ---- update ----

    def update(self, dt):
        MUSIC.update()
        _zone_dist  = None
        _pixel_dist = None

        with self._lock:
            self.player.update(dt)

            if self.player.hunger <= 0 or self.player.radiation >= self.player.RADIATION_MAX:
                self.player.alive = False

            if not self.player.alive:
                SFX.play(SND_DEATH)
                MUSIC.stop()
                return

            if not self.player.hiding:
                self.player.handle_movement(dt)
                self.player.loading_zones()
                zone_key = (self.player.loadingzonex, self.player.loadingzoney)
                if zone_key != self._last_zone:
                    self._last_zone  = zone_key
                    self._wall_rects = self._build_wall_rects(*zone_key)
                self._resolve_wall_collisions()

            # ---- Radiation logic ----
            # 1. Ambient zone radiation from radiation_map
            zone_rad_level = get_zone_radiation(
                self.player.loadingzonex, self.player.loadingzoney)
            # Levels 0-6; level 0 = clean, 1 = very low, …6 = extreme
            # Base ambient rate per second: level * 0.5  (so level 3 = 1.5 rad/s)
            ambient_rate = zone_rad_level * 0.5

            # 2. Monster proximity radiation
            monster_rate = 0.0
            if self.monster.active and self._in_player_zone(self.monster):
                if self.player.hiding:
                    monster_rate = RADIATION_RATE * 0.2
                else:
                    monster_rate = RADIATION_RATE

            total_rate = ambient_rate + monster_rate
            # Apply radiation resistance from equipped items
            resist = self.player.rad_resist
            effective_rate = total_rate * (1.0 - resist)

            if effective_rate > 0:
                self.player.radiation = min(
                    self.player.RADIATION_MAX,
                    self.player.radiation + dt * effective_rate
                )
            else:
                # Natural decay when nothing is irradiating
                self.player.radiation = max(0, self.player.radiation - dt * 1.0)

            # ---- Monster catch ----
            if (self.monster.active and self._in_player_zone(self.monster)
                    and self.player.rect.colliderect(self.monster.rect)
                    and not self.player.hiding):
                self.player.color = (255, 100, 100)
                self.player.alive = False
            else:
                self.player.color = (0, 255, 0)

            if self.monster.active:
                _zone_dist = self.monster._zone_distance(
                    self.player.loadingzonex, self.player.loadingzoney)
                _world_dx = ((self.monster.loading_zone_x - self.player.loadingzonex)
                                * MAP_WIDTH  + self.monster.x - self.player.x)
                _world_dy = ((self.monster.loading_zone_y - self.player.loadingzoney)
                                * MAP_HEIGHT + self.monster.y - self.player.y)
                _pixel_dist = math.sqrt(_world_dx ** 2 + _world_dy ** 2)

        self.bullets.update(dt)

        # Bullet-wall collisions
        for bullet in list(self.bullets.bullets):
            if self._in_player_zone(bullet):
                for wall in self._wall_rects:
                    if bullet.rect.colliderect(wall):
                        if bullet.collidewall:
                            self.bullets.bullets.remove(bullet)
                        break

        # Bullet-animal collisions
        for bullet in list(self.bullets.bullets):
            for animal in list(self.animals):
                if self._in_player_zone(animal) and bullet.rect.colliderect(animal.rect):
                    self.bullets.bullets.remove(bullet)
                    self.food.append(Food(animal.x, animal.y, 8,
                                            animal.loading_zone_x, animal.loading_zone_y))
                    self.animals.remove(animal)
                    break

        # Bullet-monster collisions
        if self._in_player_zone(self.monster):
            for bullet in list(self.bullets.bullets):
                if bullet.rect.colliderect(self.monster.rect) and bullet.collidemonster:
                    bullet.vx = -2 * bullet.vx
                    bullet.vy = -2 * bullet.vy
                    bullet.collidemonster = False
            for bullet in list(self.bullets.bullets):
                if self._in_player_zone(bullet):
                    if bullet.life < 1.85 and bullet.rect.colliderect(self.player.rect):
                        self.player.alive = False
                        break
        for bullet in list(self.bullets.bullets):
            bullet.check_wall_collision(dt)

        # ---- Proximity beep / drone ----
        _MAX_BEEP_PX = MAP_WIDTH * 9
        if not self.player.alive:
            self._beep_sound.stop()
        elif _zone_dist is not None and _zone_dist == 0:
            if not self._droning:
                self._beep_sound.stop()
                self._drone_sound.play(-1)
                self._droning = True
            self._beep_interval = None
            self._beep_timer    = 0.0
        elif _pixel_dist is not None and _pixel_dist < _MAX_BEEP_PX:
            if self._droning:
                self._drone_sound.stop()
                self._droning = False
            t = _pixel_dist / _MAX_BEEP_PX
            target_interval = 0.12 + t * (2.5 - 0.12)
            if self._beep_interval is None:
                self._beep_interval = target_interval
            else:
                self._beep_interval += (target_interval - self._beep_interval) * min(1.0, dt * 4.0)
        else:
            if self._droning:
                self._drone_sound.stop()
                self._droning = False
            self._beep_interval = None

        if not self.player.alive:
            if self._droning:
                self._drone_sound.stop()
                self._droning = False
            self._beep_interval = None

        if self._beep_interval is not None:
            self._beep_timer -= dt
            if self._beep_timer <= 0:
                if SND_BEEP not in SFX.loaded():
                    self._beep_sound.play()
                else:
                    SFX.play(SND_BEEP)
                self._beep_timer = self._beep_interval
        elif not self._droning:
            self._beep_timer = 0.0

        if _zone_dist is not None and _zone_dist <= 4:
            # MUS_TENSE is a one-shot track (loop=False): once it finishes,
            # MUSIC.current stays set to MUS_TENSE forever (MusicManager
            # doesn't clear it on natural stop), so `!= MUS_TENSE` never
            # becomes true again and it never replays. Meanwhile this
            # branch (monster still close) keeps blocking the ambient-
            # rotation fallback below. Net effect: total silence for as
            # long as the monster stays within 4 zones — restart the
            # stinger whenever it's actually finished playing instead.
            if MUSIC.current != MUS_TENSE or not MUSIC.is_playing():
                MUSIC.play(MUS_TENSE, loop=False)
        else:
            if not MUSIC.in_rotation:
                MUSIC.start_rotation(MUS_AMBIENT)

    # ---- render ----

    def render(self):
        dt = getattr(self, '_last_dt', 0.016)
        self.screen.fill((12, 16, 30))
        pygame.draw.rect(self.screen, (18, 22, 36), (0, 0, SCREEN_WIDTH, MAP_TOP))
        self.game_surface.fill((12, 16, 30))

        # Ambient radiation tint: zones with high radiation get a faint green wash
        zone_rad = get_zone_radiation(self.player.loadingzonex, self.player.loadingzoney)
        if zone_rad >= 2:
            tint_alpha = min(int(zone_rad * 12), 80)
            tint = pygame.Surface((MAP_WIDTH, MAP_HEIGHT), pygame.SRCALPHA)
            tint.fill((0, 255, 80, tint_alpha))
            self.game_surface.blit(tint, (0, 0))

        ZONE_RENDERER.render(
            self.game_surface,
            self.player.loadingzonex,
            self.player.loadingzoney,
            get_zone_type(self.player.loadingzonex, self.player.loadingzoney)
        )
        self.player.draw(self.game_surface, dt)

        for box in self.boxes:
            if self._in_player_zone(box):
                box.draw(self.game_surface)

        for food_item in self.food:
            if self._in_player_zone(food_item):
                food_item.draw(self.game_surface)

        self.bullets.draw(self.game_surface)

        if self.monster.active and self._in_player_zone(self.monster):
            self.monster.draw(self.game_surface, dt)

        for animal in self.animals:
            if self._in_player_zone(animal):
                animal.draw(self.game_surface, dt)

        self.screen.blit(self.game_surface, (MAP_LEFT, MAP_TOP))
        pygame.draw.rect(self.screen, (100, 100, 120),
                        (MAP_LEFT - 2, MAP_TOP - 2, MAP_WIDTH + 1, MAP_HEIGHT + 4), 2)

        # ---- HUD hints ----
        k_hide   = pygame.key.name(KEYBINDS['hide']).upper()
        k_action = pygame.key.name(KEYBINDS['action']).upper()
        k_inv    = pygame.key.name(KEYBINDS['inventory']).upper()

        if self.player.hiding:
            hint_text = f"{k_hide}: exit  |  {k_inv}: inventory"
        elif any(box.can_hide(self.player) for box in self.boxes):
            if self.is_in_range_of_box():
                hint_text = f"{k_hide}: hide  |  {k_action}: take item  |  {k_inv}: inventory"
            else:
                hint_text = f"{k_hide}: hide  |  {k_inv}: inventory"
        else:
            food_nearby = self.is_in_range_of_food()
            box_nearby  = self.is_in_range_of_box()
            if box_nearby and food_nearby:
                hint_text = f"{k_action}: take item / pick up food  |  {k_inv}: inventory"
            elif box_nearby:
                hint_text = f"{k_action}: take item  |  {k_inv}: inventory"
            elif food_nearby:
                hint_text = f"{k_action}: pick up food  |  {k_inv}: inventory"
            else:
                hint_text = f"{k_inv}: inventory"

        zone_text = f"Zone: {self.player.loadingzonex + 1}/{ZONE_COUNT_X}, {self.player.loadingzoney + 1}/{ZONE_COUNT_Y}"
        self.screen.blit(self.font.render(hint_text, True, (255, 255, 255)), (SCREEN_WIDTH - 350, 20))
        self.screen.blit(self.font.render(zone_text, True, (255, 255, 255)), (SCREEN_WIDTH - 350, 50))

        # Ambient radiation zone indicator
        zone_rad = get_zone_radiation(self.player.loadingzonex, self.player.loadingzoney)
        if zone_rad >= 1:
            rad_colors = [(0,200,80),(60,220,60),(120,220,40),(200,220,0),(220,160,0),(220,80,0),(200,0,0)]
            rc = rad_colors[min(int(zone_rad), 6)]
            rad_zone_surf = self.font.render(f"Zone Rad: {int(zone_rad)}", True, rc)
            self.screen.blit(rad_zone_surf, (SCREEN_WIDTH - 350, 75))

        # ---- Top HUD bars ----
        hud_x = MAP_LEFT + 20
        hud_y = 20
        pygame.draw.rect(self.screen, (255, 255, 255), (hud_x, hud_y, 220, 22), 2)
        pygame.draw.rect(self.screen, (0, 255, 75), (hud_x + 2, hud_y + 2,
                            int(min(self.player.radiation / self.player.RADIATION_MAX, 1) * 216), 18))
        pygame.draw.rect(self.screen, (255, 255, 255), (hud_x, hud_y + 30, 220, 22), 2)
        pygame.draw.rect(self.screen, (255, 140, 0), (hud_x + 2, hud_y + 32,
                            int(self.player.hunger / 100 * 216), 18))
        self.screen.blit(self.font.render("Radiation", True, (255, 255, 255)), (hud_x + 230, hud_y + 2))
        self.screen.blit(self.font.render("Hunger",    True, (255, 255, 255)), (hud_x + 230, hud_y + 32))

        # Ammo counter
        ammo_color = (255, 220, 50) if self.player.ammo > 0 else (200, 60, 60)
        ammo_surf = self.font.render(f"Ammo: {self.player.ammo}", True, ammo_color)
        self.screen.blit(ammo_surf, (hud_x, hud_y + 58))

        # Rad suit equipped indicator
        if self.player.equipment.get('body'):
            suit_surf = self.font.render("☢ SUIT", True, (80, 200, 255))
            self.screen.blit(suit_surf, (hud_x + 230, hud_y + 55))

        # Hiding indicator
        if self.player.hiding:
            hiding_surface = pygame.font.SysFont('Arial', 32, bold=True).render(
                "HIDING", True, (150, 255, 150))
            hiding_rect = hiding_surface.get_rect(topright=(SCREEN_WIDTH - 50, 100))
            pygame.draw.rect(self.screen, (50, 100, 50), hiding_rect.inflate(20, 10))
            self.screen.blit(hiding_surface, hiding_rect.topleft)

        pygame.display.flip()

    # ---- run ----

    def run(self):
        MUSIC.play(MUS_MENU)
        started = self.title_screen.run(self.screen, self.clock)
        if not started:
            MUSIC.stop()
            pygame.quit()
            return

        self.clock.tick(100)
        MUSIC.start_rotation(MUS_AMBIENT)

        self._ai_running = True
        self._ai_thread = threading.Thread(target=self._ai_loop, daemon=True, name='AI-Thread')
        self._ai_thread.start()

        self.running = True
        while self.running:
            dt = self.clock.tick(100) / 1000.0
            self._last_dt = dt
            self.handle_events()
            self.update(dt)
            self.render()


            if not self.player.alive:
                self.game_over_screen.run(self.screen, self.clock)
                self.running = False

        self._ai_running = False
        if self._ai_thread:
            self._ai_thread.join(timeout=1.0)

            pygame.quit()


if __name__ == "__main__":
   game = Game()
   game.run()