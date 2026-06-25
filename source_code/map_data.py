"""
map_data.py — Map and item data loader for Project Orin
========================================================

All zone layouts, doors, world_map, radiation_map, and item_positions are
pre-baked into map.json.  Every zone has an explicit tile grid in zone_tiles;
if one is somehow missing, an empty grid is returned as a safe fallback.

map.json structure
------------------
  world_map        — 2-D list [zy][zx] of raw zone type IDs (0-4 legacy, see below)
  zone_tiles       — dict  "zx,zy" -> 17×21 tile grid  (explicit overrides)
  zone_doors       — dict  "zx,zy" -> list of door side names
  radiation_map    — 2-D list [zy][zx] of radiation levels (0-6)
  item_positions   — dict  "zx,zy" -> list of item placement dicts

Tile IDs
--------
  TILE_EMPTY  = 0
  TILE_WALL   = 1
  TILE_OBJECT = 2

Zone types  (simplified — two types only)
------------------------------------------
  ZONE_FACTORY = 0   (factory, ruins, wasteland, or any industrial feel)
  ZONE_FOREST  = 1   (forest, jungle, overgrown areas)

  Raw world_map values 0, 2, 3, 4 all map to ZONE_FACTORY.
  Raw world_map value  1           maps to ZONE_FOREST.

Zone sub-types  (door-set based, computed by get_zone_subtype)
---------------------------------------------------------------------
  A zone sub-type describes which sides have doors.  Examples:
    "NS"   — corridor running north-south
    "EW"   — corridor running east-west
    "NSEW" — crossroads (all four sides open)
    "NE"   — corner     (north + east)
    "N"    — dead end   (north only)
  Sub-types are used to select the right tile template / sprite variant.

Public API
----------
  get_zone_type(zx, zy)        → int   (ZONE_FACTORY or ZONE_FOREST)
  get_zone_subtype(zx, zy)     → str   (e.g. "NS", "NSEW", "NE", …)
  get_zone_grid(zx, zy)        → list[list[int]]   17 rows × 21 cols
  get_zone_doors(zx, zy)       → list[str]
  get_tile(zx, zy, tx, ty)     → int
  set_tile(zx, zy, tx, ty, v)
  get_items_in_zone(zx, zy)    → list[dict]
  get_item_def(item_id)        → dict
  get_zone_radiation(zx, zy)   → float
"""

import os
import json

from config import ZONE_COUNT_X, ZONE_COUNT_Y, MAP_WIDTH, MAP_HEIGHT

# ---------------------------------------------------------------------------
# Paths  (file sits next to the script, or one level up in data/)
# ---------------------------------------------------------------------------
_SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR   = os.path.join(os.path.dirname(_SOURCE_DIR), "data")


def _find(name):
    for path in (os.path.join(_SOURCE_DIR, name), os.path.join(_DATA_DIR, name)):
        if os.path.isfile(path):
            return path
    return os.path.join(_SOURCE_DIR, name)   # fallback — will fail loudly if missing


MAP_JSON   = _find("map.json")
ITEMS_JSON = _find("items.json")

# ---------------------------------------------------------------------------
# Tile grid dimensions
# ---------------------------------------------------------------------------
ZONE_TILE_WIDTH  = 21
ZONE_TILE_HEIGHT = 17
UNIT_W = MAP_WIDTH  // ZONE_TILE_WIDTH
UNIT_H = MAP_HEIGHT // ZONE_TILE_HEIGHT

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TILE_EMPTY  = 0
TILE_WALL   = 1
TILE_OBJECT = 2

ZONE_FACTORY = 0
ZONE_FOREST  = 1

