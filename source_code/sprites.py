"""
sprites.py — All sprite loading and drawing for Project Orin
=============================================================

Loads every spritesheet from  assets/sprites/  (same directory as this file
or ../assets/sprites/ relative to it).  Falls back to coloured rectangles
when files are missing so the game always runs.

All sprites are extracted from their large canvases, trimmed to their content
bounds, then cached at the game's display size.  Game object pixel dimensions
(rect sizes) are NEVER changed here — only the visual is swapped.

Public draw helpers (call these from entity draw() methods):
------------------------------------------------------------
  draw_player(surface, rect, direction, moving, gun, suit, dt)
  draw_monster(surface, rect, direction, moving, leaving, dt)
  draw_animal(surface, rect, animal_type, direction, moving, dt)
  draw_food(surface, rect, item_id)
  draw_item_box(surface, rect, item_id, collected)
  draw_bullet(surface, x, y, radius)

Zone tile rendering (unchanged public API):
-------------------------------------------
  ZONE_RENDERER.render_zone(surface, grid, zone_type, map_w, map_h)
"""

import os
import math
import pygame

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE       = os.path.dirname(os.path.abspath(__file__))
_ASSETS_DIR = os.path.join(_HERE, "assets", "sprites")

def _path(name):
    return os.path.join(_ASSETS_DIR, name)

# ---------------------------------------------------------------------------
# Zone / tile constants (keep local so map_data import isn't needed)
# ---------------------------------------------------------------------------
TILE_EMPTY   = 0
TILE_WALL    = 1
TILE_OBJECT  = 2
ZONE_FACTORY = 0
ZONE_FOREST  = 1

_PALETTE = {
    ZONE_FACTORY: {TILE_WALL:((52,52,62),(78,78,93)), TILE_OBJECT:((90,60,25),(140,100,45))},
    ZONE_FOREST:  {TILE_WALL:((32,62,28),(52,95,42)), TILE_OBJECT:((75,50,18),(115,80,32))},
}

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _load(name):
    """Load a PNG from assets/sprites/; return None on failure."""
    p = _path(name)
    if not os.path.isfile(p):
        return None
    try:
        img = pygame.image.load(p)
        return img.convert_alpha() if img.get_flags() & pygame.SRCALPHA else img.convert()
    except pygame.error:
        return None


def _crop_content(img, bg='transparent', threshold=10):
    """Return the tight bounding-rect of non-background pixels."""
    w, h = img.get_size()
    arr  = pygame.surfarray.pixels3d(img)   # (w, h, 3)
    if bg == 'transparent':
        alpha = pygame.surfarray.pixels_alpha(img)  # (w, h)
        mask  = alpha > threshold
    else:
        # black background: any channel > threshold counts as content
        mask = (arr[:,:,0] > threshold) | (arr[:,:,1] > threshold) | (arr[:,:,2] > threshold)
    del arr
    # mask is (w, h) — transpose to rows × cols thinking
    cols_with = mask.any(axis=1)   # shape (w,)
    rows_with = mask.any(axis=0)   # shape (h,)
    if not cols_with.any() or not rows_with.any():
        return pygame.Rect(0, 0, w, h)
    x0 = int(cols_with.argmax())
    x1 = int(w - 1 - cols_with[::-1].argmax())
    y0 = int(rows_with.argmax())
    y1 = int(h - 1 - rows_with[::-1].argmax())
    return pygame.Rect(x0, y0, x1 - x0 + 1, y1 - y0 + 1)


def _extract(img, rect, target_size, bg='transparent'):
    """Crop rect from img, make alpha surface, scale to target_size."""
    surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    if bg == 'black':
        # Convert black bg to transparent
        tmp = img.subsurface(rect).copy()
        tmp.set_colorkey((0, 0, 0))
        conv = tmp.convert_alpha()
        surf.blit(conv, (0, 0))
    else:
        surf.blit(img, (0, 0), rect)
    if target_size != (rect.width, rect.height):
        surf = pygame.transform.scale(surf, target_size)
    return surf


