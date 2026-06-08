#!/usr/bin/env python3
"""Debug keybinds."""

import pygame
pygame.init()

try:
    from config import KEYBINDS
    print("✓ Config loaded")
    print("\nAll keybinds:")
    for action, key in sorted(KEYBINDS.items()):
        key_name = pygame.key.name(key)
        print(f"  {action:15} -> {key_name:10} (code: {key})")
    
    print(f"\n--- Inventory Keybind ---")
    inv_key = KEYBINDS.get('inventory')
    if inv_key is None:
        print("✗ ERROR: inventory keybind is None!")
    else:
        print(f"✓ Inventory key: {pygame.key.name(inv_key)} (code: {inv_key})")
    
    # Check if all expected keybinds are present
    expected = ['pause', 'hide', 'action', 'inventory', 'exit', 'move_up', 'move_down', 'move_left', 'move_right']
    print(f"\n--- Keybind Validation ---")
    for action in expected:
        if action in KEYBINDS:
            print(f"✓ {action}")
        else:
            print(f"✗ MISSING: {action}")
            
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
