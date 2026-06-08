import pygame


class Box:
    WIDTH = 32
    HEIGHT = 32

    def __init__(self, x, y, loading_zone_x, loading_zone_y):
        self.x = x
        self.y = y
        self.loading_zone_x = loading_zone_x
        self.loading_zone_y = loading_zone_y
        self.collected = False
        self.rect = pygame.Rect(self.x, self.y, self.WIDTH, self.HEIGHT)

    def update_rect(self):
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

    def draw(self, surface):
        box_color = (80, 50, 20) if self.collected else (150, 75, 0)
        pygame.draw.rect(surface, box_color, self.rect)
        pygame.draw.rect(surface, (255, 255, 255), self.rect, 2)
        if not self.collected:
            object_rect = pygame.Rect(self.x + 8, self.y + 8, 16, 16)
            pygame.draw.rect(surface, (255, 215, 0), object_rect)

    def collect(self, player):
        if not self.collected:
            self.collected = True
            player.collected_objects += 1

    def can_hide(self, player):
        return (
            self.collected
            and self.loading_zone_x == player.loadingzonex
            and self.loading_zone_y == player.loadingzoney
            and self.rect.inflate(24, 24).colliderect(player.rect)
        )