def _scale_to_fit(surf, target_w, target_h):
    sw, sh = surf.get_size()
    ratio  = min(target_w / sw, target_h / sh)
    nw, nh = max(1, int(sw * ratio)), max(1, int(sh * ratio))
    return pygame.transform.scale(surf, (nw, nh))


# ---------------------------------------------------------------------------
# Spritesheet frame extractor
#
# Layout definitions: each entry is (sheet_name, bg, frame_rects)
# where frame_rects is a list of pygame.Rect objects (one per frame).
# ---------------------------------------------------------------------------

def _grid_rects(cols_starts, rows_starts, canvas_w, canvas_h, n_frames=None):
    """Build frame rects from content column/row start positions.
    Each "cell" goes from one start to just before the next (or canvas edge).
    Returns list of Rect(x, y, w, h) for each (row, col) cell, row-major."""
    rects = []
    for ri, ry in enumerate(rows_starts):
        ry1 = rows_starts[ri+1] if ri+1 < len(rows_starts) else canvas_h
        rh  = ry1 - ry
        for ci, cx in enumerate(cols_starts):
            cx1 = cols_starts[ci+1] if ci+1 < len(cols_starts) else canvas_w
            cw  = cx1 - cx
            rects.append(pygame.Rect(cx, ry, cw, rh))
            if n_frames is not None and len(rects) >= n_frames:
                return rects
    return rects


class _Sheet:
    """Loads a spritesheet and extracts trimmed, scaled frames."""

    def __init__(self, filename, bg, frame_rects, target_size, n_frames=None):
        self.frames = []
        self._ok    = False
        img = _load(filename)
        if img is None:
            return
        limit = n_frames or len(frame_rects)
        for i, rect in enumerate(frame_rects[:limit]):
            # Clamp rect to image bounds
            iw, ih = img.get_size()
            rect = rect.clip(pygame.Rect(0, 0, iw, ih))
            if rect.width < 2 or rect.height < 2:
                continue
            # Find tight content within the cell
            cell_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            cell_surf.fill((0,0,0,0))
            if bg == 'black':
                tmp = img.subsurface(rect).copy()
                tmp.set_colorkey((0,0,0))
                cell_surf.blit(tmp.convert_alpha(), (0,0))
            else:
                cell_surf.blit(img, (0,0), rect)
            # Scale keeping aspect ratio inside target box
            frame = _scale_to_fit(cell_surf, *target_size)
            # Centre on a target_size canvas
            canvas = pygame.Surface(target_size, pygame.SRCALPHA)
            canvas.fill((0,0,0,0))
            ox = (target_size[0] - frame.get_width())  // 2
            oy = (target_size[1] - frame.get_height()) // 2
            canvas.blit(frame, (ox, oy))
            self.frames.append(canvas)
        self._ok = len(self.frames) > 0

    @property
    def ok(self):
        return self._ok

    def frame(self, idx):
        if not self.frames:
            return None
        return self.frames[idx % len(self.frames)]

    def n(self):
        return len(self.frames)


# ---------------------------------------------------------------------------
# All sprite definitions — measured from the uploaded files
# ---------------------------------------------------------------------------
# Target sizes: must not change gameplay rect sizes. We render sprites
# centred on the entity rect, so they can be visually larger/smaller.
# Player/monster display ≈ 48×64.  Animal ≈ 40×40.  Food/item ≈ 24×24.
_SZ_PLAYER  = (48, 64)
_SZ_MONSTER = (48, 72)
_SZ_ANIMAL  = (40, 40)
_SZ_RABBIT  = (28, 28)
_SZ_ITEM    = (28, 28)
_SZ_BULLET  = None   # drawn procedurally


