import pygame

from map_data import get_item_def


class Box:
    WIDTH = 32
    HEIGHT = 32

    def __init__(self, x, y, loading_zone_x, loading_zone_y, item=None):
        self.x = x
        self.y = y
        self.loading_zone_x = loading_zone_x
        self.loading_zone_y = loading_zone_y
        self.item = item or {}
        self.item_id = self.item.get('item_id') if isinstance(self.item, dict) else None
        self.item_def = get_item_def(self.item_id) if self.item_id else {}
        self.item_name = self.item_def.get('name', self.item_id or 'Object')
        self.description = self.item_def.get('description', '')
        self.effect = self.item_def.get('effect', {})
        self.collected = False
        self.rect = pygame.Rect(self.x, self.y, self.WIDTH, self.HEIGHT)

    def _color_for_item(self):
        palette = {
            'health_pack': (120, 220, 130),
            'food_can': (255, 170, 90),
            'rad_pill': (255, 130, 180),
            'map_fragment': (95, 205, 255),
            'key': (255, 215, 90),
        }
        return palette.get(self.item_id, (160, 95, 45))

    def update_rect(self):
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

    def draw(self, surface):
        box_color = (70, 70, 80) if self.collected else self._color_for_item()
        pygame.draw.rect(surface, box_color, self.rect)
        pygame.draw.rect(surface, (255, 255, 255), self.rect, 2)
        if not self.collected:
            object_rect = pygame.Rect(self.x + 8, self.y + 8, 16, 16)
            pygame.draw.rect(surface, (255, 255, 255), object_rect)

    def collect(self, player):
        if self.collected:
            return False

        self.collected = True
        player.collected_objects += 1
        if self.item_id:
            player.inventory.append(self.item_id)
        return True

    def can_hide(self, player):
        return (
            self.collected
            and self.loading_zone_x == player.loadingzonex
            and self.loading_zone_y == player.loadingzoney
            and self.rect.inflate(24, 24).colliderect(player.rect)
        )
