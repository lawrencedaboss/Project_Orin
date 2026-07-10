from sprites import draw_monster
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
from collections import deque
from config import MONSTER_SPEED, MONSTER_WANDER_SPEED
from map_data import get_zone_doors, get_zone_grid, TILE_WALL

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------
# NOTE: distances here are in real door-crossing hops (see _bfs_route),
# not straight-line zone distance. This map's door graph is a winding
# maze — two zones that look 6-7 apart in a straight line are routinely
# 15-25 real hops apart, or in a different reachable pocket entirely — so
# straight-line-tuned thresholds despawned/fled the monster almost
# immediately on every spawn. _spawn_near_player already picks the
# closest *reachable* candidate, which is typically 6-9 hops away even
# in the best case, so these budgets need real headroom above that for
# the monster to have any chance of closing the distance before giving up.
DESPAWN_ZONE_DISTANCE = 24
LEAVE_ZONE_DISTANCE   = 18
RESPAWN_TIME_MIN      = 15
RESPAWN_TIME_MAX      = 30

ALERT_ZONE_DIST   = 20     # real path-hop radius (see DESPAWN_ZONE_DISTANCE
                            # comment above) at which the monster enters
                            # ALERT and starts routing toward the player;
                            # kept below LEAVE_ZONE_DISTANCE so it commits
                            # to a real chase before the leave timer could
                            # ever start counting down
CHASE_SPEED_MAX   = 1.5   # top speed multiplier during a chase
CHASE_SPEED_RATE  = 0.15   # how fast the multiplier climbs per second
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

# side -> (dzx, dzy, opposite side). The opposite side is what the
# *destination* zone must declare for the crossing to be allowed — this
# mirrors the gating check `_cross_zones` actually performs, which (unlike
# a naive "does the current zone have a door here" check) is what
# determines whether a crossing is real. Zone door data isn't guaranteed
# symmetric, so route-finding has to use this exact rule or it can plan
# a route that _cross_zones will refuse to let it take.
_SIDE_DELTA = {
    'east':  (1, 0, 'west'),
    'west':  (-1, 0, 'east'),
    'south': (0, 1, 'north'),
    'north': (0, -1, 'south'),
}


def _zone_can_cross(fx, fy, side, zone_count_x, zone_count_y):
    """
    Can the monster actually get from zone (fx,fy) to its neighbour via
    `side`? Two conditions, both required:
      1. (fx,fy) itself declares a door on `side` — a zone's own tile
         grid only has a wall opening where *that zone* declares a door,
         so without this the monster can never physically walk to the
         edge to attempt the crossing at all.
      2. The destination zone declares the opposite-side door — this is
         the actual gate `_cross_zones` checks before letting the
         crossing complete.
    Door data isn't guaranteed symmetric between neighbours, so a hop
    that only satisfies one of these is a dead end: either the monster
    can't reach the edge, or it reaches the edge and gets bounced back.
    """
    dzx, dzy, opposite = _SIDE_DELTA[side]
    tx, ty = fx + dzx, fy + dzy
    if not (0 <= tx < zone_count_x and 0 <= ty < zone_count_y):
        return None
    if side not in get_zone_doors(fx, fy):
        return None
    if opposite in get_zone_doors(tx, ty):
        return (tx, ty)
    return None


def _bfs_route(src, dst, zone_count_x, zone_count_y):
    """
    Shortest real path from src to dst over the zone graph (using the
    mutual-door crossing rule above). Returns (first_hop_side, path_len_in_hops),
    or None if src == dst or no path exists.

    path_len_in_hops is used instead of straight-line zone distance for
    the leave/despawn checks: a BFS route often has to detour away from
    the target before it can loop back around a wall, so straight-line
    distance can spike past the despawn threshold mid-route even though
    the monster is making real progress. Hop count reflects actual
    distance-to-go along the path it's following.
    """
    if src == dst:
        return None
    seen   = {src}
    parent = {}
    q = deque([src])
    while q:
        cur = q.popleft()
        if cur == dst:
            path_len = 0
            node = cur
            while node != src:
                node = parent[node][0]
                path_len += 1
            first = cur
            while parent[first][0] != src:
                first = parent[first][0]
            return parent[first][1], path_len
        cx, cy = cur
        for side in ('east', 'west', 'south', 'north'):
            nxt = _zone_can_cross(cx, cy, side, zone_count_x, zone_count_y)
            if nxt is not None and nxt not in seen:
                seen.add(nxt)
                parent[nxt] = (cur, side)
                q.append(nxt)
    return None