def _init_sheets():
    """Called once after pygame.display is set (so convert_alpha works)."""
    global _SHEETS
    if _SHEETS:
        return

    def S(fname, bg, rects, size, n=None):
        return _Sheet(fname, bg, rects, size, n)

    # ---- helpers to build rects for specific sheets ----
    def _player_walk_rects(col_starts, row_starts, w, h):
        return _grid_rects(col_starts, row_starts, w, h)

    # ----------------------------------------------------------------
    # PLAYER — no suit
    # ----------------------------------------------------------------
    # normal_walk_left / player_walk_right — 8000x4000 black, 3 cols x 2 rows = 6 frames
    _pw_col = [877, 2987+877, 5096]   # start of each col group (approx cell = 2000px)
    # Use equal-cell split since frames are evenly spaced
    _pw_left = _grid_rects([0, 2667, 5334], [0, 2000], 8000, 4000)
    _pw_right= _grid_rects([0, 2667, 5334], [0, 2000], 8000, 4000)

    # player_walk_forward / player_walk_back — 8000x4000 black
    # content at cols ~[771,1355],[2881,3464],[4990,5573]  rows ~[210,915],[1792,2497]
    _pfwd_col = [0, 2667, 5334]; _pfwd_row = [0, 2000]
    _pback_col= [0, 2667, 5334]; _pback_row= [0, 2000]

    # player_walk_right mirrors left — use same cell grid
    # player_walk_back — 8000x4000

    # Stand poses — 4096x2048 transparent, single content region
    # player_gun_stand_*  and player_gun_walk_*
    # For stands: entire image = 1 frame.  Content starts at measured offsets.
    def _stand_rect(x0,y0,x1,y1):
        return [pygame.Rect(x0, y0, x1-x0, y1-y0)]

    _SHEETS = {
        # ------ player (no gun / no suit) walk ------
        'p_walk_left':    S('normal_walk_left.png',       'black',
                            _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),
        'p_walk_right':   S('player_walk_right.png',      'black',
                            _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),
        'p_walk_fwd':     S('player_walk_forward.png',    'black',
                            _grid_rects([0,2667,5334],[0,2000,4000,6000],8000,8000), _SZ_PLAYER, 6),
        'p_walk_back':    S('player_walk_back.png',       'black',
                            _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),

        # ------ player gun stands ------
        'p_gun_stand_front': S('player_gun_stand_front.png', 'transparent',
                               _stand_rect(186,57,1641,1075), _SZ_PLAYER),
        'p_gun_stand_back':  S('player_gun_stand_back.png',  'transparent',
                               _stand_rect(789,97,1641,1089), _SZ_PLAYER),
        'p_gun_stand_left':  S('player_gun_stand_left.png',  'transparent',
                               _stand_rect(489,81,1649,1075), _SZ_PLAYER),
        'p_gun_stand_right': S('player_gun_stand_right.png', 'transparent',
                               _stand_rect(510,81,1670,1075), _SZ_PLAYER),

        # ------ player gun walk ------
        'p_gun_walk_left':   S('player_gun_left_walk.png',   'black',
                               _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),
        'p_gun_walk_right':  S('player_gun_right_walk.png',  'black',
                               _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),
        'p_gun_walk_fwd':    S('player_gun_walk_forward.png','black',
                               _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),
        'p_gun_walk_back':   S('player_gun_walk_back.png',   'black',
                               _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),

        # ------ suit stands ------
        'suit_stand_front': S('suit_gun_stand_front.png', 'transparent',
                              _stand_rect(818,214,1391,1073), _SZ_PLAYER),
        'suit_stand_back':  S('suit_gun_stand_back.png',  'transparent',
                              _stand_rect(818,214,1391,1088), _SZ_PLAYER),
        'suit_stand_left':  S('suit_gun_stand_left.png',  'transparent',
                              _stand_rect(778,247,1324,1074), _SZ_PLAYER),
        'suit_stand_right': S('suit_gun_stand_right.png', 'transparent',
                              _stand_rect(835,247,1381,1074), _SZ_PLAYER),

        # ------ suit walk ------
        'suit_walk_fwd':    S('suit_gun_walk_front.png',  'black',
                              _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),
        'suit_walk_back':   S('suit_gun_walk_back.png',   'black',
                              _grid_rects([0,2667,5334],[0,2000,4000],8000,8000), _SZ_PLAYER, 6),
        'suit_walk_left':   S('suit_gun_walk_left.png',   'black',
                              _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),
        'suit_walk_right':  S('suit_gun_walk_right.png',  'black',
                              _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_PLAYER, 6),

        # ------ monster stands ------
        'mon_stand_front': S('monster_front_stand.png',  'transparent',
                             _stand_rect(668,33,1433,1503), _SZ_MONSTER),
        'mon_stand_back':  S('monster_stand_back.png',   'transparent',
                             _stand_rect(613,98,1362,1554), _SZ_MONSTER),
        'mon_stand_left':  S('monster_stand_left.png',   'transparent',
                             _stand_rect(635,66,1290,1457), _SZ_MONSTER),
        'mon_stand_right': S('monster_stand_right.png',  'transparent',
                             _stand_rect(869,66,1524,1457), _SZ_MONSTER),

        # ------ monster walk ------
        'mon_walk_front':  S('monster_walk_front.png',   'black',
                             _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_MONSTER, 6),
        'mon_walk_back':   S('monster_walk_back.png',    'black',
                             _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_MONSTER, 6),
        'mon_walk_left':   S('monster_walk_left.png',    'black',
                             _grid_rects([0,2667,5334],[0,2667,5334],8000,8000), _SZ_MONSTER, 7),
        'mon_walk_right':  S('monster_walk_right.png',   'black',
                             _grid_rects([0,2667,5334],[0,2667,5334],8000,8000), _SZ_MONSTER, 7),

        # ------ deer ------
        'deer_stand_upright': S('deer_up-right_stand.png','transparent',
                                _stand_rect(715,333,1448,1528), _SZ_ANIMAL),
        'deer_walk_left':     S('deer_walk_left.png',      'transparent',
                                _grid_rects([0],[0,2048],4096,4096), _SZ_ANIMAL, 2),
        'deer_walk_leftdown': S('deer_walk_left-down.png', 'transparent',
                                _grid_rects([0],[0,2048],4096,4096), _SZ_ANIMAL, 2),
        'deer_walk_rightdown':S('deer_walk_right-down.png','transparent',
                                _grid_rects([0],[0,2048],4096,4096), _SZ_ANIMAL, 2),

        # ------ moose ------
        'moose_stand_left':    S('moose_left_stand.png',    'transparent',
                                 _stand_rect(0,263,1565,1606), _SZ_ANIMAL),
        'moose_stand_upleft':  S('moose_up-left_stand.png', 'transparent',
                                 _stand_rect(0,312,2023,1606), _SZ_ANIMAL),
        'moose_stand_upright': S('moose_up-right_stand.png','transparent',
                                 _stand_rect(0,312,1487,1606), _SZ_ANIMAL),

        # ------ rabbit ------
        'rabbit_stand_front': S('rabbit_stand_front.png','transparent',
                                _stand_rect(953,229,1204,689), _SZ_RABBIT),
        'rabbit_stand_back':  S('rabbit_stand_back.png', 'transparent',
                                _stand_rect(953,229,1204,689), _SZ_RABBIT),
        'rabbit_stand_left':  S('rabbit_stand_left.png', 'transparent',
                                _stand_rect(964,320,1289,733), _SZ_RABBIT),
        'rabbit_stand_right': S('rabbit_stand_right.png','transparent',
                                _stand_rect(870,320,1195,733), _SZ_RABBIT),
        'rabbit_walk_back':   S('rabbit_walk_back.png',  'transparent',
                                _grid_rects([0],[0,2048],4096,4096), _SZ_RABBIT, 2),
        'rabbit_walk_front':  S('rabbit_walk_front.png', 'transparent',
                                _grid_rects([0],[0,2048],4096,4096), _SZ_RABBIT, 2),
        'rabbit_walk_left':   S('rabbit_walk_left.png',  'black',
                                _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_RABBIT, 6),
        'rabbit_walk_right':  S('rabbit_walk_right.png', 'black',
                                _grid_rects([0,2667,5334],[0,2000],8000,4000), _SZ_RABBIT, 6),

        # ------ food / items ------
        'food_deer_meat':  S('deer_meat.png',  'transparent',
                             _stand_rect(737,172,1163,481), _SZ_ITEM),
        'food_moose_meat': S('moose_meat.png', 'transparent',
                             _stand_rect(1183,170,1886,448), _SZ_ITEM),
        'food_rabbit_meat':S('rabbit_meat.png','transparent',
                             _stand_rect(297,275,516,376), _SZ_ITEM),
        'item_box':        S('box.png',        'transparent',
                             _stand_rect(736,501,1361,941), _SZ_ITEM),
        'item_bullets':    S('bullets.png',    'transparent',
                             _stand_rect(722,427,1320,1064), _SZ_ITEM),
        'item_battery':    S('battery.png',    'transparent',
                             _stand_rect(517,106,723,459), _SZ_ITEM),
        'bullet_sprite':   S('bullet_from_gun.png','transparent',
                             _stand_rect(1026,660,1217,842), (8,8)),
    }


