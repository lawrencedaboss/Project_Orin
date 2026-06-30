"""
monster.py — Monster AI for Project Orin
=========================================

States
------
  PATROL  — far from player; wanders randomly in current zone
  ALERT   — player zone detected within range; routing through doors toward it
  CHASE   — same zone, player visible; actively hunting (speed ramps up)
  SEARCH  — player vanished from same zone (crossed out without hiding);
             goes to last-known pixel position, sweeps area briefly

Hiding handling (separate from state machine)
---------------------------------------------
  When the player is hiding the state machine is bypassed entirely.
  The monster wanders *away* from the player zone — matching the original
  behaviour that let zone_dist grow large enough to trigger leaving.

Wall collision
--------------
  Feeler-based avoidance steers away from approaching walls.
  Hard position rollback prevents passing through a wall that was missed
  by the feelers (important at higher chase speeds).

Leaving / despawn
-----------------
  When zone_dist >= LEAVE_ZONE_DISTANCE for 0.5 seconds the
  monster sets _leaving=True and flees toward the nearest world edge via
  free zone crossing, eventually deactivating at the map boundary.
"""

import random
import math
import pygame
from config import MONSTER_SPEED, MONSTER_WANDER_SPEED
from map_data import get_zone_doors, get_zone_grid, TILE_WALL

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
DESPAWN_ZONE_DISTANCE = 10
LEAVE_ZONE_DISTANCE   = 5
RESPAWN_TIME_MIN      = 15
RESPAWN_TIME_MAX      = 30

ALERT_ZONE_DIST   = 5      # zone radius at which monster enters ALERT
CHASE_SPEED_MAX   = 1.35   # top speed multiplier during a chase
CHASE_SPEED_RATE  = 0.10   # how fast the multiplier climbs per second
SEARCH_DURATION   = 7.0    # seconds to sweep last-known area before giving up
SEARCH_RADIUS     = 80     # pixel radius to wander around the search anchor

PREDICT_T     = 0.15   # seconds ahead to aim during chase
PREDICT_ALPHA = 0.25   # smoothing factor for player velocity estimate

# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------
STATE_PATROL = 'patrol'
STATE_ALERT  = 'alert'
STATE_CHASE  = 'chase'
STATE_SEARCH = 'search'

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

        self._door_seek     = None
        self._player_zone_x = 0
        self._player_zone_y = 0

        # State machine
        self._state = STATE_PATROL

        # Last-known position (updated whenever player is visible in same zone)
        self._last_known_x      = None
        self._last_known_y      = None
        self._last_known_zone_x = None
        self._last_known_zone_y = None

        # Chase ramp
        self._chase_speed_mult = 1.0

        # Search sweep
        self._search_timer    = 0.0
        self._search_anchor_x = 0.0
        self._search_anchor_y = 0.0

        # Player velocity prediction (for chase look-ahead)
        self._prev_target_x = None
        self._prev_target_y = None
        self._pred_dx       = 0.0
        self._pred_dy       = 0.0

    # =========================================================================
    # Helpers
    # =========================================================================

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

    # ---- wall helpers -------------------------------------------------------

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

    def _in_wall(self, px, py):
        return self._tile_at(px + 16, py + 16) == TILE_WALL  # test rect centre

    def _wall_avoid_force(self, speed_scale=1.0):
        """
        Three-feeler wall avoidance.  *speed_scale* stretches feeler length
        so faster movement looks further ahead (important during chase).
        """
        vlen = math.sqrt(self._wander_vx ** 2 + self._wander_vy ** 2)
        if vlen < 0.001:
            return 0.0, 0.0
        nvx = self._wander_vx / vlen
        nvy = self._wander_vy / vlen

        ahead = max(40, 55 * speed_scale)
        perp  = 28
        feelers = [
            (nvx * ahead,                         nvy * ahead),
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
        Apply (dx, dy) pixel delta with hard wall rollback.
        Tries full move, then axis-separated fallbacks.
        """
        nx, ny = self.x + dx, self.y + dy
        # Full move
        if not self._in_wall(nx, ny):
            self.x, self.y = nx, ny
            return
        # Try x-only
        if not self._in_wall(nx, self.y):
            self.x = nx
            self._wander_vy = -self._wander_vy
            return
        # Try y-only
        if not self._in_wall(self.x, ny):
            self.y = ny
            self._wander_vx = -self._wander_vx
            return
        # Fully blocked — pick a new direction next tick
        self._pick_wander_direction()

    # =========================================================================
    # Movement helpers
    # =========================================================================

    def _move_wander(self, dt):
        self._wander_timer -= dt
        if self._wander_timer <= 0:
            self._pick_wander_direction()
        avoid_x, avoid_y = self._wall_avoid_force()
        spd = MONSTER_WANDER_SPEED
        self._apply_move(
            (self._wander_vx * spd + avoid_x) * dt,
            (self._wander_vy * spd + avoid_y) * dt,
        )

    def _move_toward_zone(self, dt, target_zone_x, target_zone_y):
        """
        Navigate toward a target zone via door waypoints.
        Used by ALERT and SEARCH (when the last-known zone differs).
        """
        if self._door_seek is not None:
            sk_x, sk_y = self._door_seek
            ddx = sk_x - self.x
            ddy = sk_y - self.y
            ddist = math.sqrt(ddx ** 2 + ddy ** 2)
            if ddist < 40:
                self._door_seek = None
            else:
                nx, ny = ddx / ddist, ddy / ddist
                self._wander_vx, self._wander_vy = nx, ny
                avoid_x, avoid_y = self._wall_avoid_force()
                spd = MONSTER_WANDER_SPEED
                self._apply_move(
                    (nx * spd + avoid_x) * dt,
                    (ny * spd + avoid_y) * dt,
                )
        else:
            dz_x = target_zone_x - self.loading_zone_x
            dz_y = target_zone_y - self.loading_zone_y
            dzlen = math.sqrt(dz_x ** 2 + dz_y ** 2)
            if dzlen < 0.001:
                self._move_wander(dt)
                return
            nx, ny = dz_x / dzlen, dz_y / dzlen
            self._wander_vx, self._wander_vy = nx, ny
            avoid_x, avoid_y = self._wall_avoid_force()
            spd = MONSTER_WANDER_SPEED
            self._apply_move(
                (nx * spd + avoid_x) * dt,
                (ny * spd + avoid_y) * dt,
            )

    def _move_chase(self, target_x, target_y, dt):
        """Chase with speed ramp, movement prediction, and wall rollback."""
        self._chase_speed_mult = min(
            CHASE_SPEED_MAX,
            self._chase_speed_mult + CHASE_SPEED_RATE * dt
        )
        spd = MONSTER_SPEED * self._chase_speed_mult

        # Aim slightly ahead of the player's estimated position
        px = max(0, min(target_x + self._pred_dx * PREDICT_T, self.screen_width  - 1))
        py = max(0, min(target_y + self._pred_dy * PREDICT_T, self.screen_height - 1))

        dx   = px - self.x
        dy   = py - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 1:
            nx, ny = dx / dist, dy / dist
            self._wander_vx, self._wander_vy = nx, ny
            avoid_x, avoid_y = self._wall_avoid_force(speed_scale=self._chase_speed_mult)
            self._apply_move(
                (nx * spd + avoid_x) * dt,
                (ny * spd + avoid_y) * dt,
            )

    def _move_search(self, dt):
        """
        Sweep the last-known pixel area.
        If the last-known zone is different, navigate zone-by-zone first.
        """
        if self._last_known_zone_x is None:
            self._move_wander(dt)
            return
        in_target = (self.loading_zone_x == self._last_known_zone_x and
                     self.loading_zone_y == self._last_known_zone_y)
        if in_target:
            ax, ay = self._search_anchor_x, self._search_anchor_y
            ddx = ax - self.x
            ddy = ay - self.y
            dist = math.sqrt(ddx ** 2 + ddy ** 2)
            if dist > SEARCH_RADIUS * 0.5:
                nx, ny = ddx / dist, ddy / dist
                self._wander_vx, self._wander_vy = nx, ny
                avoid_x, avoid_y = self._wall_avoid_force()
                spd = MONSTER_WANDER_SPEED * 1.1
                self._apply_move(
                    (nx * spd + avoid_x) * dt,
                    (ny * spd + avoid_y) * dt,
                )
            else:
                # At anchor — wander with spring back
                self._move_wander(dt)
                pull_x = ax - self.x
                pull_y = ay - self.y
                pull_d = math.sqrt(pull_x ** 2 + pull_y ** 2)
                if pull_d > SEARCH_RADIUS * 1.5:
                    k = (pull_d - SEARCH_RADIUS) / pull_d * 0.3
                    self.x += pull_x * k
                    self.y += pull_y * k
        else:
            self._move_toward_zone(
                dt, self._last_known_zone_x, self._last_known_zone_y)

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

    # =========================================================================
    # Zone crossing
    # =========================================================================

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

    # =========================================================================
    # Deactivate / spawn
    # =========================================================================

    def _deactivate(self):
        self.active        = False
        self._leaving      = False
        self._leave_timer  = 0.0
        self._door_seek    = None
        self._state        = STATE_PATROL
        self.respawn_timer = random.uniform(RESPAWN_TIME_MIN, RESPAWN_TIME_MAX)

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

        self.rect.x = int(self.x)
        self.rect.y = int(self.y)
        self.active        = True
        self._leaving      = False
        self._leave_timer  = 0.0
        self._door_seek    = None
        self._state        = STATE_PATROL
        self._last_known_x = None
        self._last_known_y = None
        self._last_known_zone_x = None
        self._last_known_zone_y = None
        self._chase_speed_mult = 1.0
        self._search_timer = 0.0
        self._prev_target_x = None
        self._prev_target_y = None
        self._pred_dx = 0.0
        self._pred_dy = 0.0
        self._pick_wander_direction()

    # =========================================================================
    # Main update
    # =========================================================================

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

        # ---- Leaving countdown ----
        if not self._leaving:
            if zone_dist >= LEAVE_ZONE_DISTANCE:
                self._leave_timer += dt
                if self._leave_timer >= 0.5:
                    self._leaving = True
            else:
                self._leave_timer = 0.0

        if self._leaving:
            self._move_flee_world_edge(dt)
            self._cross_zones(ignore_doors=True)
            return

        # ---- Update player velocity estimate (used in chase prediction) ----
        if target_x is not None and self._prev_target_x is not None:
            raw_vx = (target_x - self._prev_target_x) / max(dt, 0.001)
            raw_vy = (target_y - self._prev_target_y) / max(dt, 0.001)
            self._pred_dx += PREDICT_ALPHA * (raw_vx - self._pred_dx)
            self._pred_dy += PREDICT_ALPHA * (raw_vy - self._pred_dy)
        self._prev_target_x = target_x
        self._prev_target_y = target_y

        in_same_zone   = (self.loading_zone_x == player_zone_x and
                          self.loading_zone_y == player_zone_y)
        player_visible = (in_same_zone and not hiding and
                          target_x is not None and target_y is not None)

        # ---- When player is hiding: wander AWAY from player zone ----
        # This mirrors the original behaviour and lets zone_dist grow
        # naturally so the leaving trigger can fire.
        if hiding:
            dz_x = self.loading_zone_x - player_zone_x
            dz_y = self.loading_zone_y - player_zone_y
            dz_dist = math.sqrt(dz_x * dz_x + dz_y * dz_y)
            if dz_dist > 0:
                nx = dz_x / dz_dist
                ny = dz_y / dz_dist
                self._wander_vx, self._wander_vy = nx, ny
            avoid_x, avoid_y = self._wall_avoid_force()
            self._apply_move(
                (self._wander_vx * MONSTER_WANDER_SPEED + avoid_x) * dt,
                (self._wander_vy * MONSTER_WANDER_SPEED + avoid_y) * dt,
            )
            # Hiding resets state so a fresh chase starts when unhiding
            self._state = STATE_PATROL
            self._cross_zones()
            return

        # ---- State machine (player NOT hiding) ----

        # Update last-known position when player is visible
        if player_visible:
            self._last_known_x      = target_x
            self._last_known_y      = target_y
            self._last_known_zone_x = player_zone_x
            self._last_known_zone_y = player_zone_y

        # Transitions
        if self._state == STATE_PATROL:
            if zone_dist < ALERT_ZONE_DIST:
                self._state = STATE_ALERT

        elif self._state == STATE_ALERT:
            if player_visible:
                self._state            = STATE_CHASE
                self._chase_speed_mult = 1.0
            elif zone_dist >= ALERT_ZONE_DIST:
                self._state = STATE_PATROL

        elif self._state == STATE_CHASE:
            if not player_visible:
                # Player left zone (not hiding — handled above)
                self._state        = STATE_SEARCH
                self._search_timer = SEARCH_DURATION
                self._search_anchor_x = self._last_known_x or self.x
                self._search_anchor_y = self._last_known_y or self.y

        elif self._state == STATE_SEARCH:
            if player_visible:
                self._state            = STATE_CHASE
                self._chase_speed_mult = 1.1  # already alerted — faster ramp start
            else:
                self._search_timer -= dt
                if self._search_timer <= 0:
                    self._state = STATE_PATROL if zone_dist >= ALERT_ZONE_DIST else STATE_ALERT

        # Behaviours
        if self._state == STATE_PATROL:
            self._move_wander(dt)

        elif self._state == STATE_ALERT:
            self._move_toward_zone(dt, player_zone_x, player_zone_y)

        elif self._state == STATE_CHASE:
            self._move_chase(target_x, target_y, dt)

        elif self._state == STATE_SEARCH:
            self._move_search(dt)

        self._cross_zones()

    # =========================================================================
    # Draw
    # =========================================================================

    def draw(self, surface):
        if not self.active:
            return
        if self._leaving:
            color = (80, 0, 140)
        elif self._state == STATE_CHASE:
            color = (220, 30, 30)
        elif self._state == STATE_SEARCH:
            color = (160, 60, 220)
        elif self._state == STATE_ALERT:
            color = (200, 120, 0)
        else:
            color = (40, 60, 200)
        pygame.draw.rect(surface, color, self.rect)
