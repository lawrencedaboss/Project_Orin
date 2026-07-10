"""
sprites.py — Sprite loader and draw helpers for Project Orin
=============================================================
Loads PNGs from the same folder as this file.
For transparent-bg images: loads with convert_alpha(), crops the content rect.
For black-bg sheets: loads, sets colorkey=(0,0,0), crops each cell.
No per-pixel loops. No PIL needed.

Call init_sprites() once after pygame.display.set_mode().
All draw functions fall back to coloured rects when files are missing.
"""

import os
import pygame

SPRITE_DIR = os.path.join(os.getcwd(), "assets", "animations")



# ---- display sizes (visuals only, rect/collision sizes never change) ----
_SZ_P = (16, 20)   # player
_SZ_M = (24, 36)   # monster
_SZ_A = (38, 38)   # deer / moose
_SZ_R = (26, 26)   # rabbit
_SZ_I = (26, 26)   # items / food

ANIM_FPS = 8.0
_READY   = False
_FRAMES  = {}      # key -> list[pygame.Surface]

ANIMAL_DEER   = 'deer'
ANIMAL_MOOSE  = 'moose'
ANIMAL_RABBIT = 'rabbit'


# ---------------------------------------------------------------------------
# Core loaders
# ---------------------------------------------------------------------------

def _load_img(fname, colorkey=None):
    """Load a PNG. Returns None on failure."""
    path = os.path.join(SPRITE_DIR, fname)
    if not os.path.isfile(path):
        return None
    try:
        img = pygame.image.load(path)
        if colorkey is not None:
            img = img.convert()
            img.set_colorkey(colorkey)
        else:
            img = img.convert_alpha()
        return img
    except pygame.error as e:
        print(f"[sprites] load failed {fname}: {e}")
        return None


