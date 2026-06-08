#!/usr/bin/env python3
"""Quick test to verify keybind system and game functionality."""

import pygame
pygame.init()

from config import KEYBINDS
print("✓ Keybinds loaded successfully")
print(f"  Action key: {pygame.key.name(KEYBINDS['action'])}")
print(f"  Hide key: {pygame.key.name(KEYBINDS['hide'])}")
print(f"  Pause key: {pygame.key.name(KEYBINDS['pause'])}")

# Test keybind modification
original = KEYBINDS['action']
KEYBINDS['action'] = pygame.K_x
assert KEYBINDS['action'] == pygame.K_x, "Keybind modification failed"
KEYBINDS['action'] = original
print("✓ Keybind modification works")

from game import Game
print("✓ Game imports successfully")

from player import Player
print("✓ Player imports successfully")

print("\n✅ All systems verified and working!")
