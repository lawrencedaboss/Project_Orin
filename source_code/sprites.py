"""
sprites.py — Sprite-sheet loader and zone renderer for Project Orin
====================================================================

Drop a sprite-sheet PNG into  <project_root>/assets/sprites/tiles.png
and configure TILE_SPRITE_MAP to match your sheet layout.

The game runs fine without the file — it falls back to solid-colour
rectangles so you can develop and test before any art exists.

Zone-type colour palettes
--------------------------
  ZONE_FACTORY  — dark steel / concrete  (grey-blue tones)
  ZONE_FOREST   — bark / leaves          (green-brown tones)

Sprite-sheet layout (tiles.png)
--------------------------------
  Row 0 : factory tiles   col 0=wall, col 1=object, col 2=floor (optional)
  Row 1 : forest  tiles   col 0=wall, col 1=object, col 2=floor (optional)

  Each cell in the sheet is SPRITE_TILE_W × SPRITE_TILE_H pixels.
  Edit SPRITE_TILE_W / SPRITE_TILE_H to match your actual sheet.

Public API
----------
  SpriteSheet(path, tile_w, tile_h)
      .loaded          -> bool
      .get_sprite(col, row, scale_to=None) -> pygame.Surface | None

  ZoneRenderer(sheet=None)
      .render_tile(surface, tile_id, zone_type, rx, ry, tile_w, tile_h)
      .render_zone(surface, grid, zone_type, map_w, map_h)

  ZONE_RENDERER   — module-level singleton; import and use anywhere:

      from sprites import ZONE_RENDERER
      ZONE_RENDERER.render_zone(screen, grid, zone_type, MAP_WIDTH, MAP_HEIGHT)
"""

import os
import pygame

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SOURCE_DIR  = os.path.dirname(os.path.abspath(__file__))
_ASSETS_DIR  = os.path.join(os.path.dirname(_SOURCE_DIR), "assets", "sprites")
_SHEET_PATH  = os.path.join(_ASSETS_DIR, "tiles.png")

# ---------------------------------------------------------------------------
# Tile / zone constants  (mirrors map_data.py — kept local to avoid import)
# ---------------------------------------------------------------------------
TILE_EMPTY   = 0
TILE_WALL    = 1
TILE_OBJECT  = 2

ZONE_FACTORY = 0
ZONE_FOREST  = 1

# ---------------------------------------------------------------------------
# Sprite-sheet cell size (pixels in the source PNG per tile frame)
# Change these to match your actual sprite sheet.
# ---------------------------------------------------------------------------
SPRITE_TILE_W = 16
SPRITE_TILE_H = 16

# ---------------------------------------------------------------------------
# Mapping: (zone_type, tile_id) -> (sheet_col, sheet_row)
# Edit to match your sheet layout.
# ---------------------------------------------------------------------------
TILE_SPRITE_MAP: dict[tuple, tuple] = {
    (ZONE_FACTORY, TILE_WALL):   (0, 0),
    (ZONE_FACTORY, TILE_OBJECT): (1, 0),
    (ZONE_FOREST,  TILE_WALL):   (0, 1),
    (ZONE_FOREST,  TILE_OBJECT): (1, 1),
}

# ---------------------------------------------------------------------------
# Fallback colour palettes  (fill_colour, border_colour)
# Used when no sprite sheet is present.
# ---------------------------------------------------------------------------
_PALETTE: dict[int, dict[int, tuple]] = {
    ZONE_FACTORY: {
        TILE_WALL:   ((52,  52,  62),  (78,  78,  93)),
        TILE_OBJECT: ((90,  60,  25),  (140, 100, 45)),
    },
    ZONE_FOREST: {
        TILE_WALL:   ((32,  62,  28),  (52,  95,  42)),
        TILE_OBJECT: ((75,  50,  18),  (115, 80,  32)),
    },
}


