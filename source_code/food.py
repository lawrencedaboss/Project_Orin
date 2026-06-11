import pygame
class Food:
    def __init__(self, x, y, size, loading_zone_x=0, loading_zone_y=0):
        self.x = x
        self.y = y
        self.size = size
        self.loading_zone_x = loading_zone_x
        self.loading_zone_y = loading_zone_y
        self.rect = pygame.Rect(self.x, self.y, self.size, self.size)
    def update(self, dt):
        pass

    def draw(self, surface):
        pygame.draw.rect(surface, (255, 100, 100), self.rect)
