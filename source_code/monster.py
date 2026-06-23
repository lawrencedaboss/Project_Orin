import random
import math
import pygame
from config import MONSTER_SPEED, MONSTER_WANDER_SPEED

DESPAWN_ZONE_DISTANCE = 10   # hard cap — instantly deactivate beyond this
LEAVE_ZONE_DISTANCE   = 7    # monster actively retreats once it exceeds this
RESPAWN_TIME_MIN = 15
RESPAWN_TIME_MAX = 30

_SPAWN_OFFSETS = [
    (dx, dy)
    for dx in range(-8, 9)
    for dy in range(-8, 9)
    if 6.0 <= math.sqrt(dx * dx + dy * dy) <= 7.0
]


class Monster:
    def __init__(self, screen_width=1000, screen_height=800,
                 zone_count_x=20, zone_count_y=20):
        self.screen_width  = screen_width
        self.screen_height = screen_height
        self.zone_count_x  = zone_count_x
        self.zone_count_y  = zone_count_y

        self.x = 0
        self.y = 0
        self.loading_zone_x = 0
        self.loading_zone_y = 0
        self.rect = pygame.Rect(self.x, self.y, 32, 32)

        self.active        = False
        self.respawn_timer = random.uniform(RESPAWN_TIME_MIN, RESPAWN_TIME_MAX)

        # Leaving state: once triggered the monster flees to the world edge
        self._leaving       = False
        self._leave_timer   = 0.0   # how long since zone-dist exceeded threshold

        self._wander_vx    = 1.0
        self._wander_vy    = 0.0
        self._wander_timer = 0.0

    # ------------------------------------------------------------------ helpers

    def _zone_distance(self, player_zone_x, player_zone_y):
        dx = self.loading_zone_x - player_zone_x
        dy = self.loading_zone_y - player_zone_y
        return math.sqrt(dx * dx + dy * dy)

    def _pick_wander_direction(self):
        angle = random.uniform(0, 2 * math.pi)
        self._wander_vx    = math.cos(angle)
        self._wander_vy    = math.sin(angle)
        self._wander_timer = random.uniform(1.5, 3.5)

    def _spawn_near_player(self, player_zone_x, player_zone_y):
        candidates = _SPAWN_OFFSETS[:]
        random.shuffle(candidates)
        spawn_x, spawn_y = player_zone_x, player_zone_y
        for dx, dy in candidates:
            cx = player_zone_x + dx
            cy = player_zone_y + dy
            if 0 <= cx < self.zone_count_x and 0 <= cy < self.zone_count_y:
                if cx != player_zone_x or cy != player_zone_y:
                    spawn_x, spawn_y = cx, cy
                    break

        self.loading_zone_x = spawn_x
        self.loading_zone_y = spawn_y
        self.x = random.randint(50, self.screen_width  - 50)
        self.y = random.randint(50, self.screen_height - 50)
        self.rect.x = int(self.x)
        self.rect.y = int(self.y)
        self.active       = True
        self._leaving     = False
        self._leave_timer = 0.0
        self._pick_wander_direction()

    # ------------------------------------------------------------------ update

    def update(self, target_x, target_y, player_zone_x, player_zone_y, dt,
               hiding=False):
        # --- Inactive: count down respawn ---
        if not self.active:
            self.respawn_timer -= dt
            if self.respawn_timer <= 0:
                self._spawn_near_player(player_zone_x, player_zone_y)
            return

        zone_dist = self._zone_distance(player_zone_x, player_zone_y)

        # --- Hard despawn cap ---
        if zone_dist >= DESPAWN_ZONE_DISTANCE:
            self._deactivate()
            return

        # --- Check if monster should start leaving ---
        # Triggered when:  zone_dist > LEAVE_ZONE_DISTANCE  OR  player is hiding
        # Once leaving it keeps fleeing until it despawns at the world edge.
        if not self._leaving:
            if zone_dist >= LEAVE_ZONE_DISTANCE:
                self._leave_timer += dt
                if self._leave_timer >= 2.0:   # must stay far for 2 s before committing
                    self._leaving = True
            else:
                self._leave_timer = 0.0        # reset timer if player gets close again

        if self._leaving:
            self._move_flee_world_edge(dt)
            self._cross_zones()
            return

        # --- Normal behaviour ---
        in_same_zone = (self.loading_zone_x == player_zone_x and
                        self.loading_zone_y == player_zone_y)

        if hiding or target_x is None or target_y is None:
            dz_x = self.loading_zone_x - player_zone_x
            dz_y = self.loading_zone_y - player_zone_y
            dz_dist = math.sqrt(dz_x * dz_x + dz_y * dz_y)
            if dz_dist > 0:
                nx = dz_x / dz_dist
                ny = dz_y / dz_dist
                self.x += nx * MONSTER_WANDER_SPEED * dt
                self.y += ny * MONSTER_WANDER_SPEED * dt
            else:
                cx = self.screen_width  / 2
                cy = self.screen_height / 2
                ex, ey = self.x - cx, self.y - cy
                ed = math.sqrt(ex * ex + ey * ey)
                if ed > 1:
                    self.x += (ex / ed) * MONSTER_WANDER_SPEED * dt
                    self.y += (ey / ed) * MONSTER_WANDER_SPEED * dt
                else:
                    self._pick_wander_direction()
                    self._move_wander(dt)

        elif in_same_zone:
            dx = target_x - self.x
            dy = target_y - self.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 1:
                self.x += (dx / dist) * MONSTER_SPEED * dt
                self.y += (dy / dist) * MONSTER_SPEED * dt

        else:
            dz_x = player_zone_x - self.loading_zone_x
            dz_y = player_zone_y - self.loading_zone_y
            dist = math.sqrt(dz_x * dz_x + dz_y * dz_y)
            nx = dz_x / dist
            ny = dz_y / dist
            self.x += nx * MONSTER_WANDER_SPEED * dt
            self.y += ny * MONSTER_WANDER_SPEED * dt

        self._cross_zones()

    # ------------------------------------------------------------------ movement helpers

    def _move_flee_world_edge(self, dt):
        """Move directly toward the nearest world edge to leave the map."""
        # Pick closest edge: left=0, right=max_x, top=0, bottom=max_y
        dist_left   = self.loading_zone_x
        dist_right  = (self.zone_count_x - 1) - self.loading_zone_x
        dist_top    = self.loading_zone_y
        dist_bottom = (self.zone_count_y - 1) - self.loading_zone_y
        min_dist    = min(dist_left, dist_right, dist_top, dist_bottom)

        if min_dist == dist_left:
            self.x -= MONSTER_WANDER_SPEED * dt
        elif min_dist == dist_right:
            self.x += MONSTER_WANDER_SPEED * dt
        elif min_dist == dist_top:
            self.y -= MONSTER_WANDER_SPEED * dt
        else:
            self.y += MONSTER_WANDER_SPEED * dt

    def _cross_zones(self):
        """Handle zone boundary crossings and world-edge despawn when leaving."""
        ZONE_MARGIN = 30

        if self.x >= self.screen_width:
            if self.loading_zone_x < self.zone_count_x - 1:
                self.loading_zone_x += 1
                self.x = ZONE_MARGIN
                self._wander_vx = abs(self._wander_vx)
            else:
                # Hit world edge while leaving — despawn
                if self._leaving:
                    self._deactivate(); return
                self.x = self.screen_width - 1
                self._wander_vx = -abs(self._wander_vx)
        elif self.x < 0:
            if self.loading_zone_x > 0:
                self.loading_zone_x -= 1
                self.x = self.screen_width - ZONE_MARGIN
                self._wander_vx = -abs(self._wander_vx)
            else:
                if self._leaving:
                    self._deactivate(); return
                self.x = 0
                self._wander_vx = abs(self._wander_vx)

        if self.y >= self.screen_height:
            if self.loading_zone_y < self.zone_count_y - 1:
                self.loading_zone_y += 1
                self.y = ZONE_MARGIN
                self._wander_vy = abs(self._wander_vy)
            else:
                if self._leaving:
                    self._deactivate(); return
                self.y = self.screen_height - 1
                self._wander_vy = -abs(self._wander_vy)
        elif self.y < 0:
            if self.loading_zone_y > 0:
                self.loading_zone_y -= 1
                self.y = self.screen_height - ZONE_MARGIN
                self._wander_vy = -abs(self._wander_vy)
            else:
                if self._leaving:
                    self._deactivate(); return
                self.y = 0
                self._wander_vy = abs(self._wander_vy)

        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

    def _deactivate(self):
        self.active        = False
        self._leaving      = False
        self._leave_timer  = 0.0
        self.respawn_timer = random.uniform(RESPAWN_TIME_MIN, RESPAWN_TIME_MAX)

    def _move_wander(self, dt):
        self._wander_timer -= dt
        if self._wander_timer <= 0:
            self._pick_wander_direction()
        self.x += self._wander_vx * MONSTER_WANDER_SPEED * dt
        self.y += self._wander_vy * MONSTER_WANDER_SPEED * dt

    # ------------------------------------------------------------------ draw

    def draw(self, surface):
        if self.active:
            color = (180, 0, 220) if self._leaving else (0, 0, 255)
            pygame.draw.rect(surface, color, self.rect)