def _crop_scale(img, crop, target):
    """Crop a rect from img, scale to target size preserving aspect ratio, centred."""
    if img is None:
        return None
    x0, y0, x1, y1 = crop
    cw, ch = x1 - x0, y1 - y0
    if cw <= 0 or ch <= 0:
        return None
    sub  = img.subsurface(pygame.Rect(x0, y0, cw, ch)).copy()
    tw, th = target
    ratio = min(tw / cw, th / ch)
    nw, nh = max(1, int(cw * ratio)), max(1, int(ch * ratio))
    scaled = pygame.transform.scale(sub, (nw, nh))
    canvas = pygame.Surface(target, pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 0))
    canvas.blit(scaled, ((tw - nw) // 2, (th - nh) // 2))
    return canvas


# ---------------------------------------------------------------------------
# Content-aware frame detection
# ---------------------------------------------------------------------------
# Generated sheets vary in canvas size (4096x2048 up to 8192x8192) and in how
# much of that canvas the art actually occupies, so slicing a sheet into a
# fixed cols x rows grid cuts frames at the wrong boundaries (empty margins
# get treated as frames, or one frame gets split across two cells). Instead
# we find the actual blobs of non-background pixels via connected-component
# analysis and crop each one individually.

def _merge_close_rects(rects, gap):
    """Union rects that are within `gap` px of each other (repeatedly, until
    stable). Needed because thin details — claws, hair strands, a gun barrel —
    are often detected as separate components from the main body."""
    rects = list(rects)
    changed = True
    while changed:
        changed = False
        out  = []
        used = [False] * len(rects)
        for i in range(len(rects)):
            if used[i]:
                continue
            r = rects[i].copy()
            for j in range(i + 1, len(rects)):
                if used[j]:
                    continue
                if r.inflate(gap, gap).colliderect(rects[j]):
                    r = r.union(rects[j])
                    used[j] = True
                    changed = True
            out.append(r)
        rects = out
    return rects


def _content_rects(img, min_frac=0.12):
    """Return the significant content blobs on a sheet (colourkey/alpha
    already applied to `img`), largest-relative noise filtered out."""
    iw, ih = img.get_size()
    mask  = pygame.mask.from_surface(img, threshold=30)
    rects = mask.get_bounding_rects()
    if not rects:
        return []
    gap   = max(15, int(min(iw, ih) * 0.01))
    rects = _merge_close_rects(rects, gap)
    max_area = max(r.w * r.h for r in rects)
    return [r for r in rects if r.w * r.h >= max_area * min_frac]


def _reading_order(rects):
    """Sort blobs top-to-bottom by row, left-to-right within each row —
    the order animation frames are laid out in on a sheet."""
    rows = []
    for r in sorted(rects, key=lambda r: r.centery):
        placed = False
        for row in rows:
            ry = row[0].centery
            if abs(r.centery - ry) < max(r.height, row[0].height) * 0.5:
                row.append(r)
                placed = True
                break
        if not placed:
            rows.append([r])
    rows.sort(key=lambda row: sum(r.centery for r in row) / len(row))
    ordered = []
    for row in rows:
        row.sort(key=lambda r: r.centerx)
        ordered.extend(row)
    return ordered


def _single(fname, bg, target):
    """Load one image, auto-detect its content blob, crop + scale to target."""
    colorkey = (0, 0, 0) if bg == 'black' else None
    img = _load_img(fname, colorkey)
    if img is None:
        return []
    rects = _content_rects(img)
    if not rects:
        return []
    bbox = rects[0]
    for r in rects[1:]:
        bbox = bbox.union(r)
    surf = _crop_scale(img, (bbox.left, bbox.top, bbox.right, bbox.bottom), target)
    return [surf] if surf else []


def _grid(fname, bg, target):
    """
    Auto-detect every animation frame on a sheet and return them in on-sheet
    (reading) order. Each frame is cropped to its own content box and scaled
    independently, so frame sizes don't drift between poses on the same sheet.
    """
    colorkey = (0, 0, 0) if bg == 'black' else None
    img = _load_img(fname, colorkey)
    if img is None:
        return []
    frames = []
    for r in _reading_order(_content_rects(img)):
        surf = _crop_scale(img, (r.left, r.top, r.right, r.bottom), target)
        if surf:
            frames.append(surf)
    return frames


# ---------------------------------------------------------------------------
# Load everything
# ---------------------------------------------------------------------------

def _load_all():
    F = _FRAMES
    S, G = _single, _grid

    # ---- player (no gun) ----
    F['p_walk_left']  = G('normal_walk_left.png',       'black', _SZ_P)
    F['p_walk_right'] = G('player_walk_right.png',      'black', _SZ_P)
    F['p_walk_fwd']   = G('player_walk_forward.png',    'black', _SZ_P)
    F['p_walk_back']  = G('player_walk_back.png',       'black', _SZ_P)

    # ---- player gun stands ----
    F['p_gun_stand_front'] = S('player_gun_stand_front.png','transparent', _SZ_P)
    F['p_gun_stand_back']  = S('player_gun_stand_back.png', 'transparent', _SZ_P)
    F['p_gun_stand_left']  = S('player_gun_stand_left.png', 'transparent', _SZ_P)
    F['p_gun_stand_right'] = S('player_gun_stand_right.png','transparent', _SZ_P)

    # ---- player gun walk ----
    F['p_gun_walk_left']  = G('player_gun_left_walk.png',    'black', _SZ_P)
    F['p_gun_walk_right'] = G('player_gun_right_walk.png',   'black', _SZ_P)
    F['p_gun_walk_fwd']   = G('player_gun_walk_forward.png', 'black', _SZ_P)
    F['p_gun_walk_back']  = G('player_gun_walk_back.png',    'black', _SZ_P)

    # ---- suit stands ----
    F['suit_stand_front'] = S('suit_gun_stand_front.png','transparent', _SZ_P)
    F['suit_stand_back']  = S('suit_gun_stand_back.png', 'transparent', _SZ_P)
    F['suit_stand_left']  = S('suit_gun_stand_left.png', 'transparent', _SZ_P)
    F['suit_stand_right'] = S('suit_gun_stand_right.png','transparent', _SZ_P)

    # ---- suit walk ----
    F['suit_walk_fwd']   = G('suit_gun_walk_front.png', 'black', _SZ_P)
    F['suit_walk_back']  = G('suit_gun_walk_back.png',  'black', _SZ_P)
    F['suit_walk_left']  = G('suit_gun_walk_left.png',  'black', _SZ_P)
    F['suit_walk_right'] = G('suit_gun_walk_right.png', 'black', _SZ_P)

    # ---- monster stands ----
    F['mon_stand_front'] = S('monster_front_stand.png', 'transparent', _SZ_M)
    F['mon_stand_back']  = S('monster_stand_back.png',  'transparent', _SZ_M)
    F['mon_stand_left']  = S('monster_stand_left.png',  'transparent', _SZ_M)
    F['mon_stand_right'] = S('monster_stand_right.png', 'transparent', _SZ_M)

    # ---- monster walk ----
    F['mon_walk_front'] = G('monster_walk_front.png', 'black', _SZ_M)
    F['mon_walk_back']  = G('monster_walk_back.png',  'black', _SZ_M)
    F['mon_walk_left']  = G('monster_walk_left.png',  'black', _SZ_M)
    F['mon_walk_right'] = G('monster_walk_right.png', 'black', _SZ_M)

    # ---- deer ----
    F['deer_stand']          = S('deer_up-right_stand.png',  'transparent', _SZ_A)
    F['deer_walk_left']      = G('deer_walk_left.png',       'transparent', _SZ_A)
    F['deer_walk_leftdown']  = G('deer_walk_left-down.png',  'transparent', _SZ_A)
    F['deer_walk_rightdown'] = G('deer_walk_right-down.png', 'transparent', _SZ_A)

    # ---- moose ----
    F['moose_left']    = S('moose_left_stand.png',    'transparent', _SZ_A)
    F['moose_upleft']  = S('moose_up-left_stand.png', 'transparent', _SZ_A)
    F['moose_upright'] = S('moose_up-right_stand.png','transparent', _SZ_A)

    # ---- rabbit ----
    F['rabbit_stand_front'] = S('rabbit_stand_front.png','transparent', _SZ_R)
    F['rabbit_stand_back']  = S('rabbit_stand_back.png', 'transparent', _SZ_R)
    F['rabbit_stand_left']  = S('rabbit_stand_left.png', 'transparent', _SZ_R)
    F['rabbit_stand_right'] = S('rabbit_stand_right.png','transparent', _SZ_R)
    F['rabbit_walk_back']   = G('rabbit_walk_back.png',  'transparent', _SZ_R)
    F['rabbit_walk_front']  = G('rabbit_walk_front.png', 'transparent', _SZ_R)
    F['rabbit_walk_left']   = G('rabbit_walk_left.png',  'black',       _SZ_R)
    F['rabbit_walk_right']  = G('rabbit_walk_right.png', 'black',       _SZ_R)

    # ---- food drops ----
    F['food_deer_meat']   = S('deer_meat.png',  'transparent', _SZ_I)
    F['food_moose_meat']  = S('moose_meat.png', 'transparent', _SZ_I)
    F['food_rabbit_meat'] = S('rabbit_meat.png','transparent', _SZ_I)

    # ---- collectible items ----
    F['item_box']     = S('box.png',    'transparent', _SZ_I)
    F['item_bullets'] = S('bullets.png','transparent', _SZ_I)
    F['item_battery'] = S('battery.png','transparent', _SZ_I)
    F['item_bullet']  = S('bullet_from_gun.png','transparent', (8, 8))

    ok  = sum(1 for v in F.values() if v)
    bad = [k for k, v in F.items() if not v]
    print(f"[sprites] {ok}/{len(F)} keys loaded.  Missing: {bad}")


def init_sprites():
    global _READY
    if _READY:
        return
    _load_all()
    _READY = True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(key):
    f = _FRAMES.get(key, [])
    return f[0] if f else None

def _anim(key, t):
    f = _FRAMES.get(key, [])
    if not f: return None
    return f[int(t * ANIM_FPS) % len(f)]

def _blit(surface, spr, rect):
    if spr is None: return False
    sw, sh = spr.get_size()
    surface.blit(spr, (rect.centerx - sw // 2, rect.centery - sh // 2))
    return True

def _dir(dx, dy):
    if abs(dx) >= abs(dy):
        return 'right' if dx > 0 else 'left'
    return 'back' if dy < 0 else 'fwd'


# ---------------------------------------------------------------------------
# Public draw functions
# ---------------------------------------------------------------------------

def draw_player(surface, rect, dx, dy, moving, has_gun, has_suit, anim_t):
    if not _READY:
        pygame.draw.rect(surface, (0, 200, 0), rect); return
    d   = _dir(dx, dy)
    pfx = 'suit' if has_suit else ('p_gun' if has_gun else 'p')
    spr = (_anim(f'{pfx}_walk_{d}', anim_t) if moving else None) \
          or _get(f'{pfx}_stand_{d}') \
          or _get('p_gun_stand_front')
    if not _blit(surface, spr, rect):
        pygame.draw.rect(surface, (0, 200, 0), rect)


def draw_monster(surface, rect, dx, dy, moving, leaving, anim_t):
    if not _READY:
        pygame.draw.rect(surface, (180,0,220) if leaving else (0,0,200), rect); return
    d   = _dir(dx, dy)
    spr = (_anim(f'mon_walk_{d}', anim_t) if moving else None) \
          or _get(f'mon_stand_{d}') \
          or _get('mon_stand_front')
    if leaving and spr:
        tinted = spr.copy()
        tinted.fill((60, 0, 60, 80), special_flags=pygame.BLEND_RGBA_ADD)
        spr = tinted
    if not _blit(surface, spr, rect):
        pygame.draw.rect(surface, (180,0,220) if leaving else (0,0,200), rect)


def draw_animal(surface, rect, animal_type, dx, dy, moving, anim_t):
    if not _READY:
        pygame.draw.rect(surface, (125,100,10), rect); return
    d   = _dir(dx, dy)
    spr = None
    if animal_type == ANIMAL_DEER:
        wmap = {'left':'deer_walk_left','back':'deer_walk_leftdown',
                'right':'deer_walk_rightdown','fwd':'deer_walk_rightdown'}
        spr  = (_anim(wmap.get(d,'deer_walk_left'), anim_t) if moving else None) \
               or _get('deer_stand')
    elif animal_type == ANIMAL_MOOSE:
        smap = {'left':'moose_left','back':'moose_upleft',
                'right':'moose_upright','fwd':'moose_left'}
        spr  = _get(smap.get(d, 'moose_left'))
    elif animal_type == ANIMAL_RABBIT:
        wmap = {'left':'rabbit_walk_left','right':'rabbit_walk_right',
                'back':'rabbit_walk_back','fwd':'rabbit_walk_front'}
        smap = {'left':'rabbit_stand_left','right':'rabbit_stand_right',
                'back':'rabbit_stand_back','fwd':'rabbit_stand_front'}
        spr  = (_anim(wmap.get(d,'rabbit_walk_front'), anim_t) if moving else None) \
               or _get(smap.get(d,'rabbit_stand_front'))
    if not _blit(surface, spr, rect):
        pygame.draw.rect(surface, (125,100,10), rect)


_FOOD_KEYS = {
    'deer_meat':   'food_deer_meat',
    'moose_meat':  'food_moose_meat',
    'rabbit_meat': 'food_rabbit_meat',
}

def draw_food(surface, rect, item_id='food_can'):
    spr = _get(_FOOD_KEYS.get(item_id, ''))
    if not _blit(surface, spr, rect):
        pygame.draw.rect(surface, (255, 100, 100), rect)


_BOX_COLORS = {
    'health_pack':(120,220,130), 'food_can':(255,170,90),
    'rad_pill':(255,130,180),    'map_fragment':(95,205,255), 'key':(255,215,90),
}

def draw_item_box(surface, rect, item_id, collected):
    spr = _get('item_box')
    if collected:
        dark = spr.copy() if spr else None
        if dark:
            dark.fill((100,100,100,180), special_flags=pygame.BLEND_RGBA_MULT)
        if not _blit(surface, dark, rect):
            pygame.draw.rect(surface, (70,70,80), rect)
        pygame.draw.rect(surface, (255,255,255), rect, 2)
        return
    if not _blit(surface, spr, rect):
        pygame.draw.rect(surface, _BOX_COLORS.get(item_id,(160,95,45)), rect)
        pygame.draw.rect(surface, (255,255,255), rect, 2)
        pygame.draw.rect(surface, (255,255,255), pygame.Rect(rect.x+8,rect.y+8,16,16))
    else:
        pygame.draw.rect(surface, (255,255,255), rect, 2)


def draw_bullet(surface, x, y, radius):
    spr = _get('item_bullet')
    if spr:
        surface.blit(spr, (int(x)-spr.get_width()//2, int(y)-spr.get_height()//2))
    else:
        pygame.draw.circle(surface, (255,220,50), (int(x),int(y)), radius)


# ---------------------------------------------------------------------------
# Zone tile renderer — colour-based (unchanged public API)
# ---------------------------------------------------------------------------
TILE_EMPTY   = 0
TILE_WALL    = 1
TILE_OBJECT  = 2
ZONE_FACTORY = 0
ZONE_FOREST  = 1

_PALETTE = {
    ZONE_FACTORY: {TILE_WALL:((52,52,62),(78,78,93)),   TILE_OBJECT:((90,60,25),(140,100,45))},
    ZONE_FOREST:  {TILE_WALL:((32,62,28),(52,95,42)),   TILE_OBJECT:((75,50,18),(115,80,32))},
}

class ZoneRenderer:
    def render_tile(self, surface, tile_id, zone_type, rx, ry, tw, th):
        if tile_id == TILE_EMPTY: return
        pal  = _PALETTE.get(zone_type, _PALETTE[ZONE_FACTORY])
        fill, border = pal.get(tile_id, ((100,100,100),(140,140,140)))
        if tile_id == TILE_OBJECT:
            px = max(1,tw//6); py = max(1,th//6)
            pygame.draw.rect(surface, fill,   (rx+px,ry+py,tw-px*2,th-py*2))
            pygame.draw.rect(surface, border, (rx+px,ry+py,tw-px*2,th-py*2), 2)
        else:
            pygame.draw.rect(surface, fill,   (rx,ry,tw,th))
            pygame.draw.rect(surface, border, (rx,ry,tw,th), 2)

    def render(self, surface, zx, zy, zone_type):
        from map_data import get_zone_grid, MAP_WIDTH, MAP_HEIGHT
        from config import MAP_WIDTH as MW, MAP_HEIGHT as MH
        grid = get_zone_grid(zx, zy)
        if not grid: return
        rows = len(grid); cols = len(grid[0]) if rows else 1
        tw = MW // cols; th = MH // rows
        for ty, row in enumerate(grid):
            for tx, tile in enumerate(row):
                if tile != TILE_EMPTY:
                    self.render_tile(surface, tile, zone_type, tx*tw, ty*th, tw, th)

    # alias for compatibility
    def render_zone(self, surface, grid, zone_type, map_w, map_h):
        if not grid: return
        rows = len(grid); cols = len(grid[0]) if rows else 1
        tw = map_w // cols; th = map_h // rows
        for ty, row in enumerate(grid):
            for tx, tile in enumerate(row):
                if tile != TILE_EMPTY:
                    self.render_tile(surface, tile, zone_type, tx*tw, ty*th, tw, th)

    def clear_cache(self): pass

ZONE_RENDERER = ZoneRenderer()