"""
monster.py — Monster AI for Project Orin (simplified)
=======================================================

Behaviour (no state machine — just direct branches, checked every frame)
--------------------------------------------------------------------------
  1. Hiding / no visible target  -> wander AWAY from the player's zone
                                     (lets zone_dist grow so leaving can trigger)
  2. Same zone as player          -> chase directly, at MONSTER_SPEED
  3. Different zone                -> navigate toward the player's zone via doors

Leaving / despawn
------------------
  zone_dist >= LEAVE_ZONE_DISTANCE for LEAVE_DELAY seconds -> flee to the
  nearest world edge and despawn there.

Wall collision
--------------
  Feeler-based avoidance steers around walls ahead of time; a hard
  position rollback in _apply_move() guarantees the monster can never end
  up standing inside a wall tile, even at full chase speed.
"""

import random
import math
import pygame
from config import MONSTER_SPEED, MONSTER_WANDER_SPEED
from map_data import get_zone_doors, get_zone_grid, TILE_WALL

DESPAWN_ZONE_DISTANCE = 10
LEAVE_ZONE_DISTANCE   = 5
LEAVE_DELAY           = 0.5
RESPAWN_TIME_MIN      = 15
RESPAWN_TIME_MAX      = 30

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

        self.x = 0.0
        self.y = 0.0
        self.loading_zone_x = 0
        self.loading_zone_y = 0
        self.rect = pygame.Rect(0, 0, 32, 32)

        self.active        = False
        self.respawn_timer = random.uniform(RESPAWN_TIME_MIN, RESPAWN_TIME_MAX)

        self._leaving     = False
        self._leave_timer = 0.0

        self._wander_vx    = 1.0
        self._wander_vy    = 0.0
        self._wander_timer = 0.0
        self._escape_timer = 0.0   # >0 while committed to a stuck-escape heading

        self._door_seek      = None
        self._player_zone_x  = 0
        self._player_zone_y  = 0
        self._chasing        = False   # for draw() colour only
        self._engaged        = False   # True once it has actually gotten close

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _zone_distance(self, pzx, pzy):
        return math.sqrt((self.loading_zone_x - pzx) ** 2 +
                         (self.loading_zone_y - pzy) ** 2)

    def _pick_wander_direction(self):
        angle = random.uniform(0, 2 * math.pi)
        self._wander_vx    = math.cos(angle)
        self._wander_vy    = math.sin(angle)
        self._wander_timer = random.uniform(1.5, 3.5)

    def _door_edge_pos(self, side):
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
        pzx, pzy = self._player_zone_x, self._player_zone_y
        doors = get_zone_doors(self.loading_zone_x, self.loading_zone_y)
        if not doors:
            self._door_seek = None
            return
        best_side, best_dist = None, float('inf')
        for side in doors:
            if   side == 'east':  nzx, nzy = self.loading_zone_x + 1, self.loading_zone_y
            elif side == 'west':  nzx, nzy = self.loading_zone_x - 1, self.loading_zone_y
            elif side == 'south': nzx, nzy = self.loading_zone_x,     self.loading_zone_y + 1
            elif side == 'north': nzx, nzy = self.loading_zone_x,     self.loading_zone_y - 1
            else: continue
            dist = math.hypot(nzx - pzx, nzy - pzy)
            if dist < best_dist:
                best_dist, best_side = dist, side
        self._door_seek = self._door_edge_pos(best_side) if best_side else None

    # ---- wall collision ------------------------------------------------

    def _tile_at(self, px, py):
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

    def _in_wall(self, px, py):
        return self._tile_at(px + 16, py + 16) == TILE_WALL

    def _wall_avoid_force(self):
        vlen = math.sqrt(self._wander_vx ** 2 + self._wander_vy ** 2)
        if vlen < 0.001:
            return 0.0, 0.0
        nvx = self._wander_vx / vlen
        nvy = self._wander_vy / vlen

        ahead = 55
        perp  = 30
        feelers = [
            (nvx * ahead,                        nvy * ahead),
            (nvx * ahead * 0.6 - nvy * perp,  nvy * ahead * 0.6 + nvx * perp),
            (nvx * ahead * 0.6 + nvy * perp,  nvy * ahead * 0.6 - nvx * perp),
        ]

        avoid_x = avoid_y = 0.0
        for fdx, fdy in feelers:
            if self._tile_at(self.x + fdx, self.y + fdy) == TILE_WALL:
                avoid_x -= fdx
                avoid_y -= fdy

        alen = math.sqrt(avoid_x ** 2 + avoid_y ** 2)
        if alen > 0.001:
            scale = MONSTER_WANDER_SPEED * 0.8
            return (avoid_x / alen) * scale, (avoid_y / alen) * scale
        return 0.0, 0.0

    def _apply_move(self, dx, dy):
        """
        Move with hard wall rollback so the monster can't clip through walls.
        Tries the full move, then slides along whichever axis is open.
        If neither axis makes any actual progress, commits to a random
        escape heading for a short time (see _aim_or_escape) instead of
        silently freezing in place against the wall.
        """
        ox, oy = self.x, self.y
        nx, ny = self.x + dx, self.y + dy

        if not self._in_wall(nx, ny):
            self.x, self.y = nx, ny
            return

        moved = False
        if dx != 0 and not self._in_wall(nx, self.y):
            self.x = nx
            moved = True
        if dy != 0 and not self._in_wall(self.x, ny):
            self.y = ny
            moved = True

        if not moved or (self.x == ox and self.y == oy):
            self._pick_escape_direction()

    def _pick_escape_direction(self):
        """Commit to a random heading for a short time to break free of a stuck spot."""
        angle = random.uniform(0, 2 * math.pi)
        self._wander_vx    = math.cos(angle)
        self._wander_vy    = math.sin(angle)
        self._escape_timer = 0.8

    def _aim_or_escape(self, nx, ny, dt):
        """
        Returns the heading to actually steer with this frame: the freshly
        computed target-aim direction (nx, ny), unless an escape maneuver
        is still active, in which case that heading is kept so it has a
        real chance to run before being overridden again.
        """
        if self._escape_timer > 0:
            self._escape_timer -= dt
            return self._wander_vx, self._wander_vy
        self._wander_vx, self._wander_vy = nx, ny
        return nx, ny

    def _spawn_near_player(self, pzx, pzy):
        candidates = _SPAWN_OFFSETS[:]
        random.shuffle(candidates)
        spawn_x, spawn_y = pzx, pzy
        for dx, dy in candidates:
            cx, cy = pzx + dx, pzy + dy
            if 0 <= cx < self.zone_count_x and 0 <= cy < self.zone_count_y:
                if cx != pzx or cy != pzy:
                    spawn_x, spawn_y = cx, cy
                    break

        self.loading_zone_x = spawn_x
        self.loading_zone_y = spawn_y
        doors = get_zone_doors(spawn_x, spawn_y)
        if doors:
            self.x, self.y = self._door_edge_pos(random.choice(doors))
        else:
            self.x = random.randint(50, self.screen_width  - 50)
            self.y = random.randint(50, self.screen_height - 50)

        self.rect.x   = int(self.x)
        self.rect.y   = int(self.y)
        self.active   = True
        self._leaving = False
        self._leave_timer = 0.0
        self._door_seek    = None
        self._chasing      = False
        self._engaged      = False
        self._escape_timer = 0.0
        self._pick_wander_direction()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, target_x, target_y, player_zone_x, player_zone_y, dt,
               hiding=False):
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

        if zone_dist < LEAVE_ZONE_DISTANCE:
            self._engaged = True

        if not self._leaving:
            if self._engaged and zone_dist >= LEAVE_ZONE_DISTANCE:
                self._leave_timer += dt
                if self._leave_timer >= LEAVE_DELAY:
                    self._leaving = True
            else:
                self._leave_timer = 0.0

        if self._leaving:
            self._chasing = False
            self._move_flee_world_edge(dt)
            self._cross_zones(ignore_doors=True)
            return

        in_same_zone = (self.loading_zone_x == player_zone_x and
                        self.loading_zone_y == player_zone_y)

        if hiding or target_x is None or target_y is None:
            self._chasing = False
            # Wander away from the player's zone
            dz_x = self.loading_zone_x - player_zone_x
            dz_y = self.loading_zone_y - player_zone_y
            dz_dist = math.sqrt(dz_x * dz_x + dz_y * dz_y)
            if dz_dist > 0:
                nx, ny = dz_x / dz_dist, dz_y / dz_dist
            else:
                nx, ny = self._wander_vx, self._wander_vy
            mvx, mvy = self._aim_or_escape(nx, ny, dt)
            avoid_x, avoid_y = self._wall_avoid_force()
            self._apply_move(
                (mvx * MONSTER_WANDER_SPEED + avoid_x) * dt,
                (mvy * MONSTER_WANDER_SPEED + avoid_y) * dt,
            )

        elif in_same_zone:
            self._chasing = True
            dx = target_x - self.x
            dy = target_y - self.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 1:
                nx, ny = dx / dist, dy / dist
                mvx, mvy = self._aim_or_escape(nx, ny, dt)
                avoid_x, avoid_y = self._wall_avoid_force()
                self._apply_move(
                    (mvx * MONSTER_SPEED + avoid_x) * dt,
                    (mvy * MONSTER_SPEED + avoid_y) * dt,
                )

        else:
            self._chasing = False
            # Navigate toward the player's zone via doors
            if self._door_seek is not None:
                sk_x, sk_y = self._door_seek
                ddx = sk_x - self.x
                ddy = sk_y - self.y
                ddist = math.sqrt(ddx ** 2 + ddy ** 2)
                if ddist < 40:
                    self._door_seek = None
                else:
                    nx, ny = ddx / ddist, ddy / ddist
                    mvx, mvy = self._aim_or_escape(nx, ny, dt)
                    avoid_x, avoid_y = self._wall_avoid_force()
                    self._apply_move(
                        (mvx * MONSTER_WANDER_SPEED + avoid_x) * dt,
                        (mvy * MONSTER_WANDER_SPEED + avoid_y) * dt,
                    )
            else:
                dz_x = player_zone_x - self.loading_zone_x
                dz_y = player_zone_y - self.loading_zone_y
                dist = math.sqrt(dz_x * dz_x + dz_y * dz_y)
                nx, ny = dz_x / dist, dz_y / dist
                mvx, mvy = self._aim_or_escape(nx, ny, dt)
                avoid_x, avoid_y = self._wall_avoid_force()
                self._apply_move(
                    (mvx * MONSTER_WANDER_SPEED + avoid_x) * dt,
                    (mvy * MONSTER_WANDER_SPEED + avoid_y) * dt,
                )

        self._cross_zones()

    # ------------------------------------------------------------------
    # Movement helpers
    # ------------------------------------------------------------------

    def _move_flee_world_edge(self, dt):
        dl = self.loading_zone_x
        dr = (self.zone_count_x - 1) - self.loading_zone_x
        dt_ = self.loading_zone_y
        db  = (self.zone_count_y - 1) - self.loading_zone_y
        m   = min(dl, dr, dt_, db)
        if   m == dl:  self.x -= MONSTER_WANDER_SPEED * dt
        elif m == dr:  self.x += MONSTER_WANDER_SPEED * dt
        elif m == dt_: self.y -= MONSTER_WANDER_SPEED * dt
        else:          self.y += MONSTER_WANDER_SPEED * dt

    def _cross_zones(self, ignore_doors=False):
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
                if self._leaving: self._deactivate(); return
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
                if self._leaving: self._deactivate(); return
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
                if self._leaving: self._deactivate(); return
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
                if self._leaving: self._deactivate(); return
                self.y = 0
                self._wander_vy = abs(self._wander_vy)

        self.rect.x = int(self.x)
        self.rect.y = int(self.y)

    def _deactivate(self):
        self.active        = False
        self._leaving      = False
        self._leave_timer  = 0.0
        self._door_seek    = None
        self._chasing      = False
        self.respawn_timer = random.uniform(RESPAWN_TIME_MIN, RESPAWN_TIME_MAX)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, surface):
        if not self.active:
            return
        if self._leaving:
            color = (180, 0, 220)
        elif self._chasing:
            color = (220, 30, 30)
        else:
            color = (0, 0, 255)
        pygame.draw.rect(surface, color, self.rect)
