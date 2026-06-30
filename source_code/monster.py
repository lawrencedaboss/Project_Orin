"""
monster.py — Monster AI for Project Orin
=========================================

State machine
-------------
  PATROL  — wandering its current zone; player is far away
  ALERT   — detected nearby zone; routing through doors toward player
  CHASE   — same zone as player; actively hunting (speed builds over time)
  SEARCH  — player hid or slipped zone; heading to last-known position then
             sweeping the area before giving up

Improvements over previous version
------------------------------------
  • Explicit state machine (no implicit branching on hiding/same-zone bools)
  • Last-known-position tracking; monster visits that spot on SEARCH
  • Chase speed ramp: starts at 1× and builds up to 1.4× over a few seconds
  • Player-movement prediction: monster aims slightly ahead during chase
  • SEARCH sweep: wanders around anchor point with a soft spring, not just random
  • _move_alert() extracted as reusable helper (used by both ALERT and SEARCH)
  • Draw colour reflects state for easier debugging
"""

import random
import math
import pygame
from config import MONSTER_SPEED, MONSTER_WANDER_SPEED
from map_data import get_zone_doors, get_zone_grid, TILE_WALL

# ---------------------------------------------------------------------------
# Tuning knobs
# ---------------------------------------------------------------------------
DESPAWN_ZONE_DISTANCE = 10
LEAVE_ZONE_DISTANCE   = 7
RESPAWN_TIME_MIN      = 15
RESPAWN_TIME_MAX      = 30

ALERT_ZONE_DIST  = 6      # zone radius at which monster enters ALERT
CHASE_SPEED_MAX  = 1.4    # top speed multiplier during a chase
CHASE_SPEED_RATE = 0.12   # how fast the multiplier climbs per second
SEARCH_DURATION  = 9.0    # seconds to search before giving up
SEARCH_RADIUS    = 90     # pixel radius: wander within this of the anchor

PREDICT_T    = 0.18   # seconds ahead to aim during chase
PREDICT_ALPHA = 0.25  # smoothing factor for player velocity estimate

# ---------------------------------------------------------------------------
# State constants
# ---------------------------------------------------------------------------
STATE_PATROL = 'patrol'
STATE_ALERT  = 'alert'
STATE_CHASE  = 'chase'
STATE_SEARCH = 'search'

