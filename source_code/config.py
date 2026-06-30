"""
Game configuration loaded from config.json
Edit config.json to customize settings and controls.
"""

import json
import os
import pygame

# Load configuration from JSON
CONFIG_DIR = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
with open(CONFIG_PATH, 'r') as f:
    _config = json.load(f)

# Game settings
SCREEN_WIDTH = _config['game']['screen_width']
SCREEN_HEIGHT = _config['game']['screen_height']
UI_HEIGHT = 80
BOTTOM_MARGIN = 40
MAP_WIDTH = SCREEN_WIDTH - 120
MAP_HEIGHT = SCREEN_HEIGHT - UI_HEIGHT - BOTTOM_MARGIN-2
MAP_LEFT = (SCREEN_WIDTH - MAP_WIDTH) // 2
MAP_TOP = UI_HEIGHT + (SCREEN_HEIGHT - UI_HEIGHT - MAP_HEIGHT) // 2
ZONE_COUNT_X = _config['game']['zone_count_x']
ZONE_COUNT_Y = _config['game']['zone_count_y']
FPS = _config['game']['fps']
ANIMAL_COUNT = _config['game']['animal_count']

# Map string key names to pygame constants
_KEY_MAP = {
    'a': pygame.K_a, 'b': pygame.K_b, 'c': pygame.K_c, 'd': pygame.K_d, 'e': pygame.K_e,
    'f': pygame.K_f, 'g': pygame.K_g, 'h': pygame.K_h, 'i': pygame.K_i, 'j': pygame.K_j,
    'k': pygame.K_k, 'l': pygame.K_l, 'm': pygame.K_m, 'n': pygame.K_n, 'o': pygame.K_o,
    'p': pygame.K_p, 'q': pygame.K_q, 'r': pygame.K_r, 's': pygame.K_s, 't': pygame.K_t,
    'u': pygame.K_u, 'v': pygame.K_v, 'w': pygame.K_w, 'x': pygame.K_x, 'y': pygame.K_y,
    'z': pygame.K_z,
    'up': pygame.K_UP, 'down': pygame.K_DOWN, 'left': pygame.K_LEFT, 'right': pygame.K_RIGHT,
    'escape': pygame.K_ESCAPE, 'space': pygame.K_SPACE, 'enter': pygame.K_RETURN,
    '0': pygame.K_0, '1': pygame.K_1, '2': pygame.K_2, '3': pygame.K_3, '4': pygame.K_4,
    '5': pygame.K_5, '6': pygame.K_6, '7': pygame.K_7, '8': pygame.K_8, '9': pygame.K_9,
}

# Keybinds - Loaded from JSON
KEYBINDS = {}
for action, key_name in _config['keybinds'].items():
    KEYBINDS[action] = _KEY_MAP.get(key_name.lower(), pygame.K_UNKNOWN)

# Game balance settings
MONSTER_SPEED = _config['balance']['monster_speed']
MONSTER_WANDER_SPEED = _config['balance']['monster_wander_speed']
ANIMAL_SPEED = _config['balance']['animal_speed']
ANIMAL_WANDER_INTERVAL_MIN = _config['balance']['animal_wander_interval_min']
ANIMAL_WANDER_INTERVAL_MAX = _config['balance']['animal_wander_interval_max']

PLAYER_BASE_SPEED = _config['balance']['player_base_speed']
HUNGER_RATE = _config['balance']['hunger_rate']
HUNGER_SPEED_MULTIPLIER = _config['balance']['hunger_speed_multiplier']
RADIATION_RATE = _config['balance']['radiation_rate']
RADIATION_MAX = _config['balance']['radiation_max']
FOOD_HUNGER_RESTORE = _config['balance'].get('food_hunger_restore', 20)

# Starting values
PLAYER_START_X = _config['player']['start_x']
PLAYER_START_Y = _config['player']['start_y']
PLAYER_HUNGER_START = _config['player']['hunger_start']
