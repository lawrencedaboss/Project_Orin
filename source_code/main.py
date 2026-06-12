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
from map_data import (get_zone_type, get_items_in_zone, get_item_def,
                      get_zone_grid, TILE_EMPTY,TILE_WALL, TILE_OBJECT, UNIT_W, UNIT_H,
                      ZONE_TILE_WIDTH, ZONE_TILE_HEIGHT)
from bullets import BulletsManager
from bullets import Bullet
from food import Food






class PauseScreen:
   def __init__(self):
       self.title_font = pygame.font.SysFont('Arial', 64)
       self.text_font = pygame.font.SysFont('Arial', 24)
       self.small_font = pygame.font.SysFont('Arial', 18)
       self.title_surface = self.title_font.render("paused", True, (255, 255, 255))
       self.resume_surface = self.text_font.render("space: resume", True, (220, 220, 220))
       self.quit_surface = self.text_font.render("esc/q: quit", True, (220, 220, 220))
       self.keybind_surface = self.text_font.render("k: keybinds", True, (220, 220, 220))
       self.rebinding_key = None
       self.rebinding_action = None


   def show_keybind_menu(self, screen, clock):
       """Shows keybind customization menu."""
       actions = ['pause', 'hide', 'action', 'inventory', 'move_up', 'move_down', 'move_left', 'move_right', 'exit']
       selected = 0


       while True:
           clock.tick(60)
           for event in pygame.event.get():
               if event.type == pygame.QUIT:
                   return False
               if event.type == pygame.KEYDOWN:
                   if event.key == pygame.K_ESCAPE:
                       return True
                   if event.key == pygame.K_UP:
                       selected = (selected - 1) % len(actions)
                   if event.key == pygame.K_DOWN:
                       selected = (selected + 1) % len(actions)
                   if event.key == pygame.K_RETURN:
                       self.rebind_key(actions[selected], screen, clock)


           overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
           overlay.fill((15, 20, 45, 190))
           screen.blit(overlay, (0, 0))


           panel = pygame.Surface((400, 350), pygame.SRCALPHA)
           panel.fill((30, 40, 80, 220))
           panel_rect = panel.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2))
           screen.blit(panel, panel_rect)


           title = self.text_font.render("KEYBINDS", True, (255, 255, 255))
           screen.blit(title, (panel_rect.centerx - title.get_width() / 2, panel_rect.top + 20))


           for i, action in enumerate(actions):
               key_name = pygame.key.name(KEYBINDS[action])
               text = f"{action}: {key_name}"
               color = (255, 200, 100) if i == selected else (200, 200, 200)
               surface = self.small_font.render(text, True, color)
               screen.blit(surface, (panel_rect.left + 30, panel_rect.top + 70 + i * 30))


           hint = self.small_font.render("Arrow keys: navigate | Enter: rebind | Esc: back", True, (150, 150, 150))
           screen.blit(hint, (panel_rect.centerx - hint.get_width() / 2, panel_rect.bottom - 40))


           pygame.display.flip()


   def _save_keybind(self, action, key):
       """Save keybind change to config.json."""
       import json
       try:
           with open('config.json', 'r') as f:
               config = json.load(f)
           key_name = pygame.key.name(key).lower()
           config['keybinds'][action] = key_name
           with open('config.json', 'w') as f:
               json.dump(config, f, indent=2)
       except:
           pass  # Fail silently if can't save


   def rebind_key(self, action, screen, clock):
       """Wait for player to press a new key for the action and save to config."""
       prompt = self.text_font.render(f"Press key for {action}...", True, (255, 200, 100))


       while True:
           clock.tick(60)
           for event in pygame.event.get():
               if event.type == pygame.QUIT:
                   return False
               if event.type == pygame.KEYDOWN:
                   if event.key != pygame.K_ESCAPE:
                       KEYBINDS[action] = event.key
                       self._save_keybind(action, event.key)
                   return True


           overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
           overlay.fill((15, 20, 45, 190))
           screen.blit(overlay, (0, 0))
           screen.blit(prompt, (SCREEN_WIDTH // 2 - prompt.get_width() // 2, SCREEN_HEIGHT // 2 - 50))
           pygame.display.flip()


   def run(self, screen, clock):
       """Blocks until the player resumes or quits."""
       while True:
           clock.tick(60)
           for event in pygame.event.get():
               if event.type == pygame.QUIT:
                   return False
               if event.type == pygame.KEYDOWN:
                   if event.key == pygame.K_SPACE or event.key == pygame.K_p:
                       return True
                   if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                       return False
                   if event.key == pygame.K_k:
                       if not self.show_keybind_menu(screen, clock):
                           return False


           overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
           overlay.fill((15, 20, 45, 190))
           screen.blit(overlay, (0, 0))


           panel = pygame.Surface((SCREEN_WIDTH - 240, 280), pygame.SRCALPHA)
           panel.fill((30, 40, 80, 220))
           panel_rect = panel.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2))
           screen.blit(panel, panel_rect)


           screen.blit(self.title_surface, (panel_rect.centerx - self.title_surface.get_width() / 2,
                                           panel_rect.top + 30))
           screen.blit(self.resume_surface, (panel_rect.left + 40, panel_rect.top + 120))
           screen.blit(self.quit_surface, (panel_rect.left + 40, panel_rect.top + 160))
           screen.blit(self.keybind_surface, (panel_rect.left + 40, panel_rect.top + 200))
           pygame.display.flip()








