
"""
map_data.py — Map and item data loader for Project Orin
========================================================
 
All zone layouts, doors, world_map, radiation_map, and item_positions are
pre-baked into map.json.  There is no runtime procedural generation.
 
map.json structure:
  world_map        — 2-D list [zy][zx] of zone type IDs
  zone_tiles       — dict  "zx,zy" -> 17×21 tile grid
  zone_doors       — dict  "zx,zy" -> list of door side names
  radiation_map    — 2-D list [zy][zx] of radiation levels (0-6)
  item_positions   — dict  "zx,zy" -> list of item placement dicts
 
Tile IDs:   TILE_EMPTY=0  TILE_WALL=1  TILE_OBJECT=2
Zone types: ZONE_DEFAULT=0  ZONE_FOREST=1  ZONE_RUINS=2
            ZONE_WASTELAND=3  ZONE_WATER=4
 
Public API:
    get_zone_type(zx, zy)        → int
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
    return os.path.join(_SOURCE_DIR, name)   # fallback (will fail loudly if missing)
 
 
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
 
ZONE_FACTORY  = 0
ZONE_FOREST    = 1

 
# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
def _load_map():
    with open(MAP_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
 
    world_map     = data.get("world_map",     [[ZONE_FACTORY]*ZONE_COUNT_X]*ZONE_COUNT_Y)
    radiation_map = data.get("radiation_map", [[1]*ZONE_COUNT_X]*ZONE_COUNT_Y)
    item_positions= data.get("item_positions",{})
 
    # zone_tiles: convert string keys back to indexed access
    raw_tiles = data.get("zone_tiles", {})
    zone_tiles = [[None]*ZONE_COUNT_X for _ in range(ZONE_COUNT_Y)]
    for key, grid in raw_tiles.items():
        zx, zy = map(int, key.split(","))
        if 0 <= zx < ZONE_COUNT_X and 0 <= zy < ZONE_COUNT_Y:
            zone_tiles[zy][zx] = grid
 
    raw_doors = data.get("zone_doors", {})
    zone_doors = [[[]]*ZONE_COUNT_X for _ in range(ZONE_COUNT_Y)]
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
# Fallback empty grid (returned if a zone has no data — should not happen)
# ---------------------------------------------------------------------------
_EMPTY_GRID = [[TILE_EMPTY]*ZONE_TILE_WIDTH for _ in range(ZONE_TILE_HEIGHT)]
 
# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_zone_type(zone_x: int, zone_y: int) -> int:
    return WORLD_MAP[zone_y][zone_x]
 
 
def get_zone_grid(zone_x: int, zone_y: int):
    grid = ZONE_TILES[zone_y][zone_x]
    return grid if grid is not None else _EMPTY_GRID
 
 
def get_zone_doors(zone_x: int, zone_y: int) -> list:
    return ZONE_DOORS[zone_y][zone_x] or []
 
 
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