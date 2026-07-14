import pygame
from config import (SCREEN_WIDTH, SCREEN_HEIGHT, KEYBINDS)
from sounds import MUSIC
from display_scale import present

class PauseScreen:
   def __init__(self):
       self.title_font = pygame.font.SysFont('Arial', 64)
       self.text_font = pygame.font.SysFont('Arial', 24)
       self.small_font = pygame.font.SysFont('Arial', 18)
       self.title_surface = self.title_font.render("paused", True, (255, 255, 255))
       self.resume_surface = self.text_font.render("space: resume", True, (220, 220, 220))
       self.quit_surface = self.text_font.render("esc/q: quit", True, (220, 220, 220))
       self.keybind_surface = self.text_font.render("k: keybinds", True, (220, 220, 220))

   def show_keybind_menu(self, screen, clock):
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
           panel.fill((30, 40, 80, 250))
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
           present(screen)

   def _save_keybind(self, action, key):
       import json
       try:
           with open('config.json', 'r') as f:
               config = json.load(f)
           key_name = pygame.key.name(key).lower()
           config['keybinds'][action] = key_name
           with open('config.json', 'w') as f:
               json.dump(config, f, indent=2)
       except:
           pass

   def rebind_key(self, action, screen, clock):
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
           present(screen)

   def run(self, screen, clock):
       while True:
           dt = clock.tick(60) / 1000.0
           MUSIC.update(dt)
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
           present(screen)