class GameOverScreen:
   def __init__(self):
       self.font = pygame.font.SysFont('Arial', 48)
       self.sub_font = pygame.font.SysFont('Arial', 28)
       self.title_surface = self.font.render("you died", True, (200, 0, 0))
       self.prompt_surface = self.sub_font.render("press space to quit", True, (255, 255, 255))




   def run(self, screen, clock):
       """Shows the game-over screen until the player presses SPACE or closes."""
       while True:
           clock.tick(60)
           for event in pygame.event.get():
               if event.type == pygame.QUIT:
                   return
               if event.type == pygame.KEYDOWN:
                   if event.key == pygame.K_SPACE:
                       return




           screen.fill((0, 0, 0))
           screen.blit(self.title_surface, (310, 220))
           screen.blit(self.prompt_surface, (295, 300))
           pygame.display.flip()








class InventoryScreen:
   def __init__(self):
       self.title_font = pygame.font.SysFont('Arial', 48, bold=True)
       self.text_font = pygame.font.SysFont('Arial', 22)
       self.small_font = pygame.font.SysFont('Arial', 18)


   def run(self, screen, clock, player, boxes):
       """Shows inventory until the player presses ESC or I."""
       while True:
           clock.tick(60)
           for event in pygame.event.get():
               if event.type == pygame.QUIT:
                   return False
               if event.type == pygame.KEYDOWN:
                   if event.key == pygame.K_ESCAPE or event.key == KEYBINDS['inventory']:
                       return True
                   if event.key == pygame.K_u and player.inventory:
                       player.use_inventory_item()
                       continue


           overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
           overlay.fill((15, 20, 45, 200))
           screen.blit(overlay, (0, 0))


           # Main panel
           panel_width = 500
           panel_height = 450
           panel_x = (SCREEN_WIDTH - panel_width) // 2
           panel_y = (SCREEN_HEIGHT - panel_height) // 2
           
           panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
           panel.fill((30, 40, 80, 240))
           screen.blit(panel, (panel_x, panel_y))
           
           pygame.draw.rect(screen, (100, 150, 200), (panel_x, panel_y, panel_width, panel_height), 3)


           # Title
           title = self.title_font.render("INVENTORY", True, (200, 220, 255))
           title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, panel_y + 25))
           screen.blit(title, title_rect)


           y_offset = panel_y + 70
           
           # Objects collected
           objects_text = self.text_font.render(f"Objects Collected: {player.collected_objects}/{len(boxes)}", True, (150, 255, 150))
           screen.blit(objects_text, (panel_x + 30, y_offset))
           y_offset += 45


           # Object list
           collected_count = 0
           for i, box in enumerate(boxes, 1):
               status = "✓ Collected" if box.collected else "○ Not found"
               color = (150, 255, 150) if box.collected else (150, 150, 150)
               obj_text = self.small_font.render(f"  Box {i}: {status}", True, color)
               screen.blit(obj_text, (panel_x + 50, y_offset))
               y_offset += 30
               if box.collected:
                   collected_count += 1


           y_offset += 15

           # Hunger status
           hunger_bar_width = 200
           hunger_bar_height = 20
           hunger_x = panel_x + 30
           hunger_y = y_offset

           hunger_text = self.text_font.render("Hunger:", True, (255, 200, 100))
           screen.blit(hunger_text, (hunger_x, hunger_y))

           hunger_percentage = player.hunger / 100
           pygame.draw.rect(screen, (50, 50, 50), (hunger_x + 150, hunger_y + 2, hunger_bar_width, hunger_bar_height))
           pygame.draw.rect(screen, (255, 140, 0), (hunger_x + 150, hunger_y + 2, hunger_bar_width * hunger_percentage, hunger_bar_height))
           pygame.draw.rect(screen, (200, 200, 200), (hunger_x + 150, hunger_y + 2, hunger_bar_width, hunger_bar_height), 1)

           hunger_pct = self.small_font.render(f"{player.hunger:.0f}%", True, (255, 255, 255))
           screen.blit(hunger_pct, (hunger_x + 360, hunger_y + 2))

           y_offset += 35

           # Radiation status
           radiation_bar_width = 200
           radiation_bar_height = 20
           radiation_x = panel_x + 30
           radiation_y = y_offset

           radiation_text = self.text_font.render("Radiation:", True, (150, 255, 150))
           screen.blit(radiation_text, (radiation_x, radiation_y))

           radiation_percentage = min(player.radiation / player.RADIATION_MAX, 1.0)
           pygame.draw.rect(screen, (50, 50, 50), (radiation_x + 150, radiation_y + 2, radiation_bar_width, radiation_bar_height))
           pygame.draw.rect(screen, (0, 255, 75), (radiation_x + 150, radiation_y + 2, radiation_bar_width * radiation_percentage, radiation_bar_height))
           pygame.draw.rect(screen, (200, 200, 200), (radiation_x + 150, radiation_y + 2, radiation_bar_width, radiation_bar_height), 1)

           radiation_pct = self.small_font.render(f"{player.radiation:.0f}%", True, (255, 255, 255))
           screen.blit(radiation_pct, (radiation_x + 360, radiation_y + 2))

           y_offset += 55
           inv_title = self.small_font.render("Inventory items:", True, (255, 255, 255))
           screen.blit(inv_title, (panel_x + 30, y_offset))
           y_offset += 28

           if player.inventory:
               for item_id in player.inventory:
                   item_def = get_item_def(item_id)
                   name = item_def.get('name', item_id)
                   desc = item_def.get('description', '')
                   screen.blit(self.small_font.render(f"• {name}", True, (255, 230, 180)), (panel_x + 50, y_offset))
                   y_offset += 24
                   if desc:
                       screen.blit(self.small_font.render(f"  {desc}", True, (190, 205, 240)), (panel_x + 60, y_offset))
                       y_offset += 22
           else:
               screen.blit(self.small_font.render("No consumables collected yet.", True, (200, 200, 200)), (panel_x + 50, y_offset))

           y_offset = panel_y + panel_height - 50
           hint = self.small_font.render("Press U to use a held item | ESC/I to close", True, (150, 150, 150))
           screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, y_offset))


           pygame.display.flip()