def _tile_path_next_waypoint(grid, from_tx, from_ty, to_tx, to_ty):
    """
    BFS over a zone's own tile grid (walls block, 4-directional) from
    (from_tx,from_ty) to (to_tx,to_ty). Returns the tile coords of the
    *second* tile on the shortest path (the first real step away from
    the current tile), or None if no path exists or already there.

    Reactive steering (aim-at-target + feeler-based wall avoidance) can
    get trapped indefinitely in a zigzag/dead-end corridor: the avoidance
    force and the aim force can settle into a loop that cancels out net
    progress every tick, forever, in a way no tuning of the reactive
    forces can fully rule out. Actual pathfinding over the tile grid
    doesn't have that failure mode — it always finds real progress if a
    path exists at all.
    """
    if not grid:
        return None
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    if not (0 <= from_ty < rows and 0 <= from_tx < cols and
            0 <= to_ty   < rows and 0 <= to_tx   < cols):
        return None
    if (from_tx, from_ty) == (to_tx, to_ty):
        return None
    if grid[to_ty][to_tx] == TILE_WALL:
        return None

    start = (from_tx, from_ty)
    goal  = (to_tx, to_ty)
    seen   = {start}
    parent = {}
    q = deque([start])
    while q:
        cx, cy = q.popleft()
        if (cx, cy) == goal:
            node = (cx, cy)
            while parent[node] != start:
                node = parent[node]
            return node
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < cols and 0 <= ny < rows and (nx, ny) not in seen:
                if grid[ny][nx] != TILE_WALL:
                    seen.add((nx, ny))
                    parent[(nx, ny)] = (cx, cy)
                    q.append((nx, ny))
    return None


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
        # sprite animation state
        self._anim_t  = 0.0
        self._last_dx = 0.0
        self._last_dy = 1.0

        self._leaving     = False
        self._leave_timer = 0.0

        self._wander_vx    = 1.0
        self._wander_vy    = 0.0
        self._wander_timer = 0.0

        self._door_seek     = None
        self._route_hops    = None   # BFS hop-count-to-target from _set_door_seek
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

    def _door_exit_pos(self, side):
        """
        Waypoint used to *leave* the current zone through `side` — sits
        just past the zone boundary so walking to it actually triggers
        `_cross_zones()`, unlike `_door_edge_pos` (the post-crossing
        arrival point, which sits *inside* the boundary and would leave
        the monster parked short of the edge forever).
        """
        cx = self.screen_width  / 2
        cy = self.screen_height / 2
        m  = 24
        return {
            'west':  (-m,                          cy),
            'east':  (self.screen_width + m,       cy),
            'north': (cx,                          -m),
            'south': (cx, self.screen_height + m),
        }.get(side, (cx, cy))

    def _zone_has_door(self, zx, zy, side):
        return side in get_zone_doors(zx, zy)

    def _set_door_seek(self, target_zone_x, target_zone_y):
        """
        Point `_door_seek` at the exit waypoint for the first hop of the
        shortest real path (per the crossing rule `_cross_zones` enforces)
        from the current zone toward (target_zone_x, target_zone_y).

        Previously this greedily picked whichever of the *current* zone's
        declared doors looked closest to the target by straight-line zone
        distance, with no path memory and no check that the destination
        zone actually allows the crossing back. On corridors where door
        data isn't symmetric, or where two neighbouring zones both look
        "closer", that greedy pick could send the monster back and forth
        between the same two zones forever without making net progress.
        """
        route = _bfs_route(
            (self.loading_zone_x, self.loading_zone_y),
            (target_zone_x, target_zone_y),
            self.zone_count_x, self.zone_count_y,
        )
        if route is None:
            self._door_seek   = None
            self._route_hops  = None
            return
        side, hops = route
        self._door_seek  = self._door_exit_pos(side)
        self._route_hops = hops

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

    def _tile_coords(self, px, py):
        grid = get_zone_grid(self.loading_zone_x, self.loading_zone_y)
        rows = len(grid)
        cols = len(grid[0]) if rows else 1
        tile_w = self.screen_width  / cols
        tile_h = self.screen_height / rows
        tx = int((px + 16) / tile_w)
        ty = int((py + 16) / tile_h)
        return grid, tx, ty, tile_w, tile_h

    def _line_clear(self, dx, dy, dist):
        """Sample points along the straight line from the current position
        by delta (dx,dy) (length `dist`) and report whether they're all
        wall-free."""
        if dist < 1:
            return True
        step = 16
        n = max(1, int(dist // step))
        for i in range(1, n + 1):
            t = min(i * step, dist)
            px = self.x + dx * (t / dist)
            py = self.y + dy * (t / dist)
            if self._in_wall(px, py):
                return False
        return True

    def _steer_dir_toward(self, target_x, target_y):
        """
        Direction vector (nx, ny) to move this tick to make real progress
        toward (target_x, target_y) within the current zone, routing
        around walls via tile-grid pathfinding rather than pure
        aim-at-target + reactive feeler avoidance.

        Reactive steering alone can settle into a loop in a zigzag
        corridor where the "aim at target" and "avoid this wall" forces
        cancel out net progress every tick, forever — no feeler tuning
        can fully rule that out since it depends on the specific corridor
        shape. Falling back to real pathfinding when the straight line to
        the target is blocked guarantees forward progress whenever a
        route exists at all.
        """
        grid, tx, ty, tile_w, tile_h = self._tile_coords(self.x, self.y)
        rows = len(grid)
        cols = len(grid[0]) if rows else 0
        # Door-exit waypoints deliberately sit just past the zone boundary
        # (see _door_exit_pos) so reaching them actually triggers a zone
        # crossing — but that puts their tile coords out of this zone's
        # grid entirely. Clamp to the nearest in-bounds tile so the
        # pathfinder still targets "the door opening on this edge"
        # instead of silently refusing to run at all.
        goal_tx = min(max(int(target_x / tile_w), 0), cols - 1) if tile_w and cols else 0
        goal_ty = min(max(int(target_y / tile_h), 0), rows - 1) if tile_h and rows else 0

        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.hypot(dx, dy)
        if dist < 1:
            return self._wander_vx, self._wander_vy
        straight_nx, straight_ny = dx / dist, dy / dist

        # Only take the direct line if it's clear ALL the way to the
        # target (not just a short probe ahead) — a short probe can miss
        # a wall further along the line, commit to a heading that then
        # hits that wall, and settle into a stable back-and-forth loop
        # with the corner-avoidance fallback in _apply_move.
        if self._line_clear(dx, dy, dist):
            return straight_nx, straight_ny

        waypoint = _tile_path_next_waypoint(grid, tx, ty, goal_tx, goal_ty)
        if waypoint is None:
            return straight_nx, straight_ny
        wtx, wty = waypoint
        wx = (wtx + 0.5) * tile_w - 16
        wy = (wty + 0.5) * tile_h - 16
        wdx, wdy = wx - self.x, wy - self.y
        wdist = math.hypot(wdx, wdy)
        if wdist < 0.5:
            return straight_nx, straight_ny
        return wdx / wdist, wdy / wdist

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
        Tries full move, then axis-separated fallbacks, then — if the
        current heading is fully blocked (e.g. wedged in a corner) — an
        8-way compass sweep so the monster always makes some progress
        instead of freezing in place forever.
        """
        nx, ny = self.x + dx, self.y + dy
        # Full move
        if not self._in_wall(nx, ny):
            self.x, self.y = nx, ny
            return
        # Try x-only (only meaningful if this axis moves by more than a
        # negligible amount — a near-zero component would "succeed" the
        # wall check by re-validating essentially the current position,
        # taking a real step forward without ever making progress)
        MIN_STEP = 0.5
        if abs(dx) > MIN_STEP and not self._in_wall(nx, self.y):
            self.x = nx
            self._wander_vy = -self._wander_vy
            return
        # Try y-only (same caveat as above)
        if abs(dy) > MIN_STEP and not self._in_wall(self.x, ny):
            self.y = ny
            self._wander_vx = -self._wander_vx
            return
        # Fully blocked on this heading — sweep compass directions for the
        # first one that's clear, so a corner never freezes the monster.
        step = math.hypot(dx, dy) or (MONSTER_WANDER_SPEED * 0.02)
        for angle_deg in (45, -45, 90, -90, 135, -135, 180):
            ang = math.atan2(dy, dx) + math.radians(angle_deg)
            tvx, tvy = math.cos(ang), math.sin(ang)
            tx, ty = self.x + tvx * step, self.y + tvy * step
            if not self._in_wall(tx, ty):
                self.x, self.y = tx, ty
                self._wander_vx, self._wander_vy = tvx, tvy
                return
        # Every direction blocked (fully enclosed) — pick a new random
        # direction for next tick as a last resort.
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
        if self.loading_zone_x == target_zone_x and self.loading_zone_y == target_zone_y:
            self._move_wander(dt)
            return

        # Always route through an actual door rather than cutting a
        # straight line toward the target zone — the direct line ignores
        # this zone's interior wall layout and can walk the monster
        # straight into a wall it can never path around.
        if self._door_seek is None:
            self._set_door_seek(target_zone_x, target_zone_y)

        if self._door_seek is not None:
            sk_x, sk_y = self._door_seek
            ddx = sk_x - self.x
            ddy = sk_y - self.y
            ddist = math.sqrt(ddx ** 2 + ddy ** 2)
            if ddist > 1:
                nx, ny = self._steer_dir_toward(sk_x, sk_y)
            else:
                nx, ny = self._wander_vx, self._wander_vy
            self._wander_vx, self._wander_vy = nx, ny
            spd = MONSTER_WANDER_SPEED
            # No extra wall_avoid_force here: _steer_dir_toward already
            # routes around walls via tile-grid pathfinding when the
            # direct line is blocked. Adding the reactive avoidance force
            # on top fights the path direction and can cancel out net
            # progress every tick (a stable 2-3 tick position cycle).
            self._apply_move(nx * spd * dt, ny * spd * dt)
            if ddist < 40:
                # Close enough to the door — clear so the next tick
                # re-aims (e.g. after actually crossing into the new
                # zone). Movement above still happened this tick, so
                # the monster keeps pushing toward/through the doorway
                # instead of freezing in place while "arrived".
                self._door_seek = None
        else:
            # No doors at all in this zone (shouldn't normally happen) —
            # fall back to a blind vector so the monster still moves.
            dz_x = target_zone_x - self.loading_zone_x
            dz_y = target_zone_y - self.loading_zone_y
            dzlen = math.sqrt(dz_x ** 2 + dz_y ** 2)
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
                        self._set_door_seek(self._player_zone_x, self._player_zone_y)
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
                        self._set_door_seek(self._player_zone_x, self._player_zone_y)
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
                        self._set_door_seek(self._player_zone_x, self._player_zone_y)
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
                        self._set_door_seek(self._player_zone_x, self._player_zone_y)
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
        self._route_hops   = None
        self._state        = STATE_PATROL
        self.respawn_timer = random.uniform(RESPAWN_TIME_MIN, RESPAWN_TIME_MAX)

    def _spawn_near_player(self, pzx, pzy):
        # Pick the candidate offset with the shortest *real* path back to
        # the player, not just a random one that's a plausible straight-
        # line distance away. This map's doors form a winding maze where
        # a zone 6-7 zones away in a straight line can easily be 20+ real
        # door-crossings away (or in a separate, unreachable pocket) — a
        # random pick from _SPAWN_OFFSETS routinely stranded the monster
        # so far along the real graph that it was doomed to despawn
        # before ever closing the distance.
        candidates = _SPAWN_OFFSETS[:]
        random.shuffle(candidates)
        best_zone, best_hops = None, None
        for dx, dy in candidates:
            cx, cy = pzx + dx, pzy + dy
            if not (0 <= cx < self.zone_count_x and 0 <= cy < self.zone_count_y):
                continue
            if cx == pzx and cy == pzy:
                continue
            route = _bfs_route((cx, cy), (pzx, pzy), self.zone_count_x, self.zone_count_y)
            if route is None:
                continue
            hops = route[1]
            if best_hops is None or hops < best_hops:
                best_zone, best_hops = (cx, cy), hops
                if best_hops <= LEAVE_ZONE_DISTANCE - 2:
                    break  # good enough, stop searching

        if best_zone is not None:
            spawn_x, spawn_y = best_zone
        else:
            # No reachable candidate at all (player is in a tiny isolated
            # pocket) — fall back to the old straight-line pick so the
            # monster still spawns somewhere rather than not at all.
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
        self._route_hops   = None
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

    def _path_distance(self, pzx, pzy):
        """
        Real distance-to-target in door-crossing hops, used for the
        leave/despawn checks. Straight-line zone distance (`_zone_distance`)
        isn't a safe proxy here: a BFS route often has to detour away from
        the target before looping back around a wall, so straight-line
        distance can spike past the despawn threshold mid-route even
        though the monster is making real progress toward the player.
        Returns DESPAWN_ZONE_DISTANCE (i.e. "just despawn") if no path
        exists at all, so an unreachable player doesn't strand the
        monster forever.
        """
        if self.loading_zone_x == pzx and self.loading_zone_y == pzy:
            return 0
        route = _bfs_route((self.loading_zone_x, self.loading_zone_y),
                            (pzx, pzy), self.zone_count_x, self.zone_count_y)
        return route[1] if route is not None else DESPAWN_ZONE_DISTANCE

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
        path_dist = self._path_distance(player_zone_x, player_zone_y)

        if path_dist >= DESPAWN_ZONE_DISTANCE:
            self._deactivate()
            return

        # ---- Leaving countdown ----
        if not self._leaving:
            if path_dist >= LEAVE_ZONE_DISTANCE:
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
            if path_dist < ALERT_ZONE_DIST:
                self._state = STATE_ALERT

        elif self._state == STATE_ALERT:
            if player_visible:
                self._state            = STATE_CHASE
                self._chase_speed_mult = 1.0
            elif path_dist >= ALERT_ZONE_DIST:
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
                    self._state = STATE_PATROL if path_dist >= ALERT_ZONE_DIST else STATE_ALERT

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

    def draw(self, surface, dt=0.0):
        if not self.active:
            return
        moving = (abs(self._last_dx) > 0.01 or abs(self._last_dy) > 0.01)
        if moving:
            self._anim_t += dt
        draw_monster(surface, self.rect,
                     self._last_dx, self._last_dy,
                     moving, self._leaving, self._anim_t)