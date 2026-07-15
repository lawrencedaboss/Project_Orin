import pygame
import math
from config import KEYBINDS, PLAYER_BASE_SPEED, HUNGER_RATE, HUNGER_SPEED_MULTIPLIER, RADIATION_MAX, PLAYER_START_X, PLAYER_START_Y, PLAYER_HUNGER_START
from map_data import get_item_def
from sprites import draw_player, init_sprites


class Player:
    def __init__(self, screen_width=1000, screen_height=800, zone_count_x=20, zone_count_y=20):
        self.x = PLAYER_START_X
        self.y = PLAYER_START_Y

        self.screen_width = screen_width
        self.screen_height = screen_height
        self.zone_count_x = zone_count_x
        self.zone_count_y = zone_count_y

        self.radiation = 0
        self.loadingzonex = 0
        self.loadingzoney = 0

        self.rect = pygame.Rect(self.x, self.y, 20, 20)
        self.color = (0, 255, 0)
        self.speed = PLAYER_BASE_SPEED

        self.hunger = PLAYER_HUNGER_START
        self.hunger_rate = HUNGER_RATE
        self.alive = True
        self.hiding = False
        self.collected_objects = 0

        # inventory: list of item_id strings (consumables / keys / etc.)
        self.inventory = []
        self.ammo = 30

        # equipment slots: dict of slot_name -> item_id (None = empty)
        self.equipment = {
            'body': None,   # radiation suit goes here
        }

        self.RADIATION_MAX = RADIATION_MAX
        # sprite animation state
        self._anim_t  = 0.0   # accumulated time for walk cycle
        self._last_dx = 0.0
        self._last_dy = 1.0   # default face-forward
        self._shoot_timer = 0.0   # counts down while the gun-hold pose is shown

        # Minimap: zones the player has physically visited or revealed via
        # a map_fragment's reveal_radius effect.
        self.known_zones = {(self.loadingzonex, self.loadingzoney)}

    # ------------------------------------------------------------------
    # Properties derived from equipped items
    # ------------------------------------------------------------------

    @property
    def rad_resist(self):
        """Returns the fraction of radiation that is blocked (0.0 - 1.0)."""
        total = 0.0
        for slot, item_id in self.equipment.items():
            if item_id is None:
                continue
            item_def = get_item_def(item_id)
            total += item_def.get('effect', {}).get('rad_resist', 0.0)
        return min(total, 0.95)   # cap at 95% resistance

    # ------------------------------------------------------------------
    # Update / movement
    # ------------------------------------------------------------------

    def update(self, dt):
        keys = pygame.key.get_pressed()
        moving = (keys[KEYBINDS['move_left']] or keys[KEYBINDS['move_right']] or
                    keys[KEYBINDS['move_up']] or keys[KEYBINDS['move_down']])
        drain = self.hunger_rate * (2 if moving else 1) * dt
        self.hunger = max(0, self.hunger - drain)

        if self._shoot_timer > 0:
            self._shoot_timer = max(0.0, self._shoot_timer - dt)

        # Slow down as hunger falls below 50
        if self.hunger <= 50:
            self.speed = PLAYER_BASE_SPEED - HUNGER_SPEED_MULTIPLIER * (50 - self.hunger)
        else:
            self.speed = PLAYER_BASE_SPEED

    def trigger_shoot(self, hold_seconds=0.35):
        """Show the gun-hold pose for a brief moment after firing."""
        self._shoot_timer = hold_seconds

    def eat(self, nutrition):
        self.hunger = min(100, self.hunger + nutrition)

    # ------------------------------------------------------------------
    # Inventory / Equipment helpers
    # ------------------------------------------------------------------

    def equip_item(self, item_id):
        """Move an equippable item from inventory into its equipment slot.
        Returns True on success."""
        item_def = get_item_def(item_id)
        if not item_def.get('equippable'):
            return False
        slot = item_def.get('slot')
        if slot not in self.equipment:
            return False
        # Unequip whatever is already there (put it back in inventory)
        current = self.equipment[slot]
        if current is not None:
            self.inventory.append(current)
        # Equip the new item (remove from inventory)
        if item_id in self.inventory:
            self.inventory.remove(item_id)
        self.equipment[slot] = item_id
        return True

    def unequip_slot(self, slot):
        """Move equipped item back to inventory. Returns True on success."""
        if slot not in self.equipment or self.equipment[slot] is None:
            return False
        self.inventory.append(self.equipment[slot])
        self.equipment[slot] = None
        return True

    def use_inventory_item(self, item_id=None):
        """Use / consume an item from inventory (or equip it if equippable).
        If item_id is None, uses the first item."""
        if not self.inventory:
            return False

        target_id = item_id if item_id is not None else self.inventory[0]
        if target_id not in self.inventory:
            return False

        item_def = get_item_def(target_id)
        if not item_def:
            return False

        # Equippable items go to equipment slot instead of being consumed
        if item_def.get('equippable'):
            return self.equip_item(target_id)

        # Consumable: apply effects and remove
        effect = item_def.get('effect', {})
        if 'hunger' in effect:
            self.hunger = max(0, min(100, self.hunger + effect['hunger']))
        if 'radiation' in effect:
            self.radiation = max(0, self.radiation + effect['radiation'])
        if 'ammo' in effect:
            self.ammo = min(self.ammo + effect['ammo'], 99)
        if 'reveal_radius' in effect:
            self.reveal_zones_around(effect['reveal_radius'])

        self.inventory.remove(target_id)
        return True

    def reveal_zones_around(self, radius):
        """Add every zone within `radius` (Chebyshev distance) of the
        player's current zone to known_zones — used by map_fragment."""
        cx, cy = self.loadingzonex, self.loadingzoney
        r = int(radius)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                zx, zy = cx + dx, cy + dy
                if 0 <= zx < self.zone_count_x and 0 <= zy < self.zone_count_y:
                    self.known_zones.add((zx, zy))

    # ------------------------------------------------------------------
    # Hiding
    # ------------------------------------------------------------------

    def toggle_hiding(self, boxes):
        if self.hiding:
            self.hiding = False
            return

        for box in boxes:
            if box.can_hide(self):
                self.hiding = True
                self.x = box.x + (box.WIDTH - self.rect.width) / 2
                self.y = box.y + box.HEIGHT + (self.rect.height) / 2
                self.rect.x = int(self.x)
                self.rect.y = int(self.y)
                return

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def handle_movement(self, dt):
        if not self.alive:
            return

        keys = pygame.key.get_pressed()

        dx = 0
        dy = 0
        if keys[KEYBINDS['move_left']]:  dx -= 1
        if keys[KEYBINDS['move_right']]: dx += 1
        if keys[KEYBINDS['move_up']]:    dy -= 1
        if keys[KEYBINDS['move_down']]:  dy += 1

        if self.hiding:
            return

        # Normalise diagonal movement
        if dx != 0 and dy != 0:
            factor = 1 / math.sqrt(2)
            dx *= factor
            dy *= factor

        self.x += dx * self.speed * dt
        self.y += dy * self.speed * dt
        if dx or dy:
                self._last_dx = dx
                self._last_dy = dy

        self.rect.x = int(self.x)

        self.rect.y = int(self.y)

    def loading_zones(self):
        ZONE_MARGIN = 30

        if self.x < 0:
            if self.loadingzonex > 0:
                self.loadingzonex -= 1
                self.x = self.screen_width - ZONE_MARGIN
            else:
                self.x = 0
        elif self.x >= self.screen_width:
            if self.loadingzonex < self.zone_count_x - 1:
                self.loadingzonex += 1
                self.x = ZONE_MARGIN
            else:
                self.x = self.screen_width - 1
        elif self.y < 0:
            if self.loadingzoney > 0:
                self.loadingzoney -= 1
                self.y = self.screen_height - ZONE_MARGIN
            else:
                self.y = 0
        elif self.y >= self.screen_height:
            if self.loadingzoney < self.zone_count_y - 1:
                self.loadingzoney += 1
                self.y = ZONE_MARGIN
            else:
                self.y = self.screen_height - 1

        self.rect.x = int(self.x)
        self.rect.y = int(self.y)
        self.known_zones.add((self.loadingzonex, self.loadingzoney))

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, screen, dt=0.0):
        if self.alive and not self.hiding:
            keys = pygame.key.get_pressed()
            from config import KEYBINDS
            moving = (keys[KEYBINDS['move_left']] or keys[KEYBINDS['move_right']] or
                        keys[KEYBINDS['move_up']]   or keys[KEYBINDS['move_down']])
            if moving:
                self._anim_t += dt
            has_suit = self.equipment.get('body') is not None
            has_gun  = self._shoot_timer > 0
            draw_player(screen, self.rect,
                        self._last_dx, self._last_dy,
                        moving, has_gun, has_suit, self._anim_t)
