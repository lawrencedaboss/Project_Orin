import pygame


class TitleScreen:
   def __init__(self):
       self.title_font = pygame.font.SysFont('Arial', 72, bold=True)
       self.subtitle_font = pygame.font.SysFont('Arial', 28)
       self.prompt_font = pygame.font.SysFont('Arial', 24)

       self.title_surface = self.title_font.render('Project Orin', True, (235, 230, 210))
       self.subtitle_surface = self.subtitle_font.render(
           'Survive the zones, collect objects, and hide from the monster.', True, (200, 200, 200))
       self.prompt_surface = self.prompt_font.render('space: start  |  esc/q: quit', True, (200, 200, 200))
       self.tip_surface = self.prompt_font.render(
           'Use arrow keys to move. Press H to hide in a collected box.', True, (180, 180, 180))

   def run(self, screen, clock) -> bool:
       '''
       Blocks until the player presses SPACE or quits.
       Returns True if the game should start, False if the window was closed.
       '''
       while True:
           clock.tick(60)
           for event in pygame.event.get():
               if event.type == pygame.QUIT:
                   return False
               if event.type == pygame.KEYDOWN:
                   if event.key == pygame.K_SPACE:
                       return True
                   if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                       return False

           screen.fill((18, 24, 42))
           overlay = pygame.Surface((screen.get_width() - 120, screen.get_height() - 120), pygame.SRCALPHA)
           overlay.fill((32, 42, 70, 220))
           screen.blit(overlay, (60, 60))

           width = screen.get_width()
           screen.blit(self.title_surface, (width // 2 - self.title_surface.get_width() // 2, 140))
           screen.blit(self.subtitle_surface, (width // 2 - self.subtitle_surface.get_width() // 2, 240))
           screen.blit(self.prompt_surface, (width // 2 - self.prompt_surface.get_width() // 2, 320))
           screen.blit(self.tip_surface, (width // 2 - self.tip_surface.get_width() // 2, 360))

           pygame.display.flip()
