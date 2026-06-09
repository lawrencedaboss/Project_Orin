import pygame
import math

class Bullet:
    def __init__(self, x, y, vx, vy, speed=900, radius=4, color=(255, 220, 50), loading_zone_x=0, loading_zone_y=0,collidemonster=True,collidewall=True):
        self.x = x
        self.y = y
        # velocity is normalized direction multiplied by speed
        self.vx = vx * speed
        self.vy = vy * speed
        self.life = 2
        self.loading_zone_x = loading_zone_x
        self.loading_zone_y = loading_zone_y
        self.radius = radius
        self.color = color
        self.rect = pygame.Rect(int(x - radius), int(y - radius), radius * 2, radius * 2)
        self.collidemonster = collidemonster
        self.collidewall = collidewall  
        self.walltime=0
    def update(self, dt):
        self.x += self.vx * dt*(self.life+1)/3
        self.y += self.vy * dt*(self.life+1)/3
        self.life -= dt
        self.rect.x = int(self.x - self.radius)
        self.rect.y = int(self.y - self.radius)
        return self.life > 0
    def check_wall_collision(self,dt):
        if not self.collidewall:
            self.walltime+=dt
            if self.walltime>0.1:
                self.collidewall=True
                self.walltime=0

    def draw(self, screen):
        self.rect=pygame.draw.circle(screen, self.color, (int(self.x), int(self.y)), self.radius)


class BulletsManager:
    def __init__(self):
        self.bullets = []

    def fire(self, x, y, dx, dy, loading_zone_x=0, loading_zone_y=0):
        # normalize direction
        mag = math.hypot(dx, dy)
        if mag == 0:
            return
        nx = dx / mag
        ny = dy / mag
        b = Bullet(x, y, nx, ny, loading_zone_x=loading_zone_x, loading_zone_y=loading_zone_y)
        self.bullets.append(b)
    def update(self, dt):
        self.bullets = [b for b in self.bullets if b.update(dt)]

    def draw(self, screen):
        for b in self.bullets:
            b.draw(screen)
