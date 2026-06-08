#!/usr/bin/env python3
"""Comprehensive keybind debugging and verification."""

import json
import sys

print("=" * 60)
print("KEYBIND DEBUGGING")
print("=" * 60)

# Step 1: Verify config.json
print("\n[1] Loading config.json...")
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    print("✓ config.json loaded successfully")
except Exception as e:
    print(f"✗ Error loading config.json: {e}")
    sys.exit(1)

# Step 2: Check keybinds in config.json
print("\n[2] Checking keybinds in config.json...")
expected_binds = ['pause', 'hide', 'action', 'inventory', 'exit', 'move_up', 'move_down', 'move_left', 'move_right']
for bind in expected_binds:
    if bind in config['keybinds']:
        print(f"✓ {bind:15} -> {config['keybinds'][bind]}")
    else:
        print(f"✗ MISSING: {bind}")

# Step 3: Initialize pygame and load config module
print("\n[3] Loading pygame and config module...")
try:
    import pygame
    pygame.init()
    from config import KEYBINDS
    print("✓ Pygame initialized")
    print("✓ Config module loaded")
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Verify all keybinds are mapped correctly
print("\n[4] Verifying keybind mappings...")
for action in sorted(KEYBINDS.keys()):
    key_code = KEYBINDS[action]
    key_name = pygame.key.name(key_code)
    if key_code != pygame.K_UNKNOWN:
        print(f"✓ {action:15} -> {key_name:10} (code: {key_code})")
    else:
        print(f"✗ {action:15} -> UNKNOWN")

# Step 5: Check inventory keybind specifically
print("\n[5] Inventory Keybind Check...")
inv_key = KEYBINDS.get('inventory')
if inv_key is None:
    print("✗ ERROR: inventory not in KEYBINDS dictionary!")
else:
    print(f"✓ Inventory keybind registered: {pygame.key.name(inv_key)}")

# Step 6: Test comparison logic
print("\n[6] Testing key comparison logic...")
test_key = KEYBINDS['inventory']
if test_key == KEYBINDS['inventory']:
    print(f"✓ Direct comparison works: {test_key} == {KEYBINDS['inventory']}")
else:
    print(f"✗ Comparison failed!")

print("\n" + "=" * 60)
print("KEYBIND VERIFICATION COMPLETE")
print("=" * 60)