_SHEETS: dict = {}   # filled by _init_sheets()

# ---------------------------------------------------------------------------
# Animation timer helpers — per-entity anim state stored externally
# ---------------------------------------------------------------------------
ANIM_FPS = 8.0   # frames per second for walk cycles

def _anim_frame(sheet_key, t):
    sh = _SHEETS.get(sheet_key)
    if sh is None or not sh.ok:
        return None
    idx = int(t * ANIM_FPS) % sh.n()
    return sh.frame(idx)


def _get(sheet_key):
    sh = _SHEETS.get(sheet_key)
    if sh and sh.ok:
        return sh.frame(0)
    return None


# ---------------------------------------------------------------------------
# Direction helpers
# ---------------------------------------------------------------------------
def _dir_from_velocity(dx, dy):
    """Return 'left','right','front','back' from movement delta."""
    if abs(dx) >= abs(dy):
        return 'right' if dx > 0 else 'left'
    return 'back' if dy < 0 else 'front'


# ---------------------------------------------------------------------------
# Fallback draw — coloured rect matching old style
# ---------------------------------------------------------------------------
def _fallback_rect(surface, rect, color):
    pygame.draw.rect(surface, color, rect)


def _blit_centered(surface, sprite, rect):
    """Blit sprite centred on rect."""
    if sprite is None:
        return False
    sx, sy = sprite.get_size()
    ox = rect.centerx - sx // 2
    oy = rect.centery - sy // 2
    surface.blit(sprite, (ox, oy))
    return True