class Game:
   def __init__(self):
       pygame.mixer.pre_init(44100, -16, 1, 512)
       pygame.init()
       init_audio()   # load all .wav/.ogg files from assets/sounds/ — must be after pygame.init()
       self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
       pygame.display.set_caption("Project Orin")
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

                   # Item positions are stored in map units, then converted to
                   # pixel coordinates for the runtime box objects.
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
               Box(520, 90, 1, 0),
               Box(240, 420, 0, 1),
               Box(560, 360, 1, 1),
           ]
       self.font = pygame.font.SysFont('Arial', 20)




       self.title_screen = TitleScreen()
       self.pause_screen = PauseScreen()
       self.inventory_screen = InventoryScreen()
       self.game_over_screen = GameOverScreen()
       self.bullets = BulletsManager()
       self.last_mouse_pressed = False
       self.last_shoot_pressed = False



       self.running = False

       # Threading: monster AI and animal updates run on a background thread
       self._lock = threading.Lock()
       self._ai_thread = None
       self._ai_running = False

       # Proximity beep / drone
       self._beep_sound  = self._create_beep()
       self._drone_sound = self._create_drone()
       self._beep_timer    = 0.0
       self._beep_interval = None   # None = silent
       self._droning       = False  # True while drone is looping

       # Tile map — wall rects rebuilt whenever the player changes zone
       self._last_zone  = (-1, -1)
       self._wall_rects = []




   @staticmethod
   def _create_beep(frequency=880, duration=0.045, sample_rate=44100, volume=0.35):
       """Synthesise a short sine-wave beep without numpy."""
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
       """Synthesise a seamlessly-looping continuous tone at the same pitch as the beep.

       Buffer length is a whole number of cycles so the loop point is
       click-free when pygame repeats it with play(-1).
       """
       n_cycles = max(1, round(frequency * 1.0))   # one second of whole cycles
       n = int(sample_rate * n_cycles / frequency)
       buf = array.array('h')
       for i in range(n):
           t = i / sample_rate
           val = volume * math.sin(2 * math.pi * frequency * t)
           buf.append(int(32767 * val))
       return pygame.mixer.Sound(buffer=buf)

   def _try_fire(self):
       if pygame.mouse.get_pressed()[0] and not self.player.hiding:
           mx, my = pygame.mouse.get_pos()
           mx -= MAP_LEFT
           my -= MAP_TOP
           px, py = self.player.rect.center
           dx = mx - px
           dy = my - py
           self.bullets.fire(px, py, dx, dy, self.player.loadingzonex, self.player.loadingzoney)

   def _ai_loop(self):
       """Background thread: updates monster AI and all animals."""
       interval = 1.0 / FPS
       last = _time.perf_counter()
       while self._ai_running:
           now = _time.perf_counter()
           dt = min(now - last, 0.05)  # cap to avoid spiral on lag
           last = now

           with self._lock:
               if self.player.alive and self.running:
                   if self.player.hiding:
                       self.monster.update(
                           None, None,
                           self.player.loadingzonex, self.player.loadingzoney,
                           dt, hiding=True,
                       )
                   else:
                       self.monster.update(
                           self.player.x, self.player.y,
                           self.player.loadingzonex, self.player.loadingzoney,
                           dt, hiding=False,
                       )
                   for animal in self.animals:
                       animal.update(dt)

           sleep_for = interval - (_time.perf_counter() - now)
           if sleep_for > 0:
               _time.sleep(sleep_for)


   def _in_player_zone(self, entity):
       """Returns True if the entity is in the same loading zone as the player."""
       return (entity.loading_zone_x == self.player.loadingzonex and
               entity.loading_zone_y == self.player.loadingzoney)


   # ------------------------------------------------------------------ tile map

   def _build_wall_rects(self, zone_x, zone_y):
       """Return a list of pygame.Rects for every TILE_WALL in the zone."""
       rects = []
       grid = get_zone_grid(zone_x, zone_y)
       if not grid:
           return rects

       tile_w = MAP_WIDTH // max(1, len(grid[0]))
       tile_h = MAP_HEIGHT // max(1, len(grid))

       for ty, row in enumerate(grid):
           for tx, tile in enumerate(row):
               if tile == TILE_WALL:
                   rects.append(pygame.Rect(tx * tile_w, ty * tile_h, tile_w, tile_h))
       return rects


   def _resolve_wall_collisions(self):
       """Push the player out of any wall tile they overlap."""
       pr = self.player.rect
       for wall in self._wall_rects:
           if not pr.colliderect(wall):
               continue
           # Overlap on each side
           left_overlap  = pr.right  - wall.left
           right_overlap = wall.right - pr.left
           top_overlap   = pr.bottom - wall.top
           bot_overlap   = wall.bottom - pr.top
           # Smallest penetration axis
           min_x = left_overlap  if left_overlap  < right_overlap else -right_overlap
           min_y = top_overlap   if top_overlap   < bot_overlap   else -bot_overlap
           if abs(min_x) < abs(min_y):
               self.player.x -= min_x
           else:
               self.player.y -= min_y
           self.player.rect.x = int(self.player.x)
           self.player.rect.y = int(self.player.y)


   def _render_tiles(self, surface):
       """Draw the tile map for the player's current loading zone."""
       grid = get_zone_grid(self.player.loadingzonex, self.player.loadingzoney)
       if not grid:
           return

       tile_w = MAP_WIDTH // max(1, len(grid[0]))
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
                   pygame.draw.rect(surface, (55, 55, 65),
                                    (rx, ry, tile_w, tile_h))
                   pygame.draw.rect(surface, (80, 80, 95),
                                    (rx, ry, tile_w, tile_h), 2)
               elif tile == TILE_OBJECT:
                   pygame.draw.rect(surface, (100, 70, 30),
                                    (rx + inner_pad_x, ry + inner_pad_y,
                                     tile_w - inner_pad_x * 2,
                                     tile_h - inner_pad_y * 2))
                   pygame.draw.rect(surface, (150, 110, 50),
                                    (rx + inner_pad_x, ry + inner_pad_y,
                                     tile_w - inner_pad_x * 2,
                                     tile_h - inner_pad_y * 2), 2)




   def handle_events(self):
       for event in pygame.event.get():
           if event.type == pygame.QUIT:
               self.running = False
           if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
               self._try_fire()
           if event.type == pygame.KEYDOWN:
               if event.key == KEYBINDS['pause']:
                   resume = self.pause_screen.run(self.screen, self.clock)
                   if not resume:
                       self.running = False
                   else:
                       self.clock.tick(FPS)
               if event.key == KEYBINDS['hide']:
                   was_hiding = self.player.hiding
                   self.player.toggle_hiding(self.boxes)
                   if self.player.hiding != was_hiding:
                       SFX.play(SND_HIDE if self.player.hiding else SND_UNHIDE)
               if event.key == KEYBINDS['action']:
                   self.try_use_action()
               if event.key == KEYBINDS['inventory']:
                   self.inventory_screen.run(self.screen, self.clock, self.player, self.boxes)


   def is_in_range_of_box(self):
       """Check if player is in range of any uncollected box."""
       for box in self.boxes:
           if self._in_player_zone(box) and not box.collected:
               dist_x = abs(self.player.x - box.x)
               dist_y = abs(self.player.y - box.y)
               if dist_x < 60 and dist_y < 60:
                   return True
       return False

   def food_items_in_player_zone(self):
       """Return food items that are in the same loading zone as the player."""
       return [food_item for food_item in self.food
               if self._in_player_zone(food_item)]

   def is_in_range_of_food(self):
       """Check if player is in range of any food item in the same zone."""
       for food_item in self.food_items_in_player_zone():
           dist_x = abs(self.player.x - food_item.x)
           dist_y = abs(self.player.y - food_item.y)
           if dist_x < 60 and dist_y < 60:
               return True
       return False

   def try_eat_food(self):
       """Eat the closest nearby food item if the player is in range."""
       nearest_food = None
       nearest_distance = None
       for food_item in self.food_items_in_player_zone():
           dist_x = abs(self.player.x - food_item.x)
           dist_y = abs(self.player.y - food_item.y)
           if dist_x < 60 and dist_y < 60:
               distance = math.hypot(dist_x, dist_y)
               if nearest_food is None or distance < nearest_distance:
                   nearest_food = food_item
                   nearest_distance = distance
       if nearest_food is not None:
           self.player.eat(FOOD_HUNGER_RESTORE)
           self.food.remove(nearest_food)
           SFX.play(SND_COLLECT)
           return True
       return False

   def try_collect_object(self):
       """Try to collect an object from a nearby box."""
       for box in self.boxes:
           if self._in_player_zone(box) and not box.collected:
               # Check if player is close enough to the box
               dist_x = abs(self.player.x - box.x)
               dist_y = abs(self.player.y - box.y)
               if dist_x < 60 and dist_y < 60:
                   box.collect(self.player)
                   SFX.play(SND_COLLECT)
                   return True
       return False

   def try_use_action(self):
       """Use the action key for eating food or collecting nearby objects."""
       food_available = self.is_in_range_of_food()
       box_available = self.is_in_range_of_box()
       if food_available and box_available:
           # Prefer the nearest interactable item when both are available.
           nearest_food = None
           nearest_box = None
           nearest_food_dist = None
           nearest_box_dist = None
           for food_item in self.food_items_in_player_zone():
               dist = math.hypot(self.player.x - food_item.x, self.player.y - food_item.y)
               if nearest_food is None or dist < nearest_food_dist:
                   nearest_food = food_item
                   nearest_food_dist = dist
           for box in self.boxes:
               if not self._in_player_zone(box) or box.collected:
                   continue
               dist = math.hypot(self.player.x - box.x, self.player.y - box.y)
               if dist < 60 and (nearest_box is None or dist < nearest_box_dist):
                   nearest_box = box
                   nearest_box_dist = dist
           if nearest_food is not None and (nearest_box is None or nearest_food_dist <= nearest_box_dist):
               self.player.eat(FOOD_HUNGER_RESTORE)
               self.food.remove(nearest_food)
               SFX.play(SND_COLLECT)
               return True
           if nearest_box is not None:
               nearest_box.collect(self.player)
               SFX.play(SND_COLLECT)
               return True
           return False
       if food_available:
           return self.try_eat_food()
       if box_available:
           return self.try_collect_object()
       return False




   def update(self, dt):
       _zone_dist = None
       # Hold the lock for the entire update so the AI thread never reads
       # player position mid-transition (e.g. x wrapped but zone not yet updated).
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

               # Rebuild wall rect cache when the player enters a new zone
               zone_key = (self.player.loadingzonex, self.player.loadingzoney)
               if zone_key != self._last_zone:
                   self._last_zone  = zone_key
                   self._wall_rects = self._build_wall_rects(*zone_key)

               # Push player out of any wall tiles
               self._resolve_wall_collisions()
               
           # Radiation accumulates when the monster is in the player's zone.
           if self.monster.active and self._in_player_zone(self.monster):
               if self.player.hiding:
                   self.player.radiation += dt * RADIATION_RATE * 0.2
               else:
                   self.player.radiation += dt * RADIATION_RATE
           else: self.player.radiation = max(0, self.player.radiation - dt )
           # Collision colour feedback.
           if (self.monster.active and self._in_player_zone(self.monster)
                   and self.player.rect.colliderect(self.monster.rect)
                   and not self.player.hiding):
               self.player.color = (255, 100, 100)
           else:
               self.player.color = (0, 255, 0)

           # Read zone + pixel distance for beep (while lock is held)
           if self.monster.active:
               _zone_dist = self.monster._zone_distance(
                   self.player.loadingzonex, self.player.loadingzoney)
               _world_dx = ((self.monster.loading_zone_x - self.player.loadingzonex)
                            * MAP_WIDTH  + self.monster.x - self.player.x)
               _world_dy = ((self.monster.loading_zone_y - self.player.loadingzoney)
                            * MAP_HEIGHT + self.monster.y - self.player.y)
               _pixel_dist = math.sqrt(_world_dx * _world_dx + _world_dy * _world_dy)
           else:
               _zone_dist  = None
               _pixel_dist = None
       self.bullets.update(dt)

       # Bullet-wall collisions
       for bullet in list(self.bullets.bullets):
           if self._in_player_zone(bullet):
               for wall in self._wall_rects:
                   if bullet.rect.colliderect(wall):
                       if bullet.collidewall:
                           bullet.vx = -0.99 * bullet.vx
                           bullet.vy = -0.99 * bullet.vy
                           bullet.collidewall = False
                       break

       # Bullet-animal collisions
       for bullet in list(self.bullets.bullets):
           for animal in list(self.animals):
               if self._in_player_zone(animal) and bullet.rect.colliderect(animal.rect):
                   self.bullets.bullets.remove(bullet)
                   # Spawn food at animal's location
                   self.food.append(Food(animal.x, animal.y, 8,
                                         animal.loading_zone_x,
                                         animal.loading_zone_y))
                   self.animals.remove(animal)
                   break
                   

       # Bullet-monster collisions and player hit checks
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
       # Proximity beep / flatline drone — runs on main thread, outside lock
       _MAX_BEEP_PX = MAP_WIDTH * 9  # silence beyond ~9 zones' worth of pixels
       if not self.player.alive:
           self._beep_sound.stop()
       elif _zone_dist is not None and _zone_dist == 0:
           # Same zone — flatline into continuous drone
           if not self._droning:
               self._beep_sound.stop()
               self._drone_sound.play(-1)   # loop forever
               self._droning = True
           self._beep_interval = None
           self._beep_timer    = 0.0

       elif _pixel_dist is not None and _pixel_dist < _MAX_BEEP_PX:
           # Use raw pixel distance so beeps respond to position within zones,
           # but ease the interval so the alert rate ramps up smoothly instead
           # of snapping to the next loading-zone value.
           if self._droning:
               self._drone_sound.stop()
               self._droning = False
           t = _pixel_dist / _MAX_BEEP_PX          # 0 = right next door, 1 = edge of range
           target_interval = 0.12 + t * (2.5 - 0.12)

           if self._beep_interval is None:
               self._beep_interval = target_interval
           else:
               smoothing = min(1.0, dt * 4.0)
               self._beep_interval += (target_interval - self._beep_interval) * smoothing

       else:
           # Far away or inactive — silence everything
           if self._droning:
               self._drone_sound.stop()
               self._droning = False
           self._beep_interval = None
       if not self.player.alive:
           # Far away or inactive — silence everything
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

       # Music transitions based on monster proximity
       if _zone_dist is not None and _zone_dist <= 4:
           if MUSIC.current != MUS_TENSE:
               MUSIC.play(MUS_TENSE)
       else:
           if MUSIC.current != MUS_AMBIENT:
               MUSIC.play(MUS_AMBIENT)












   def render(self):
       self.screen.fill((12, 16, 30))
       pygame.draw.rect(self.screen, (18, 22, 36), (0, 0, SCREEN_WIDTH, MAP_TOP))
       self.game_surface.fill((12, 16, 30))
       self._render_tiles(self.game_surface)   # draw walls / objects beneath everything else
       self.player.draw(self.game_surface)


       # Only draw boxes that share the player's zone
       for box in self.boxes:
           if self._in_player_zone(box):
               box.draw(self.game_surface)

       # Draw food items in the player's zone
       for food_item in self.food:
           if self._in_player_zone(food_item):
               food_item.draw(self.game_surface)

       # Draw bullets on the game surface so they appear above the map and under the HUD.
       self.bullets.draw(self.game_surface)

       # Only draw monster when active and in the player's zone
       if self.monster.active and self._in_player_zone(self.monster):
           self.monster.draw(self.game_surface)




       # Only draw animals that share the player's zone
       for animal in self.animals:
           if self._in_player_zone(animal):
               animal.draw(self.game_surface)


       self.screen.blit(self.game_surface, (MAP_LEFT, MAP_TOP))
       pygame.draw.rect(self.screen, (100, 100, 120), (MAP_LEFT - 2, MAP_TOP - 2, MAP_WIDTH + 4, MAP_HEIGHT + 4), 2)



       # Build hint text using the actual bound keys
       k_hide = pygame.key.name(KEYBINDS['hide']).upper()
       k_action = pygame.key.name(KEYBINDS['action']).upper()
       k_inv = pygame.key.name(KEYBINDS['inventory']).upper()

       if self.player.hiding:
           hint_text = f"{k_hide}: exit  |  {k_inv}: inventory"
       elif any(box.can_hide(self.player) for box in self.boxes):
           if self.is_in_range_of_box():
               hint_text = f"{k_hide}: hide  |  {k_action}: take item  |  {k_inv}: inventory"
           else:
               hint_text = f"{k_hide}: hide  |  {k_inv}: inventory"
       else:
           food_nearby = self.is_in_range_of_food()
           box_nearby = self.is_in_range_of_box()
           if box_nearby and food_nearby:
               hint_text = f"{k_action}: take item / eat food  |  {k_inv}: inventory"
           elif box_nearby:
               hint_text = f"{k_action}: take item  |  {k_inv}: inventory"
           elif food_nearby:
               hint_text = f"{k_action}: eat food  |  {k_inv}: inventory"
           else:
               hint_text = f"{k_inv}: inventory"


       zone_text = f"Zone: {self.player.loadingzonex + 1}/{ZONE_COUNT_X}, {self.player.loadingzoney + 1}/{ZONE_COUNT_Y}"
       hint_surface = self.font.render(hint_text, True, (255, 255, 255))
       zone_surface = self.font.render(zone_text, True, (255, 255, 255))
       self.screen.blit(hint_surface, (SCREEN_WIDTH - 350, 20))
       self.screen.blit(zone_surface, (SCREEN_WIDTH - 350, 50))

       # Draw top HUD bars for radiation and hunger
       hud_x = MAP_LEFT + 20
       hud_y = 20
       pygame.draw.rect(self.screen, (255, 255, 255), (hud_x, hud_y, 220, 22), 2)
       pygame.draw.rect(self.screen, (0, 255, 75), (hud_x + 2, hud_y + 2,
                        int(min(self.player.radiation / self.player.RADIATION_MAX, 1) * 216), 18))
       pygame.draw.rect(self.screen, (255, 255, 255), (hud_x, hud_y + 30, 220, 22), 2)
       pygame.draw.rect(self.screen, (255, 140, 0), (hud_x + 2, hud_y + 32,
                        int(self.player.hunger / 100 * 216), 18))
       radiation_label = self.font.render("Radiation", True, (255, 255, 255))
       hunger_label = self.font.render("Hunger", True, (255, 255, 255))
       self.screen.blit(radiation_label, (hud_x + 230, hud_y + 2))
       self.screen.blit(hunger_label, (hud_x + 230, hud_y + 32))






       # Display hiding indicator


       if self.player.hiding:
           hiding_surface = pygame.font.SysFont('Arial', 32, bold=True).render("HIDING", True, (150, 255, 150))
           hiding_rect = hiding_surface.get_rect(topright=(SCREEN_WIDTH - 50, 100))
           pygame.draw.rect(self.screen, (50, 100, 50), hiding_rect.inflate(20, 10))
           self.screen.blit(hiding_surface, hiding_rect.topleft)




       pygame.display.flip()




   def run(self):
       MUSIC.play(MUS_MENU)
       started = self.title_screen.run(self.screen, self.clock)
       if not started:
           MUSIC.stop()
           pygame.quit()
           return




       # Discard time accumulated on the title screen
       self.clock.tick(100)
       MUSIC.play(MUS_AMBIENT)  # switch from menu music to ambient on game start




       # Start the AI background thread
       self._ai_running = True
       self._ai_thread = threading.Thread(target=self._ai_loop, daemon=True, name='AI-Thread')
       self._ai_thread.start()

       self.running = True
       while self.running:
           dt = self.clock.tick(100) / 1000.0
           self.handle_events()
           self.update(dt)
           self.render()

           if not self.player.alive:
               self.game_over_screen.run(self.screen, self.clock)
               self.running = False

       # Stop the AI thread cleanly
       self._ai_running = False
       if self._ai_thread:
           self._ai_thread.join(timeout=1.0)

       pygame.quit()








if __name__ == "__main__":
   game = Game()
   game.run()