# ---------------------------------------------------------------------------
# Spawn ring
# ---------------------------------------------------------------------------
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
        self.rect = pygame.Rect(int(self.x), int(self.y), 32, 32)

        self.active        = False
        self.respawn_timer = random.uniform(RESPAWN_TIME_MIN, RESPAWN_TIME_MAX)

        self._leaving     = False
        self._leave_timer = 0.0

        # Wander direction & timer (used by PATROL and SEARCH)
        self._wander_vx    = 1.0
        self._wander_vy    = 0.0
        self._wander_timer = 0.0

        # Door navigation
        self._door_seek      = None   # (x, y) pixel target at a zone edge
        self._player_zone_x  = 0
        self._player_zone_y  = 0

        # ---- State machine ----
        self._state = STATE_PATROL

        # Last known player position
        self._last_known_x      = None
        self._last_known_y      = None
        self._last_known_zone_x = None
        self._last_known_zone_y = None

        # Chase speed ramp
        self._chase_speed_mult = 1.0

        # Search
        self._search_timer    = 0.0
        self._search_anchor_x = 0.0
        self._search_anchor_y = 0.0

        # Player movement prediction
        self._prev_target_x = None
        self._prev_target_y = None
        self._pred_dx       = 0.0   # estimated player vx (px/s)
        self._pred_dy       = 0.0   # estimated player vy (px/s)

    # =====================================================================
    # Helpers
    # =====================================================================

    def _zone_distance(self, pzx, pzy):
        return math.sqrt((self.loading_zone_x - pzx) ** 2 +
                         (self.loading_zone_y - pzy) ** 2)

    def _pick_wander_direction(self):
        angle = random.uniform(0, 2 * math.pi)
        self._wander_vx    = math.cos(angle)
        self._wander_vy    = math.sin(angle)
        self._wander_timer = random.uniform(1.5, 3.5)

    def _door_edge_pos(self, side):
        """Pixel (x, y) at the midpoint of the given zone edge."""
        cx = self.screen_width  / 2
        cy = self.screen_height / 2
        m  = 24
        return {
            'west':  (m,                      cy),
            'east':  (self.screen_width  - m, cy),
            'north': (cx,                     m),
            'south': (cx, self.screen_height - m),
        }.get(side, (cx, cy))

    def _zone_has_door(self, zx, zy, side):
        return side in get_zone_doors(zx, zy)

    def _best_door_toward(self, target_zx, target_zy):
        """
        Return the side name of the door in the current zone that brings the
        monster closest to (target_zx, target_zy), or None if no doors.
        """
        doors = get_zone_doors(self.loading_zone_x, self.loading_zone_y)
        if not doors:
            return None
        best_side, best_dist = None, float('inf')
        for side in doors:
            if   side == 'east':  nzx, nzy = self.loading_zone_x + 1, self.loading_zone_y
            elif side == 'west':  nzx, nzy = self.loading_zone_x - 1, self.loading_zone_y
            elif side == 'south': nzx, nzy = self.loading_zone_x,     self.loading_zone_y + 1
            elif side == 'north': nzx, nzy = self.loading_zone_x,     self.loading_zone_y - 1
            else: continue
            dist = math.hypot(nzx - target_zx, nzy - target_zy)
            if dist < best_dist:
                best_dist = dist
                best_side = side
        return best_side

    def _set_door_seek(self):
        """Set door-seek to the best door toward the stored player zone."""
        side = self._best_door_toward(self._player_zone_x, self._player_zone_y)
        self._door_seek = self._door_edge_pos(side) if side else None

    def _wall_avoid_force(self):
        """
        Three-feeler wall avoidance. Returns (fx, fy) repulsion force.
        """
        grid = get_zone_grid(self.loading_zone_x, self.loading_zone_y)
        if not grid:
            return 0.0, 0.0
        rows   = len(grid)
        cols   = len(grid[0]) if rows else 1
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
            (nvx * ahead,                        nvy * ahead),
            (nvx * ahead * 0.6 - nvy * perp,    nvy * ahead * 0.6 + nvx * perp),
            (nvx * ahead * 0.6 + nvy * perp,    nvy * ahead * 0.6 - nvx * perp),
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
        self._leave_timer     = 0.0
        self._door_seek       = None
        self._state           = STATE_PATROL
        self._last_known_x    = None
        self._last_known_y    = None
        self._chase_speed_mult = 1.0
        self._search_timer    = 0.0
        self._prev_target_x   = None
        self._prev_target_y   = None
        self._pred_dx         = 0.0
        self._pred_dy         = 0.0
        self._pick_wander_direction()

    # =====================================================================
    # Movement helpers
    # =====================================================================

    def _move_wander(self, dt):
        """Random wander with periodic direction changes and wall avoidance."""
        self._wander_timer -= dt
        if self._wander_timer <= 0:
            self._pick_wander_direction()
        avoid_x, avoid_y = self._wall_avoid_force()
        self.x += (self._wander_vx * MONSTER_WANDER_SPEED + avoid_x) * dt
        self.y += (self._wander_vy * MONSTER_WANDER_SPEED + avoid_y) * dt

    def _move_alert(self, dt, target_zone_x, target_zone_y):
        """
        Navigate toward (target_zone_x, target_zone_y) using door waypoints.
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
                self.x += (nx * MONSTER_WANDER_SPEED + avoid_x) * dt
                self.y += (ny * MONSTER_WANDER_SPEED + avoid_y) * dt
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
            self.x += (nx * MONSTER_WANDER_SPEED + avoid_x) * dt
            self.y += (ny * MONSTER_WANDER_SPEED + avoid_y) * dt

    def _move_chase(self, target_x, target_y, dt):
        """
        Chase the player. Speed ramps up over time.
        Aims slightly ahead of the player based on estimated velocity.
        """
        # Ramp up speed
        self._chase_speed_mult = min(
            CHASE_SPEED_MAX,
            self._chase_speed_mult + CHASE_SPEED_RATE * dt
        )

        # Predict player position PREDICT_T seconds ahead
        px = target_x + self._pred_dx * PREDICT_T
        py = target_y + self._pred_dy * PREDICT_T

        # Clamp prediction to map bounds so we don't chase a ghost outside
        px = max(0, min(px, self.screen_width  - 1))
        py = max(0, min(py, self.screen_height - 1))

        dx   = px - self.x
        dy   = py - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 1:
            nx, ny = dx / dist, dy / dist
            self._wander_vx, self._wander_vy = nx, ny
            avoid_x, avoid_y = self._wall_avoid_force()
            speed = MONSTER_SPEED * self._chase_speed_mult
            self.x += (nx * speed + avoid_x) * dt
            self.y += (ny * speed + avoid_y) * dt

    def _move_search(self, dt):
        """
        Head to last-known position (possibly via doors if different zone),
        then sweep around the anchor point.
        """
        if self._last_known_zone_x is None:
            self._move_wander(dt)
            return

        in_target_zone = (self.loading_zone_x == self._last_known_zone_x and
                          self.loading_zone_y == self._last_known_zone_y)

        if in_target_zone:
            ax, ay = self._search_anchor_x, self._search_anchor_y
            ddx = ax - self.x
            ddy = ay - self.y
            dist = math.sqrt(ddx * ddx + ddy * ddy)

            if dist > SEARCH_RADIUS * 0.6:
                # Beeline to anchor
                nx, ny = ddx / dist, ddy / dist
                self._wander_vx, self._wander_vy = nx, ny
                avoid_x, avoid_y = self._wall_avoid_force()
                self.x += (nx * MONSTER_WANDER_SPEED * 1.15 + avoid_x) * dt
                self.y += (ny * MONSTER_WANDER_SPEED * 1.15 + avoid_y) * dt
            else:
                # Wander around anchor with a soft spring to stay nearby
                self._move_wander(dt)
                pull_dx = ax - self.x
                pull_dy = ay - self.y
                pull_dist = math.sqrt(pull_dx * pull_dx + pull_dy * pull_dy)
                if pull_dist > SEARCH_RADIUS * 1.4:
                    k = (pull_dist - SEARCH_RADIUS) / pull_dist * 0.35
                    self.x += pull_dx * k
                    self.y += pull_dy * k
        else:
            # Navigate zone-by-zone toward the last-known zone
            self._move_alert(dt, self._last_known_zone_x, self._last_known_zone_y)

    def _move_flee_world_edge(self, dt):
        """Flee toward the nearest world border to despawn."""
        dl = self.loading_zone_x
        dr = (self.zone_count_x - 1) - self.loading_zone_x
        dt_ = self.loading_zone_y
        db = (self.zone_count_y - 1) - self.loading_zone_y
        m  = min(dl, dr, dt_, db)
        if   m == dl:  self.x -= MONSTER_WANDER_SPEED * dt
        elif m == dr:  self.x += MONSTER_WANDER_SPEED * dt
        elif m == dt_: self.y -= MONSTER_WANDER_SPEED * dt
        else:          self.y += MONSTER_WANDER_SPEED * dt

    # =====================================================================
    # Zone crossing
    # =====================================================================

    def _cross_zones(self, ignore_doors=False):
        """
        Check all four edges; cross if the destination zone has the right door.
        In normal mode, bounce and set a door-seek if blocked.
        In flee mode (ignore_doors), cross freely and despawn at world edge.
        """
        MARGIN = 24

        # East
        if self.x >= self.screen_width:
            new_zx = self.loading_zone_x + 1
            if new_zx < self.zone_count_x:
                if ignore_doors or self._zone_has_door(new_zx, self.loading_zone_y, 'west'):
                    self.loading_zone_x = new_zx
                    ex, ey = self._door_edge_pos('west')
                    self.x = ex if not ignore_doors else MARGIN
                    self._wander_vx  = abs(self._wander_vx)
                    self._door_seek  = None
                else:
                    self.x = self.screen_width - MARGIN
                    self._wander_vx = -abs(self._wander_vx)
                    if self._door_seek is None:
                        self._set_door_seek()
            else:
                if self._leaving: self._deactivate(); return
                self.x = self.screen_width - 1
                self._wander_vx = -abs(self._wander_vx)

        # West
        elif self.x < 0:
            new_zx = self.loading_zone_x - 1
            if new_zx >= 0:
                if ignore_doors or self._zone_has_door(new_zx, self.loading_zone_y, 'east'):
                    self.loading_zone_x = new_zx
                    ex, ey = self._door_edge_pos('east')
                    self.x = ex if not ignore_doors else self.screen_width - MARGIN
                    self._wander_vx  = -abs(self._wander_vx)
                    self._door_seek  = None
                else:
                    self.x = MARGIN
                    self._wander_vx = abs(self._wander_vx)
                    if self._door_seek is None:
                        self._set_door_seek()
            else:
                if self._leaving: self._deactivate(); return
                self.x = 0
                self._wander_vx = abs(self._wander_vx)

        # South
        if self.y >= self.screen_height:
            new_zy = self.loading_zone_y + 1
            if new_zy < self.zone_count_y:
                if ignore_doors or self._zone_has_door(self.loading_zone_x, new_zy, 'north'):
                    self.loading_zone_y = new_zy
                    ex, ey = self._door_edge_pos('north')
                    self.y = ey if not ignore_doors else MARGIN
                    self._wander_vy  = abs(self._wander_vy)
                    self._door_seek  = None
                else:
                    self.y = self.screen_height - MARGIN
                    self._wander_vy = -abs(self._wander_vy)
                    if self._door_seek is None:
                        self._set_door_seek()
            else:
                if self._leaving: self._deactivate(); return
                self.y = self.screen_height - 1
                self._wander_vy = -abs(self._wander_vy)

        # North
        elif self.y < 0:
            new_zy = self.loading_zone_y - 1
            if new_zy >= 0:
                if ignore_doors or self._zone_has_door(self.loading_zone_x, new_zy, 'south'):
                    self.loading_zone_y = new_zy
                    ex, ey = self._door_edge_pos('south')
                    self.y = ey if not ignore_doors else self.screen_height - MARGIN
                    self._wander_vy  = -abs(self._wander_vy)
                    self._door_seek  = None
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

    # =====================================================================
    # Deactivate
    # =====================================================================

    def _deactivate(self):
        self.active        = False
        self._leaving      = False
        self._leave_timer  = 0.0
        self._door_seek    = None
        self._state        = STATE_PATROL
        self.respawn_timer = random.uniform(RESPAWN_TIME_MIN, RESPAWN_TIME_MAX)

    # =====================================================================
    # Main update
    # =====================================================================

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

        # Hard despawn when very far
        if zone_dist >= DESPAWN_ZONE_DISTANCE:
            self._deactivate()
            return

        # Leaving mode: flee to world edge and despawn
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

        # ---- Flags used by state logic ----
        in_same_zone = (self.loading_zone_x == player_zone_x and
                        self.loading_zone_y == player_zone_y)
        player_visible = (in_same_zone and not hiding
                          and target_x is not None and target_y is not None)

        # ---- Update player velocity estimate for prediction ----
        if target_x is not None and self._prev_target_x is not None:
            raw_vx = (target_x - self._prev_target_x) / max(dt, 0.001)
            raw_vy = (target_y - self._prev_target_y) / max(dt, 0.001)
            self._pred_dx += PREDICT_ALPHA * (raw_vx - self._pred_dx)
            self._pred_dy += PREDICT_ALPHA * (raw_vy - self._pred_dy)
        self._prev_target_x = target_x
        self._prev_target_y = target_y

        # ---- Update last-known position whenever player is visible ----
        if player_visible:
            self._last_known_x      = target_x
            self._last_known_y      = target_y
            self._last_known_zone_x = player_zone_x
            self._last_known_zone_y = player_zone_y

        # ---- State transitions ----
        if self._state == STATE_PATROL:
            if zone_dist < ALERT_ZONE_DIST:
                self._state = STATE_ALERT

        elif self._state == STATE_ALERT:
            if player_visible:
                self._state = STATE_CHASE
                self._chase_speed_mult = 1.0
            elif zone_dist >= ALERT_ZONE_DIST:
                self._state = STATE_PATROL

        elif self._state == STATE_CHASE:
            if not player_visible:
                # Player hid or left — begin search
                self._state        = STATE_SEARCH
                self._search_timer = SEARCH_DURATION
                if (self._last_known_zone_x == player_zone_x and
                        self._last_known_zone_y == player_zone_y):
                    self._search_anchor_x = self._last_known_x or self.x
                    self._search_anchor_y = self._last_known_y or self.y
                else:
                    side = self._best_door_toward(player_zone_x, player_zone_y)
                    ex, ey = self._door_edge_pos(side) if side else (self.x, self.y)
                    self._search_anchor_x = ex
                    self._search_anchor_y = ey

        elif self._state == STATE_SEARCH:
            if player_visible:
                # Re-spotted — immediately give chase with a head-start on speed
                self._state            = STATE_CHASE
                self._chase_speed_mult = 1.15
            else:
                self._search_timer -= dt
                if self._search_timer <= 0:
                    self._state = STATE_PATROL if zone_dist >= ALERT_ZONE_DIST else STATE_ALERT

        # ---- State behaviours ----
        if self._state == STATE_PATROL:
            self._move_wander(dt)

        elif self._state == STATE_ALERT:
            self._move_alert(dt, player_zone_x, player_zone_y)

        elif self._state == STATE_CHASE:
            self._move_chase(target_x, target_y, dt)

        elif self._state == STATE_SEARCH:
            self._move_search(dt)

        self._cross_zones()

    # =====================================================================
    # Draw
    # =====================================================================

    def draw(self, surface):
        if not self.active:
            return
        if self._leaving:
            color = (80, 0, 140)    # dark purple — fleeing
        elif self._state == STATE_CHASE:
            color = (220, 30, 30)   # bright red — hunting
        elif self._state == STATE_SEARCH:
            color = (160, 60, 220)  # violet — searching
        elif self._state == STATE_ALERT:
            color = (200, 120, 0)   # orange — alerted
        else:
            color = (40, 60, 200)   # blue — patrolling
        pygame.draw.rect(surface, color, self.rect)