# ===========================================================================
# SpriteSheet
# ===========================================================================
class SpriteSheet:
    """
    Loads a PNG sprite sheet and slices it into fixed-size frames.

    Parameters
    ----------
    sheet_path  : path to the PNG (may not exist yet)
    tile_w      : pixel width  of each sprite frame in the sheet
    tile_h      : pixel height of each sprite frame in the sheet
    """

    def __init__(self, sheet_path: str, tile_w: int, tile_h: int):
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
                pass   # pygame not yet initialized or corrupted file — silent fallback

    @property
    def loaded(self) -> bool:
        """True if the sprite sheet PNG was found and loaded successfully."""
        return self._loaded

    def get_sprite(self, col: int, row: int,
                   scale_to: tuple | None = None) -> "pygame.Surface | None":
        """
        Return a Surface for the frame at grid position (col, row).

        scale_to : optional (width, height) to scale the sprite to.
                   Pass the on-screen tile size so sprites scale cleanly.
        Returns None if the sheet was not loaded.
        """
        if not self._loaded:
            return None

        src_rect = pygame.Rect(
            col * self._tile_w,
            row * self._tile_h,
            self._tile_w,
            self._tile_h,
        )
        sprite = pygame.Surface((self._tile_w, self._tile_h), pygame.SRCALPHA)
        sprite.blit(self._sheet, (0, 0), src_rect)

        if scale_to and scale_to != (self._tile_w, self._tile_h):
            sprite = pygame.transform.scale(sprite, scale_to)
        return sprite


# ===========================================================================
# ZoneRenderer
# ===========================================================================
class ZoneRenderer:
    """
    Renders zone tiles to a pygame Surface.

    Tries the sprite sheet first; falls back to solid-colour rectangles
    if no sheet is available so the game always runs without art assets.

    Parameters
    ----------
    sheet : SpriteSheet instance, or None to force colour fallback
    """

    def __init__(self, sheet: "SpriteSheet | None" = None):
        self._sheet  = sheet
        self._cache: dict = {}    # (zone_type, tile_id, w, h) -> Surface | None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_cached_surface(self, zone_type: int, tile_id: int,
                            tile_w: int, tile_h: int) -> "pygame.Surface | None":
        key = (zone_type, tile_id, tile_w, tile_h)
        if key not in self._cache:
            surf = None
            if self._sheet and self._sheet.loaded:
                pos = TILE_SPRITE_MAP.get((zone_type, tile_id))
                if pos:
                    surf = self._sheet.get_sprite(pos[0], pos[1],
                                                  scale_to=(tile_w, tile_h))
            self._cache[key] = surf
        return self._cache[key]

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def render_tile(self, surface: "pygame.Surface", tile_id: int,
                    zone_type: int, rx: int, ry: int,
                    tile_w: int, tile_h: int) -> None:
        """Draw a single tile at pixel position (rx, ry) on *surface*."""
        if tile_id == TILE_EMPTY:
            return

        sprite = self._get_cached_surface(zone_type, tile_id, tile_w, tile_h)
        if sprite is not None:
            surface.blit(sprite, (rx, ry))
            return

        # ---- colour fallback ----
        zpal  = _PALETTE.get(zone_type, _PALETTE[ZONE_FACTORY])
        fill, border = zpal.get(tile_id, ((100, 100, 100), (140, 140, 140)))

        if tile_id == TILE_OBJECT:
            # Inset the object rect slightly so it looks distinct from walls
            pad_x = max(1, tile_w // 6)
            pad_y = max(1, tile_h // 6)
            pygame.draw.rect(surface, fill,
                             (rx + pad_x, ry + pad_y,
                              tile_w - pad_x * 2, tile_h - pad_y * 2))
            pygame.draw.rect(surface, border,
                             (rx + pad_x, ry + pad_y,
                              tile_w - pad_x * 2, tile_h - pad_y * 2), 2)
        else:
            pygame.draw.rect(surface, fill,   (rx, ry, tile_w, tile_h))
            pygame.draw.rect(surface, border, (rx, ry, tile_w, tile_h), 2)

    def render_zone(self, surface: "pygame.Surface", grid: list,
                    zone_type: int, map_w: int, map_h: int) -> None:
        """
        Render every non-empty tile in *grid* onto *surface*.

        grid      : 2-D list[list[int]] — the zone's tile array
        zone_type : ZONE_FACTORY or ZONE_FOREST
        map_w / map_h : pixel dimensions of the playfield area
        """
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
                                     tx * tile_w, ty * tile_h,
                                     tile_w, tile_h)

    def clear_cache(self) -> None:
        """Call if the sprite sheet is reloaded at runtime."""
        self._cache.clear()


# ===========================================================================
# Module-level singleton
# ===========================================================================
def _build_default_renderer() -> ZoneRenderer:
    sheet = SpriteSheet(_SHEET_PATH, SPRITE_TILE_W, SPRITE_TILE_H)
    return ZoneRenderer(sheet)


ZONE_RENDERER: ZoneRenderer = _build_default_renderer()