# Raw world_map values -> canonical zone type
_RAW_TO_ZONE_TYPE: dict[int, int] = {
    0: ZONE_FACTORY,   # default / industrial
    1: ZONE_FOREST,    # forest
    2: ZONE_FACTORY,   # ruins  (industrial remains)
    3: ZONE_FACTORY,   # wasteland
    4: ZONE_FACTORY,   # water-edge / hazard
}


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def _load_map():
    with open(MAP_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    world_map     = data.get("world_map",     [[ZONE_FACTORY] * ZONE_COUNT_X] * ZONE_COUNT_Y)
    radiation_map = data.get("radiation_map", [[1] * ZONE_COUNT_X] * ZONE_COUNT_Y)
    item_positions = data.get("item_positions", {})

    # zone_tiles: convert "zx,zy" string keys to indexed 2-D list (None = use template)
    raw_tiles  = data.get("zone_tiles", {})
    zone_tiles = [[None] * ZONE_COUNT_X for _ in range(ZONE_COUNT_Y)]
    for key, grid in raw_tiles.items():
        zx, zy = map(int, key.split(","))
        if 0 <= zx < ZONE_COUNT_X and 0 <= zy < ZONE_COUNT_Y:
            zone_tiles[zy][zx] = grid

    # zone_doors: same pattern
    raw_doors  = data.get("zone_doors", {})
    zone_doors = [[[] for _ in range(ZONE_COUNT_X)] for _ in range(ZONE_COUNT_Y)]
    for key, doors in raw_doors.items():
        zx, zy = map(int, key.split(","))
        if 0 <= zx < ZONE_COUNT_X and 0 <= zy < ZONE_COUNT_Y:
            zone_doors[zy][zx] = doors

    return world_map, zone_tiles, zone_doors, radiation_map, item_positions


def _load_items():
    if not os.path.isfile(ITEMS_JSON):
        return {}
    with open(ITEMS_JSON, "r") as f:
        return json.load(f)


# Module-level data loaded once at import time
WORLD_MAP, ZONE_TILES, ZONE_DOORS, RADIATION_MAP, ITEM_POSITIONS = _load_map()
ITEM_DEFS = _load_items()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_zone_type(zone_x: int, zone_y: int) -> int:
    """Return ZONE_FACTORY (0) or ZONE_FOREST (1) for the given zone."""
    raw = WORLD_MAP[zone_y][zone_x]
    return _RAW_TO_ZONE_TYPE.get(raw, ZONE_FACTORY)


_SIDE_ORDER = ("N", "S", "E", "W")
_SIDE_ABBR  = {"north": "N", "south": "S", "east": "E", "west": "W"}


def get_zone_subtype(zone_x: int, zone_y: int) -> str:
    """
    Return the door-set sub-type string for the zone, e.g. 'NS', 'NSEW', 'NE'.

    Derived from the zone's door list; useful for selecting sprite variants.
    """
    letters = {_SIDE_ABBR[d] for d in ZONE_DOORS[zone_y][zone_x] if d in _SIDE_ABBR}
    return "".join(s for s in _SIDE_ORDER if s in letters) or "NONE"


def get_zone_doors(zone_x: int, zone_y: int) -> list:
    return ZONE_DOORS[zone_y][zone_x] or []


_EMPTY_GRID = [[TILE_EMPTY] * ZONE_TILE_WIDTH for _ in range(ZONE_TILE_HEIGHT)]


def get_zone_grid(zone_x: int, zone_y: int) -> list:
    """Return the 17×21 tile grid for the zone from map.json."""
    grid = ZONE_TILES[zone_y][zone_x]
    return grid if grid is not None else _EMPTY_GRID


def get_tile(zone_x: int, zone_y: int, tile_x: int, tile_y: int) -> int:
    return get_zone_grid(zone_x, zone_y)[tile_y][tile_x]


def set_tile(zone_x: int, zone_y: int, tile_x: int, tile_y: int, tile_id: int):
    """Overwrite a tile at runtime (in-memory only, does not persist to disk)."""
    grid = ZONE_TILES[zone_y][zone_x]
    if grid is not None:
        grid[tile_y][tile_x] = tile_id


def get_item_def(item_id: str) -> dict:
    return ITEM_DEFS.get(item_id, {})


def get_items_in_zone(zone_x: int, zone_y: int) -> list:
    return ITEM_POSITIONS.get(f"{zone_x},{zone_y}", [])


def get_zone_radiation(zone_x: int, zone_y: int) -> float:
    try:
        return float(RADIATION_MAP[zone_y][zone_x])
    except (IndexError, TypeError):
        return 1.0
