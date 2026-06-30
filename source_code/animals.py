import pygame
import random
import math
from config import ANIMAL_SPEED, ANIMAL_WANDER_INTERVAL_MIN, ANIMAL_WANDER_INTERVAL_MAX
from map_data import get_zone_grid, TILE_WALL


class Animal:
    def __init__(self, loading_zone_x, loading_zone_y,
                 screen_width=800, screen_height=600,
                 zone_count_x=20, zone_count_y=20):
        self.screen_width  = screen_width
        self.screen_height = screen_height
        self.zone_count_x  = zone_count_x
        self.zone_count_y  = zone_count_y

        self.loading_zone_x = random.randint(0, self.zone_count_x - 1)
        self.loading_zone_y = random.randint(0, self.zone_count_y - 1)

        self.x = random.randint(50, self.screen_width  - 50)
        self.y = random.randint(50, self.screen_height - 50)

        self.speed = ANIMAL_SPEED
        self.rect  = pygame.Rect(int(self.x), int(self.y), 16, 16)

        self.targetx = random.randint(50, self.screen_width  - 50)
        self.targety = random.randint(50, self.screen_height - 50)

        self.wander_timer    = 0.0
        self.wander_interval = random.uniform(
            ANIMAL_WANDER_INTERVAL_MIN, ANIMAL_WANDER_INTERVAL_MAX)

        # Current normalised movement direction (used by wall avoidance)
        self._dir_x = 0.0
        self._dir_y = 0.0

    # ------------------------------------------------------------------
    # Wall helpers
    # ------------------------------------------------------------------

    def _tile_at(self, px, py):
        """Return the tile value at pixel position (px, py), or 0 if clear."""
        grid = get_zone_grid(self.loading_zone_x, self.loading_zone_y)
        if not grid:
            return 0
        rows   = len(grid)
        cols   = len(grid[0]) if rows else 1
        tile_w = self.screen_width  / cols
        tile_h = self.screen_height / rows
        tx = int(px / tile_w)
        ty = int(py / tile_h)
        if 0 <= ty < rows and 0 <= tx < cols:
            return grid[ty][tx]
        return 0

    def _wall_avoid_force(self):
        """
        Three-feeler wall avoidance; returns (fx, fy) steering force.
        Feelers are cast ahead in the current movement direction.
        """
        vlen = math.sqrt(self._dir_x ** 2 + self._dir_y ** 2)
        if vlen < 0.001:
            return 0.0, 0.0
        nx = self._dir_x / vlen
        ny = self._dir_y / vlen

        ahead = 35
        perp  = 20
        feelers = [
            (nx * ahead,                      ny * ahead),
            (nx * ahead * 0.6 - ny * perp,   ny * ahead * 0.6 + nx * perp),
            (nx * ahead * 0.6 + ny * perp,   ny * ahead * 0.6 - nx * perp),
        ]

        avoid_x = avoid_y = 0.0
        for fdx, fdy in feelers:
            if self._tile_at(self.x + fdx, self.y + fdy) == TILE_WALL:
                avoid_x -= fdx
                avoid_y -= fdy

        alen = math.sqrt(avoid_x ** 2 + avoid_y ** 2)
        if alen > 0.001:
            scale = self.speed * 0.9
            return (avoid_x / alen) * scale, (avoid_y / alen) * scale
        return 0.0, 0.0

    def _pick_open_target(self):
        """Pick a random target; retry if it lands inside a wall tile."""
        for _ in range(8):
            tx = random.randint(50, self.screen_width  - 50)
            ty = random.randint(50, self.screen_height - 50)
            if self._tile_at(tx, ty) != TILE_WALL:
                return tx, ty
        return (self.screen_width // 2, self.screen_height // 2)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt):
        self.wander_timer += dt

        if self.wander_timer >= self.wander_interval:
            self.targetx, self.targety = self._pick_open_target()
            self.wander_timer    = 0.0
            self.wander_interval = random.uniform(
                ANIMAL_WANDER_INTERVAL_MIN, ANIMAL_WANDER_INTERVAL_MAX)

        dif_x = self.targetx - self.x
        dif_y = self.targety - self.y
        dist  = math.sqrt(dif_x ** 2 + dif_y ** 2)

        if dist > 10:
            # Normalised direction toward target
            nx = dif_x / dist
            ny = dif_y / dist

            # Randomly choose axis (original jittery feel)
            if random.random() < abs(nx) / (abs(nx) + abs(ny) + 1e-9):
                self._dir_x, self._dir_y = nx, 0.0
            else:
                self._dir_x, self._dir_y = 0.0, ny

            avoid_x, avoid_y = self._wall_avoid_force()

            new_x = self.x + (self._dir_x * self.speed + avoid_x) * dt
            new_y = self.y + (self._dir_y * self.speed + avoid_y) * dt

            # Only apply movement if destination is not a wall
            if self._tile_at(new_x, self.y) != TILE_WALL:
                self.x = new_x
            else:
                # Wall hit on X — jog toward a new target
                self.targetx, self.targety = self._pick_open_target()

            if self._tile_at(self.x, new_y) != TILE_WALL:
                self.y = new_y
            else:
                self.targetx, self.targety = self._pick_open_target()

        # Zone crossing (unchanged behaviour)
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

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, surface):
        pygame.draw.rect(surface, (125, 100, 10), self.rect)