# ---------------------------------------------------------------------------
# Public draw helpers
# ---------------------------------------------------------------------------

def draw_player(surface, rect, dx, dy, moving, has_gun, has_suit, anim_t):
    """
    Draw the player sprite centred on rect.
    dx,dy   — last movement direction (0,0 if standing)
    moving  — bool
    has_gun — bool (player.ammo > 0 or always True)
    has_suit— bool (rad suit equipped)
    anim_t  — float, accumulated time (seconds) for animation
    """
    if not _SHEETS:
        _fallback_rect(surface, rect, (0, 200, 0))
        return

    direction = _dir_from_velocity(dx, dy) if (dx or dy) else 'front'

    if has_suit:
        prefix = 'suit'
    elif has_gun:
        prefix = 'p_gun'
    else:
        prefix = 'p'

    if moving:
        key = f'{prefix}_walk_{direction}'
        sprite = _anim_frame(key, anim_t)
        if sprite is None:  # try stand fallback
            key = f'{prefix}_stand_{direction}'
            sprite = _get(key)
    else:
        key = f'{prefix}_stand_{direction}'
        sprite = _get(key)
        if sprite is None and has_suit:
            sprite = _get(f'suit_stand_front')
        if sprite is None:
            sprite = _get(f'p_gun_stand_front')

    if not _blit_centered(surface, sprite, rect):
        _fallback_rect(surface, rect, (0, 200, 0))


def draw_monster(surface, rect, dx, dy, moving, leaving, anim_t):
    """Draw monster sprite centred on rect."""
    if not _SHEETS:
        color = (180,0,220) if leaving else (0,0,200)
        _fallback_rect(surface, rect, color)
        return

    direction = _dir_from_velocity(dx, dy) if (dx or dy) else 'front'

    if moving:
        key  = f'mon_walk_{direction}'
        spr  = _anim_frame(key, anim_t)
        if spr is None:
            key = f'mon_stand_{direction}'
            spr = _get(key)
    else:
        key = f'mon_stand_{direction}'
        spr = _get(key)

    if leaving and spr:
        # Tint purple when retreating
        tinted = spr.copy()
        tinted.fill((80, 0, 80, 60), special_flags=pygame.BLEND_RGBA_ADD)
        spr = tinted

    if not _blit_centered(surface, spr, rect):
        color = (180,0,220) if leaving else (0,0,200)
        _fallback_rect(surface, rect, color)


