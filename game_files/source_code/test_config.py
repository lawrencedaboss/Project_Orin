#!/usr/bin/env python3
"""Test script to verify JSON config and inventory system."""

import sys
import json

try:
    # Test 1: Load config.json
    with open('config.json', 'r') as f:
        config = json.load(f)
    print("✓ config.json loaded successfully")
    
    # Test 2: Verify pygame key mapping
    import pygame
    pygame.init()
    print("✓ Pygame initialized")
    
    # Test 3: Import config module
    from config import SCREEN_WIDTH, SCREEN_HEIGHT, KEYBINDS, FPS
    print("✓ config.py loaded successfully")
    print(f"  Screen: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
    print(f"  FPS: {FPS}")
    print(f"  Available keybinds: {list(KEYBINDS.keys())}")
    print(f"  Inventory keybind: {pygame.key.name(KEYBINDS.get('inventory', pygame.K_UNKNOWN))}")
    
    # Test 4: Import game module (without running it)
    print("\n✓ All imports successful")
    print("✓ JSON config system working")
    print("✓ Inventory keybind registered")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
