import pygame
import random
from config import ANIMAL_SPEED, ANIMAL_WANDER_INTERVAL_MIN, ANIMAL_WANDER_INTERVAL_MAX


class Animal:
   def __init__(self, loading_zone_x, loading_zone_y, screen_width=800, screen_height=600, zone_count_x=20, zone_count_y=20):
       self.screen_width = screen_width
       self.screen_height = screen_height
       self.zone_count_x = zone_count_x
       self.zone_count_y = zone_count_y

       # Generate a random zone that is likely different from player's starting zone
       self.loading_zone_x = random.randint(0, self.zone_count_x - 1)
       self.loading_zone_y = random.randint(0, self.zone_count_y - 1)

       self.x = random.randint(50, self.screen_width - 50)
       self.y = random.randint(50, self.screen_height - 50)

       self.speed = ANIMAL_SPEED
       self.rect = pygame.Rect(self.x, self.y, 16, 16)

       self.targetx = random.randint(50, self.screen_width - 50)
       self.targety = random.randint(50, self.screen_height - 50)
       self.wander_timer = 0
       self.wander_interval = random.uniform(ANIMAL_WANDER_INTERVAL_MIN, ANIMAL_WANDER_INTERVAL_MAX)



   def update(self, dt):
       self.wander_timer += dt
       
       # Pick a new target periodically
       if self.wander_timer >= self.wander_interval:
           self.targetx = random.randint(50, self.screen_width - 50)
           self.targety = random.randint(50, self.screen_height - 50)
           self.wander_timer = 0
           self.wander_interval = random.uniform(ANIMAL_WANDER_INTERVAL_MIN, ANIMAL_WANDER_INTERVAL_MAX)

       difX = self.x - self.targetx
       difY = self.y - self.targety

       x_change = 0
       y_change = 0

       if difX < 0:
           x_change = 1
       elif difX > 0:
           x_change = -1

       if difY < 0:
           y_change = 1
       elif difY > 0:
           y_change = -1

       total_dif = abs(difX) + abs(difY)
       if total_dif > 10:
           vector = random.randint(0, int(total_dif))
           if vector < int(abs(difX)):
               self.x += self.speed * dt * x_change
           else:
               self.y += self.speed * dt * y_change


       if self.x >= self.screen_width:
           if self.loading_zone_x < self.zone_count_x - 1:
               self.loading_zone_x += 1
               self.x = 0
           else:
               self.x = self.screen_width - 1
       elif self.x < 0:
           if self.loading_zone_x > 0:
               self.loading_zone_x -= 1
               self.x = self.screen_width - 1
           else:
               self.x = 0

       if self.y >= self.screen_height:
           if self.loading_zone_y < self.zone_count_y - 1:
               self.loading_zone_y += 1
               self.y = 0
           else:
               self.y = self.screen_height - 1
       elif self.y < 0:
           if self.loading_zone_y > 0:
               self.loading_zone_y -= 1
               self.y = self.screen_height - 1
           else:
               self.y = 0

       self.rect.x = int(self.x)
       self.rect.y = int(self.y)


   def draw(self, surface):
       pygame.draw.rect(surface, (125, 100, 10), self.rect)





