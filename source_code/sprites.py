import pygame
import os
from map_data import TILE_EMPTY, TILE_WALL, TILE_OBJECT, get_zone_grid, UNIT_W, UNIT_H
from config import MAP_WIDTH, MAP_HEIGHT


SPRITE_TILE_W = 16
SPRITE_TILE_H = 16

TILE_SPRITE_MAP = {
    (0, TILE_WALL):   (0, 0),
    (0, TILE_OBJECT): (1, 0),
    (1, TILE_WALL):   (0, 1),
    (1, TILE_OBJECT): (1, 1),
}

FALLBACK = {
    0: {
        TILE_WALL:   ((55, 55, 65), (80, 80, 95)),
        TILE_OBJECT: ((100, 70, 30), (150, 110, 50)),
    },
    1: {
        TILE_WALL:   ((32, 62, 28), (52, 95, 42)),
        TILE_OBJECT: ((75, 50, 18), (115, 80, 32)),
    }
}

class TileSprite(pygame.sprite.Sprite):
    def __init__(self, image, x, y):
        super().__init__()
        self.image = image
        self.rect = image.get_rect(topleft=(x, y))

class SpriteSheet:
    def __init__(self, path):
        self.loaded = False
        self.cache = {}

        if os.path.isfile(path):
            try:
                raw = pygame.image.load(path)
                self.sheet = raw.convert_alpha()
                self.loaded = True
            except pygame.error:
                self.sheet = None

    def get(self, col, row):
        key = (col, row)
        if key in self.cache:
            return self.cache[key]

        if not self.loaded:
            return None

        x = col * SPRITE_TILE_W
        y = row * SPRITE_TILE_H
        surf = self.sheet.subsurface((x, y, SPRITE_TILE_W, SPRITE_TILE_H))
        self.cache[key] = surf
        return surf

class ZoneRenderer:
    def __init__(self, sheet):
        self.sheet = sheet
        self.zone_cache = {}

    def build_zone(self, zx, zy, zone_type):
        key = (zx, zy)
        if key in self.zone_cache:
            return self.zone_cache[key]

        grid = get_zone_grid(zx, zy)
        if not grid:
            return None

        tile_w = MAP_WIDTH // len(grid[0])
        tile_h = MAP_HEIGHT // len(grid)

        group = pygame.sprite.Group()

        for ty, row in enumerate(grid):
            for tx, tile in enumerate(row):
                if tile == TILE_EMPTY:
                    continue

                if self.sheet.loaded:
                    colrow = TILE_SPRITE_MAP.get((zone_type, tile))
                    if colrow:
                        img = pygame.transform.scale(
                            self.sheet.get(*colrow),
                            (tile_w, tile_h)
                        )
                    else:
                        img = None
                else:
                    fill, border = FALLBACK[zone_type][tile]
                    img = pygame.Surface((tile_w, tile_h))
                    img.fill(fill)
                    pygame.draw.rect(img, border, img.get_rect(), 2)

                if img:
                    sprite = TileSprite(img, tx * tile_w, ty * tile_h)
                    group.add(sprite)

        self.zone_cache[key] = group
        return group

    def render(self, surface, zx, zy, zone_type):
        group = self.build_zone(zx, zy, zone_type)
        if group:
            group.draw(surface)

# Module-level singleton
SHEET_PATH = os.path.join("assets", "sprites", "tiles.png")
ZONE_RENDERER = ZoneRenderer(SpriteSheet(SHEET_PATH))
def draw_player(surface, player, dt=0):
    player.draw(surface, dt)

def draw_monster(surface, monster):
    monster.draw(surface)

def draw_animal(surface, animal):
    animal.draw(surface)

def draw_bullet(surface, bullet):
    bullet.draw(surface)

def draw_food(surface, food):
    food.draw(surface)

def init_sprites():
    pass
