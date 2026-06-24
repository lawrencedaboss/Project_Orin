import random
import math
import pygame
from config import MONSTER_SPEED, MONSTER_WANDER_SPEED
from map_data import get_zone_doors, get_zone_grid, TILE_WALL

DESPAWN_ZONE_DISTANCE = 10
LEAVE_ZONE_DISTANCE   = 7
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

        self._leaving      = False
        self._leave_timer  = 0.0

        self._wander_vx    = 1.0
        self._wander_vy    = 0.0
        self._wander_timer = 0.0

        self._door_seek    = None  # (x, y) target when navigating to a door
        self._player_zone_x = 0
        self._player_zone_y = 0

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

    def _door_edge_pos(self, side):
        """Screen (x, y) at the midpoint of the given zone edge."""
        cx = self.screen_width  / 2
        cy = self.screen_height / 2
        m  = 24
        return {
            'west':  (m,                      cy),
            'east':  (self.screen_width - m,  cy),
            'north': (cx,                     m),
            'south': (cx, self.screen_height - m),
        }.get(side, (cx, cy))

    def _zone_has_door(self, zx, zy, side):
        return side in get_zone_doors(zx, zy)

    def _set_door_seek(self):
        """
        Pick the door in the current zone that leads closest to the player zone
        and set it as the navigation target.  Called when a crossing is blocked.
        """
        pzx, pzy = self._player_zone_x, self._player_zone_y
        doors = get_zone_doors(self.loading_zone_x, self.loading_zone_y)
        if not doors:
            self._door_seek = None
            return

        best_side = None
        best_dist = float('inf')
        for side in doors:
            if   side == 'east':  nzx, nzy = self.loading_zone_x + 1, self.loading_zone_y
            elif side == 'west':  nzx, nzy = self.loading_zone_x - 1, self.loading_zone_y
            elif side == 'south': nzx, nzy = self.loading_zone_x,     self.loading_zone_y + 1
            elif side == 'north': nzx, nzy = self.loading_zone_x,     self.loading_zone_y - 1
            else: continue
            dist = math.hypot(nzx - pzx, nzy - pzy)
            if dist < best_dist:
                best_dist = dist
                best_side = side

        self._door_seek = self._door_edge_pos(best_side) if best_side else None

    def _wall_avoid_force(self):
        """
        Return (fx, fy) avoidance nudge based on wall tiles ahead.
        Uses three forward feelers; pushes back from any wall hit.
        """
        grid = get_zone_grid(self.loading_zone_x, self.loading_zone_y)
        if not grid:
            return 0.0, 0.0

        rows = len(grid)
        cols = len(grid[0]) if rows else 1
        tile_w = self.screen_width  / cols
        tile_h = self.screen_height / rows

        vlen = math.sqrt(self._wander_vx ** 2 + self._wander_vy ** 2)
        if vlen < 0.001:
            return 0.0, 0.0
        nvx = self._wander_vx / vlen
        nvy = self._wander_vy / vlen

        ahead = 55
        perp  = 30
        feelers = [
            (nvx * ahead,                          nvy * ahead),
            (nvx * ahead * 0.6 - nvy * perp,  nvy * ahead * 0.6 + nvx * perp),
            (nvx * ahead * 0.6 + nvy * perp,  nvy * ahead * 0.6 - nvx * perp),
        ]

        avoid_x = avoid_y = 0.0
        for fdx, fdy in feelers:
            tx = int((self.x + fdx) / tile_w)
            ty = int((self.y + fdy) / tile_h)
            if 0 <= ty < rows and 0 <= tx < cols and grid[ty][tx] == TILE_WALL:
                avoid_x -= fdx
                avoid_y -= fdy

        alen = math.sqrt(avoid_x ** 2 + avoid_y ** 2)
        if alen > 0.001:
            scale = MONSTER_WANDER_SPEED * 0.8
            return (avoid_x / alen) * scale, (avoid_y / alen) * scale
        return 0.0, 0.0

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

        # Spawn at a doorway if one exists, else random position
        doors = get_zone_doors(spawn_x, spawn_y)
        if doors:
            self.x, self.y = self._door_edge_pos(random.choice(doors))
        else:
            self.x = random.randint(50, self.screen_width  - 50)
            self.y = random.randint(50, self.screen_height - 50)

        self.rect.x    = int(self.x)
        self.rect.y    = int(self.y)
        self.active    = True
        self._leaving  = False
        self._leave_timer = 0.0
        self._door_seek   = None
        self._pick_wander_direction()

    # ------------------------------------------------------------------ update

    def update(self, target_x, target_y, player_zone_x, player_zone_y, dt,
               hiding=False):
        # Store player zone so _cross_zones can access it without extra args
        self._player_zone_x = player_zone_x
        self._player_zone_y = player_zone_y

        if not self.active:
            self.respawn_timer -= dt
            if self.respawn_timer <= 0:
                self._spawn_near_player(player_zone_x, player_zone_y)
            return

        zone_dist = self._zone_distance(player_zone_x, player_zone_y)

        if zone_dist >= DESPAWN_ZONE_DISTANCE:
            self._deactivate()
            return

        if not self._leaving:
            if zone_dist >= LEAVE_ZONE_DISTANCE:
                self._leave_timer += dt
                if self._leave_timer >= 2.0:
                    self._leaving = True
            else:
                self._leave_timer = 0.0

        if self._leaving:
            self._move_flee_world_edge(dt)
            self._cross_zones(ignore_doors=True)
            return

        in_same_zone = (self.loading_zone_x == player_zone_x and
                        self.loading_zone_y == player_zone_y)

        if hiding or target_x is None or target_y is None:
            # Wander away from player zone
            dz_x = self.loading_zone_x - player_zone_x
            dz_y = self.loading_zone_y - player_zone_y
            dz_dist = math.sqrt(dz_x * dz_x + dz_y * dz_y)
            if dz_dist > 0:
                nx = dz_x / dz_dist
                ny = dz_y / dz_dist
                self._wander_vx, self._wander_vy = nx, ny
            else:
                self._move_wander(dt)
                self._cross_zones()
                return
            avoid_x, avoid_y = self._wall_avoid_force()
            self.x += (nx * MONSTER_WANDER_SPEED + avoid_x) * dt
            self.y += (ny * MONSTER_WANDER_SPEED + avoid_y) * dt

        elif in_same_zone:
            # Chase player with wall avoidance
            dx = target_x - self.x
            dy = target_y - self.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 1:
                nx = dx / dist
                ny = dy / dist
                self._wander_vx, self._wander_vy = nx, ny
                avoid_x, avoid_y = self._wall_avoid_force()
                self.x += (nx * MONSTER_SPEED + avoid_x) * dt
                self.y += (ny * MONSTER_SPEED + avoid_y) * dt

        else:
            # Navigate toward the player's zone via doors
            if self._door_seek is not None:
                sk_x, sk_y = self._door_seek
                ddx = sk_x - self.x
                ddy = sk_y - self.y
                ddist = math.sqrt(ddx ** 2 + ddy ** 2)
                if ddist < 40:
                    self._door_seek = None  # reached the door, let normal move take over
                else:
                    nx = ddx / ddist
                    ny = ddy / ddist
                    self._wander_vx, self._wander_vy = nx, ny
                    avoid_x, avoid_y = self._wall_avoid_force()
                    self.x += (nx * MONSTER_WANDER_SPEED + avoid_x) * dt
                    self.y += (ny * MONSTER_WANDER_SPEED + avoid_y) * dt
            else:
                dz_x = player_zone_x - self.loading_zone_x
                dz_y = player_zone_y - self.loading_zone_y
                dist = math.sqrt(dz_x * dz_x + dz_y * dz_y)
                nx = dz_x / dist
                ny = dz_y / dist
                self._wander_vx, self._wander_vy = nx, ny
                avoid_x, avoid_y = self._wall_avoid_force()
                self.x += (nx * MONSTER_WANDER_SPEED + avoid_x) * dt
                self.y += (ny * MONSTER_WANDER_SPEED + avoid_y) * dt

        self._cross_zones()

    # ------------------------------------------------------------------ movement helpers

    def _move_flee_world_edge(self, dt):
        """Move directly toward the nearest world edge to despawn."""
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

    def _cross_zones(self, ignore_doors=False):
        """
        Handle zone boundary crossings.
        Normal mode: only cross if destination zone has a door on the entry side;
        otherwise bounce and set a door-seek target so the monster routes around.
        Fleeing mode (ignore_doors=True): cross freely and despawn at world edge.
        """
        MARGIN = 24

        if self.x >= self.screen_width:
            new_zx = self.loading_zone_x + 1
            if new_zx < self.zone_count_x:
                if ignore_doors or self._zone_has_door(new_zx, self.loading_zone_y, 'west'):
                    self.loading_zone_x = new_zx
                    self.x, self.y = self._door_edge_pos('west') if not ignore_doors else (MARGIN, self.y)
                    self._wander_vx = abs(self._wander_vx)
                    self._door_seek = None
                else:
                    self.x = self.screen_width - MARGIN
                    self._wander_vx = -abs(self._wander_vx)
                    if self._door_seek is None:
                        self._set_door_seek()
            else:
                if self._leaving:
                    self._deactivate(); return
                self.x = self.screen_width - 1
                self._wander_vx = -abs(self._wander_vx)

        elif self.x < 0:
            new_zx = self.loading_zone_x - 1
            if new_zx >= 0:
                if ignore_doors or self._zone_has_door(new_zx, self.loading_zone_y, 'east'):
                    self.loading_zone_x = new_zx
                    self.x, self.y = self._door_edge_pos('east') if not ignore_doors else (self.screen_width - MARGIN, self.y)
                    self._wander_vx = -abs(self._wander_vx)
                    self._door_seek = None
                else:
                    self.x = MARGIN
                    self._wander_vx = abs(self._wander_vx)
                    if self._door_seek is None:
                        self._set_door_seek()
            else:
                if self._leaving:
                    self._deactivate(); return
                self.x = 0
                self._wander_vx = abs(self._wander_vx)

        if self.y >= self.screen_height:
            new_zy = self.loading_zone_y + 1
            if new_zy < self.zone_count_y:
                if ignore_doors or self._zone_has_door(self.loading_zone_x, new_zy, 'north'):
                    self.loading_zone_y = new_zy
                    self.x, self.y = self._door_edge_pos('north') if not ignore_doors else (self.x, MARGIN)
                    self._wander_vy = abs(self._wander_vy)
                    self._door_seek = None
                else:
                    self.y = self.screen_height - MARGIN
                    self._wander_vy = -abs(self._wander_vy)
                    if self._door_seek is None:
                        self._set_door_seek()
            else:
                if self._leaving:
                    self._deactivate(); return
                self.y = self.screen_height - 1
                self._wander_vy = -abs(self._wander_vy)

        elif self.y < 0:
            new_zy = self.loading_zone_y - 1
            if new_zy >= 0:
                if ignore_doors or self._zone_has_door(self.loading_zone_x, new_zy, 'south'):
                    self.loading_zone_y = new_zy
                    self.x, self.y = self._door_edge_pos('south') if not ignore_doors else (self.x, self.screen_height - MARGIN)
                    self._wander_vy = -abs(self._wander_vy)
                    self._door_seek = None
                else:
                    self.y = MARGIN
                    self._wander_vy = abs(self._wander_vy)
                    if self._door_seek is None:
                        self._set_door_seek()
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
        self._door_seek    = None
        self.respawn_timer = random.uniform(RESPAWN_TIME_MIN, RESPAWN_TIME_MAX)

    def _move_wander(self, dt):
        self._wander_timer -= dt
        if self._wander_timer <= 0:
            self._pick_wander_direction()
        avoid_x, avoid_y = self._wall_avoid_force()
        self.x += (self._wander_vx * MONSTER_WANDER_SPEED + avoid_x) * dt
        self.y += (self._wander_vy * MONSTER_WANDER_SPEED + avoid_y) * dt

    # ------------------------------------------------------------------ draw

    def draw(self, surface):
        if self.active:
            color = (180, 0, 220) if self._leaving else (0, 0, 255)
            pygame.draw.rect(surface, color, self.rect)
