"""
map_data.py — Map and item data loader for Project Orin
========================================================

Each loading zone is divided into a 21 × 17 grid of "units".
Each unit is UNIT_W × UNIT_H pixels and holds one of three values:

    TILE_EMPTY  = 0   walkable, nothing drawn
    TILE_WALL   = 1   impassable solid block
    TILE_OBJECT = 2   item / interactable marker

Folder layout:

    game_files/
    ├── source_code/
    │   └── map_data.py      ← this file
    └── data/
        ├── map.json          ← world map + per-zone tile grids
        ├── items.json        ← item definitions
        └── item_positions.json ← item placements per zone

Public API:
    get_zone_type(zx, zy)              → int
    get_tile(zx, zy, tx, ty)          → int   (tx 0-7, ty 0-5)
    set_tile(zx, zy, tx, ty, tile_id)
    get_zone_grid(zx, zy)             → list[list[int]]   6 rows × 8 cols
    get_items_in_zone(zx, zy)         → list[dict]
    get_item_def(item_id)             → dict
"""

import os
import json

from config import ZONE_COUNT_X, ZONE_COUNT_Y, MAP_WIDTH, MAP_HEIGHT

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR   = os.path.join(os.path.dirname(_SOURCE_DIR), "data")

MAP_JSON            = os.path.join(_DATA_DIR, "map.json")
ITEMS_JSON          = os.path.join(_DATA_DIR, "items.json")
ITEM_POSITIONS_JSON = os.path.join(_DATA_DIR, "item_positions.json")


# ---------------------------------------------------------------------------
# Tile grid dimensions — 21 units wide, 17 units tall per loading zone
# ---------------------------------------------------------------------------
ZONE_TILE_WIDTH  = 21
ZONE_TILE_HEIGHT = 17
UNIT_W = MAP_WIDTH  // (ZONE_TILE_WIDTH + 1)   # pixels per unit
UNIT_H = MAP_HEIGHT // (ZONE_TILE_HEIGHT + 1)    # pixels per unit


# ---------------------------------------------------------------------------
# Tile ID constants
# ---------------------------------------------------------------------------
TILE_EMPTY  = 0   # walkable, nothing drawn
TILE_WALL   = 1   # solid, impassable
TILE_OBJECT = 2   # item / interactable


# ---------------------------------------------------------------------------
# Zone type ID constants  (used in world_map)
# ---------------------------------------------------------------------------
ZONE_DEFAULT   = 0
ZONE_FOREST    = 1
ZONE_RUINS     = 2
ZONE_WASTELAND = 3
ZONE_WATER     = 4


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _empty_zone():
    return [[TILE_EMPTY] * ZONE_TILE_WIDTH for _ in range(ZONE_TILE_HEIGHT)]


def _default_world_map():
    return [[ZONE_DEFAULT] * ZONE_COUNT_X for _ in range(ZONE_COUNT_Y)]


def _default_zone_tiles():
    return [[_empty_zone() for _ in range(ZONE_COUNT_X)]
            for _ in range(ZONE_COUNT_Y)]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load_map():
    world_map  = _default_world_map()
    zone_tiles = _default_zone_tiles()

    if not os.path.isfile(MAP_JSON):
        return world_map, zone_tiles

    with open(MAP_JSON, "r") as f:
        data = json.load(f)

    if "world_map" in data:
        world_map = data["world_map"]

    for key, grid in data.get("zone_tiles", {}).items():
        zx, zy = map(int, key.split(","))
        if 0 <= zx < ZONE_COUNT_X and 0 <= zy < ZONE_COUNT_Y:
            zone_tiles[zy][zx] = grid

    return world_map, zone_tiles


def _load_items():
    if not os.path.isfile(ITEMS_JSON):
        return {}
    with open(ITEMS_JSON, "r") as f:
        return json.load(f)


def _load_item_positions():
    if not os.path.isfile(ITEM_POSITIONS_JSON):
        return {}
    with open(ITEM_POSITIONS_JSON, "r") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Module-level data
# ---------------------------------------------------------------------------
WORLD_MAP, ZONE_TILES = _load_map()
ITEM_DEFS             = _load_items()
ITEM_POSITIONS        = _load_item_positions()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_zone_type(zone_x: int, zone_y: int) -> int:
    return WORLD_MAP[zone_y][zone_x]


def get_zone_grid(zone_x: int, zone_y: int):
    """Return the full 6-row × 8-col tile grid for a loading zone."""
    return ZONE_TILES[zone_y][zone_x]


def get_tile(zone_x: int, zone_y: int, tile_x: int, tile_y: int) -> int:
    return ZONE_TILES[zone_y][zone_x][tile_y][tile_x]


def set_tile(zone_x: int, zone_y: int, tile_x: int, tile_y: int, tile_id: int):
    """Overwrite a tile at runtime (does not save to disk)."""
    ZONE_TILES[zone_y][zone_x][tile_y][tile_x] = tile_id


def get_item_def(item_id: str) -> dict:
    return ITEM_DEFS.get(item_id, {})


def get_items_in_zone(zone_x: int, zone_y: int) -> list:
    return ITEM_POSITIONS.get(f"{zone_x},{zone_y}", [])