# Animal type constants — callers use these
ANIMAL_DEER   = 'deer'
ANIMAL_MOOSE  = 'moose'
ANIMAL_RABBIT = 'rabbit'

def draw_animal(surface, rect, animal_type, dx, dy, moving, anim_t):
    """Draw an animal sprite centred on rect."""
    if not _SHEETS:
        _fallback_rect(surface, rect, (125, 100, 10))
        return

    direction = _dir_from_velocity(dx, dy) if (dx or dy) else 'front'
    spr = None

    if animal_type == ANIMAL_DEER:
        if moving:
            if direction in ('left',):
                spr = _anim_frame('deer_walk_left', anim_t)
            elif direction == 'back':
                spr = _anim_frame('deer_walk_leftdown', anim_t)
            else:
                spr = _anim_frame('deer_walk_rightdown', anim_t)
        if spr is None:
            spr = _get('deer_stand_upright')

    elif animal_type == ANIMAL_MOOSE:
        if direction == 'left':
            spr = _get('moose_stand_left')
        elif direction == 'back':
            spr = _get('moose_stand_upleft')
        else:
            spr = _get('moose_stand_upright')

    elif animal_type == ANIMAL_RABBIT:
        if moving:
            if direction in ('left',):
                spr = _anim_frame('rabbit_walk_left', anim_t)
            elif direction == 'right':
                spr = _anim_frame('rabbit_walk_right', anim_t)
            elif direction == 'back':
                spr = _anim_frame('rabbit_walk_back', anim_t)
            else:
                spr = _anim_frame('rabbit_walk_front', anim_t)
        if spr is None:
            key_map = {'front':'rabbit_stand_front','back':'rabbit_stand_back',
                       'left':'rabbit_stand_left','right':'rabbit_stand_right'}
            spr = _get(key_map.get(direction,'rabbit_stand_front'))

    if not _blit_centered(surface, spr, rect):
        _fallback_rect(surface, rect, (125, 100, 10))


# Food item_id -> sprite key
_FOOD_SPRITE = {
    'deer_meat':   'food_deer_meat',
    'moose_meat':  'food_moose_meat',
    'rabbit_meat': 'food_rabbit_meat',
}
_FOOD_COLOR = {
    'deer_meat':   (160, 80, 60),
    'moose_meat':  (140, 70, 50),
    'rabbit_meat': (130, 80, 70),
}

def draw_food(surface, rect, item_id='food_can'):
    """Draw a food drop centred on rect."""
    key = _FOOD_SPRITE.get(item_id)
    spr = _get(key) if key else None
    if not _blit_centered(surface, spr, rect):
        color = _FOOD_COLOR.get(item_id, (255, 100, 100))
        _fallback_rect(surface, rect, color)


_BOX_SPRITE_MAP = {
    'health_pack':  None,
    'food_can':     None,
    'rad_pill':     None,
    'map_fragment': None,
    'key':          None,
    'bullets':      'item_bullets',
    'battery':      'item_battery',
    'ammo':         'item_bullets',
}
_BOX_COLORS = {
    'health_pack':  (120,220,130), 'food_can': (255,170,90),
    'rad_pill':     (255,130,180), 'map_fragment': (95,205,255),
    'key':          (255,215,90),
}

