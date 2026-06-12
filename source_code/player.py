import pygame
import math
from config import KEYBINDS, PLAYER_BASE_SPEED, HUNGER_RATE, HUNGER_SPEED_MULTIPLIER, RADIATION_MAX, PLAYER_START_X, PLAYER_START_Y, PLAYER_HUNGER_START

# radiation >= this kills the player




class Player:
   def __init__(self, screen_width=1000, screen_height=800, zone_count_x=20, zone_count_y=20):
       self.x = PLAYER_START_X
       self.y = PLAYER_START_Y

       self.screen_width = screen_width
       self.screen_height = screen_height
       self.zone_count_x = zone_count_x
       self.zone_count_y = zone_count_y

       self.radiation = 0
       self.loadingzonex = 0
       self.loadingzoney = 0

       self.rect = pygame.Rect(self.x, self.y, 20, 20)
       self.color = (0, 255, 0)
       self.speed = PLAYER_BASE_SPEED

       self.hunger = PLAYER_HUNGER_START
       self.hunger_rate = HUNGER_RATE
       self.alive = True
       self.hiding = False
       self.collected_objects = 0
       self.RADIATION_MAX = RADIATION_MAX


   def update(self, dt):
       keys = pygame.key.get_pressed()
       moving = (keys[KEYBINDS['move_left']] or keys[KEYBINDS['move_right']] or
                 keys[KEYBINDS['move_up']] or keys[KEYBINDS['move_down']])
       drain = self.hunger_rate * (2 if moving else 1) * dt
       self.hunger = max(0, self.hunger - drain)

       # Slow down as hunger falls below 50
       if self.hunger <= 50:
           self.speed = PLAYER_BASE_SPEED - HUNGER_SPEED_MULTIPLIER * (50 - self.hunger)
       else:
           self.speed = PLAYER_BASE_SPEED

   def eat(self, nutrition):
       self.hunger = min(100, self.hunger + nutrition)



   def toggle_hiding(self, boxes):
       if self.hiding:
           self.hiding = False
           return

       for box in boxes:
           if box.can_hide(self):
               self.hiding = True
               self.x = box.x + (box.WIDTH - self.rect.width) / 2
               self.y = box.y + box.HEIGHT + (self.rect.height) / 2
               self.rect.x = int(self.x)
               self.rect.y = int(self.y)
               return


   def handle_movement(self, dt):
       if not self.alive:
           return

       keys = pygame.key.get_pressed()
       moving = (keys[KEYBINDS['move_left']] or keys[KEYBINDS['move_right']] or
                 keys[KEYBINDS['move_up']] or keys[KEYBINDS['move_down']])

       dx = 0
       dy = 0
       if keys[KEYBINDS['move_left']]:  dx -= 1
       if keys[KEYBINDS['move_right']]: dx += 1
       if keys[KEYBINDS['move_up']]:    dy -= 1
       if keys[KEYBINDS['move_down']]:  dy += 1

       if self.hiding:
           return

       # Normalise diagonal movement
       if dx != 0 and dy != 0:
           factor = 1 / math.sqrt(2)
           dx *= factor
           dy *= factor

       self.x += dx * self.speed * dt
       self.y += dy * self.speed * dt

       self.rect.x = int(self.x)
       self.rect.y = int(self.y)


   def loading_zones(self):
       # Place the entity ZONE_MARGIN pixels inside the new zone so that
       # reversing direction immediately never re-triggers the opposite edge.
       ZONE_MARGIN = 30

       if self.x < 0:
           if self.loadingzonex > 0:
               self.loadingzonex -= 1
               self.x = self.screen_width - ZONE_MARGIN
           else:
               self.x = 0
       elif self.x >= self.screen_width:
           if self.loadingzonex < self.zone_count_x - 1:
               self.loadingzonex += 1
               self.x = ZONE_MARGIN
           else:
               self.x = self.screen_width - 1
       elif self.y < 0:
           if self.loadingzoney > 0:
               self.loadingzoney -= 1
               self.y = self.screen_height - ZONE_MARGIN
           else:
               self.y = 0
       elif self.y >= self.screen_height:
           if self.loadingzoney < self.zone_count_y - 1:
               self.loadingzoney += 1
               self.y = ZONE_MARGIN
           else:
               self.y = self.screen_height - 1

       self.rect.x = int(self.x)
       self.rect.y = int(self.y)


   def draw(self, screen, dt):
       if self.alive and not self.hiding:
           pygame.draw.rect(screen, self.color, self.rect)







       keys = pygame.key.get_pressed()
       moving = (keys[KEYBINDS['move_left']] or keys[KEYBINDS['move_right']] or
                 keys[KEYBINDS['move_up']] or keys[KEYBINDS['move_down']])
       drain = self.hunger_rate * (2 if moving else 1) * dt
       self.hunger = max(0, self.hunger - drain)

       # Slow down as hunger falls below 50
       if self.hunger <= 50:
           self.speed = PLAYER_BASE_SPEED - HUNGER_SPEED_MULTIPLIER * (50 - self.hunger)
       else:
           self.speed = PLAYER_BASE_SPEED




   def toggle_hiding(self, boxes):
       if self.hiding:
           self.hiding = False
           return

       for box in boxes:
           if box.can_hide(self):
               self.hiding = True
               self.x = box.x + (box.WIDTH - self.rect.width) / 2
               self.y = box.y + box.HEIGHT + (self.rect.height) / 2
               self.rect.x = int(self.x)
               self.rect.y = int(self.y)
               return


   def handle_movement(self, dt):
       if not self.alive:
           return

       keys = pygame.key.get_pressed()
       moving = (keys[KEYBINDS['move_left']] or keys[KEYBINDS['move_right']] or
                 keys[KEYBINDS['move_up']] or keys[KEYBINDS['move_down']])

       dx = 0
       dy = 0
       if keys[KEYBINDS['move_left']]:  dx -= 1
       if keys[KEYBINDS['move_right']]: dx += 1
       if keys[KEYBINDS['move_up']]:    dy -= 1
       if keys[KEYBINDS['move_down']]:  dy += 1

       if self.hiding:
           return

       # Normalise diagonal movement
       if dx != 0 and dy != 0:
           factor = 1 / math.sqrt(2)
           dx *= factor
           dy *= factor

       self.x += dx * self.speed * dt
       self.y += dy * self.speed * dt

       self.rect.x = int(self.x)
       self.rect.y = int(self.y)


   def loading_zones(self):
       # Place the entity ZONE_MARGIN pixels inside the new zone so that
       # reversing direction immediately never re-triggers the opposite edge.
       ZONE_MARGIN = 30

       if self.x < 0:
           if self.loadingzonex > 0:
               self.loadingzonex -= 1
               self.x = self.screen_width - ZONE_MARGIN
           else:
               self.x = 0
       elif self.x >= self.screen_width:
           if self.loadingzonex < self.zone_count_x - 1:
               self.loadingzonex += 1
               self.x = ZONE_MARGIN
           else:
               self.x = self.screen_width - 1
       elif self.y < 0:
           if self.loadingzoney > 0:
               self.loadingzoney -= 1
               self.y = self.screen_height - ZONE_MARGIN
           else:
               self.y = 0
       elif self.y >= self.screen_height:
           if self.loadingzoney < self.zone_count_y - 1:
               self.loadingzoney += 1
               self.y = ZONE_MARGIN
           else:
               self.y = self.screen_height - 1

       self.rect.x = int(self.x)
       self.rect.y = int(self.y)


   def draw(self, screen):
       if self.alive and not self.hiding:
           pygame.draw.rect(screen, self.color, self.rect)







