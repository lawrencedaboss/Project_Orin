import pygame

from config import FOOD_HUNGER_RESTORE
from sprites import draw_food as _draw_food_sprite

class Food:
    def __init__(self, x, y, size, loading_zone_x, loading_zone_y, item_id="food_can"):
        self.x = x
        self.y = y
        self.size = size
        self.loading_zone_x = loading_zone_x
        self.loading_zone_y = loading_zone_y
        self.item_id = item_id
        self.nutrition = FOOD_HUNGER_RESTORE
        self.rect = pygame.Rect(self.x, self.y, self.size, self.size)

    def update(self, dt):
        pass

    def draw(self, surface):
        _draw_food_sprite(surface, self.rect, self.item_id)