def draw_item_box(surface, rect, item_id, collected):
    """Draw a collectible box."""
    if collected:
        # Show the used box sprite (darker)
        spr = _get('item_box')
        if spr:
            dark = spr.copy()
            dark.fill((0,0,0,120), special_flags=pygame.BLEND_RGBA_MULT)
            _blit_centered(surface, dark, rect)
        else:
            pygame.draw.rect(surface, (70,70,80), rect)
        pygame.draw.rect(surface, (255,255,255), rect, 2)
        return

    # Uncollected: show box sprite with a colour tint based on item type
    spr_key = _BOX_SPRITE_MAP.get(item_id)
    spr = _get(spr_key) if spr_key else None
    if spr is None:
        spr = _get('item_box')

    color = _BOX_COLORS.get(item_id, (160,95,45))
    if not _blit_centered(surface, spr, rect):
        pygame.draw.rect(surface, color, rect)
        pygame.draw.rect(surface, (255,255,255), rect, 2)
        inner = pygame.Rect(rect.x+8, rect.y+8, 16, 16)
        pygame.draw.rect(surface, (255,255,255), inner)
    else:
        pygame.draw.rect(surface, (255,255,255), rect, 2)


def draw_bullet(surface, x, y, radius):
    """Draw a bullet at (x,y)."""
    spr = _get('bullet_sprite')
    if spr:
        bx = int(x - spr.get_width()//2)
        by = int(y - spr.get_height()//2)
        surface.blit(spr, (bx, by))
    else:
        pygame.draw.circle(surface, (255, 220, 50), (int(x), int(y)), radius)


# ---------------------------------------------------------------------------
# Zone tile renderer (unchanged public API)
# ---------------------------------------------------------------------------

class SpriteSheet:
    def __init__(self, sheet_path, tile_w, tile_h):
        self._sheet  = None
        self._tile_w = tile_w
        self._tile_h = tile_h
        self._loaded = False
        if os.path.isfile(sheet_path):
            try:
                raw = pygame.image.load(sheet_path)
                self._sheet  = raw.convert_alpha()
                self._loaded = True
            except pygame.error:
                pass

    @property
    def loaded(self):
        return self._loaded

    def get_sprite(self, col, row, scale_to=None):
        if not self._loaded:
            return None
        src = pygame.Rect(col*self._tile_w, row*self._tile_h, self._tile_w, self._tile_h)
        s   = pygame.Surface((self._tile_w, self._tile_h), pygame.SRCALPHA)
        s.blit(self._sheet, (0,0), src)
        if scale_to and scale_to != (self._tile_w, self._tile_h):
            s = pygame.transform.scale(s, scale_to)
        return s


class ZoneRenderer:
    def __init__(self, sheet=None):
        self._sheet  = sheet
        self._cache  = {}

    def render_tile(self, surface, tile_id, zone_type, rx, ry, tile_w, tile_h):
        if tile_id == TILE_EMPTY:
            return
        zpal = _PALETTE.get(zone_type, _PALETTE[ZONE_FACTORY])
        fill, border = zpal.get(tile_id, ((100,100,100),(140,140,140)))
        if tile_id == TILE_OBJECT:
            px = max(1, tile_w//6); py = max(1, tile_h//6)
            pygame.draw.rect(surface, fill,   (rx+px, ry+py, tile_w-px*2, tile_h-py*2))
            pygame.draw.rect(surface, border, (rx+px, ry+py, tile_w-px*2, tile_h-py*2), 2)
        else:
            pygame.draw.rect(surface, fill,   (rx, ry, tile_w, tile_h))
            pygame.draw.rect(surface, border, (rx, ry, tile_w, tile_h), 2)

    def render_zone(self, surface, grid, zone_type, map_w, map_h):
        if not grid:
            return
        rows   = len(grid)
        cols   = len(grid[0]) if rows else 1
        tile_w = map_w // cols
        tile_h = map_h // rows
        for ty, row in enumerate(grid):
            for tx, tile in enumerate(row):
                if tile != TILE_EMPTY:
                    self.render_tile(surface, tile, zone_type,
                                     tx*tile_w, ty*tile_h, tile_w, tile_h)

    def clear_cache(self):
        self._cache.clear()


_TILE_SHEET_PATH = os.path.join(_ASSETS_DIR, "tiles.png")
ZONE_RENDERER = ZoneRenderer(SpriteSheet(_TILE_SHEET_PATH, 16, 16))


def init_sprites():
    """Call after pygame.display.set_mode() to load all spritesheets."""
    _init_sheets()