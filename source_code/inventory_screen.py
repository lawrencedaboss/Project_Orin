import pygame
from config import (SCREEN_WIDTH, SCREEN_HEIGHT, KEYBINDS)
from map_data import (get_item_def)
from sounds import MUSIC
from display_scale import present
# ---------------------------------------------------------------------------
# Inventory screen — two tabs: Items | Equipment
# ---------------------------------------------------------------------------
class InventoryScreen:
    """
    Tab 0: Items     — consumables in inventory, pick & use individually
    Tab 1: Equipment — equippable items (rad suit etc.)
    """

    TABS = ["ITEMS", "EQUIPMENT"]
    TAB_COLORS = {
        "ITEMS":     (80, 140, 220),
        "EQUIPMENT": (200, 130, 50),
    }

    def __init__(self):
        self.title_font = pygame.font.SysFont('Arial', 38, bold=True)
        self.tab_font   = pygame.font.SysFont('Arial', 20, bold=True)
        self.text_font  = pygame.font.SysFont('Arial', 20)
        self.small_font = pygame.font.SysFont('Arial', 17)
        self._tab = 0            # active tab index
        self._item_cursor = 0   # cursor within Items tab

    # ---- helpers ----

    def _panel_rect(self):
        pw, ph = 660, 520
        px = (SCREEN_WIDTH  - pw) // 2
        py = (SCREEN_HEIGHT - ph) // 2
        return pygame.Rect(px, py, pw, ph)

    @staticmethod
    def _ordered_items(player):
        """Consumables first, then equippables. Both the Items-tab renderer
        and the Enter/U action must index into this exact same ordering —
        they used to compute it separately (one used raw player.inventory
        order), so the cursor position (drawn against this order) and the
        item actually used (looked up in the other order) could point at
        different items whenever an equippable wasn't already last in
        player.inventory."""
        consumables = [iid for iid in player.inventory
                       if not get_item_def(iid).get('equippable')]
        equippables = [iid for iid in player.inventory
                       if get_item_def(iid).get('equippable')]
        return consumables + equippables

    def _draw_bar(self, screen, x, y, w, h, value, max_value, fill_color):
        pct = max(0.0, min(1.0, value / max_value))
        pygame.draw.rect(screen, (40, 40, 40), (x, y, w, h))
        pygame.draw.rect(screen, fill_color,   (x, y, int(w * pct), h))
        pygame.draw.rect(screen, (180, 180, 180), (x, y, w, h), 1)

    def _tab_rect(self, panel, index):
        tab_w = panel.width // len(self.TABS)
        return pygame.Rect(panel.left + index * tab_w, panel.top, tab_w, 36)

    def _draw_tabs(self, screen, panel):
        for i, name in enumerate(self.TABS):
            r = self._tab_rect(panel, i)
            active = (i == self._tab)
            bg = (30, 45, 90) if active else (20, 28, 60)
            pygame.draw.rect(screen, bg, r)
            border_color = self.TAB_COLORS[name] if active else (60, 70, 100)
            pygame.draw.rect(screen, border_color, r, 2 if active else 1)
            label = self.tab_font.render(name, True,
                                         self.TAB_COLORS[name] if active else (140, 140, 160))
            screen.blit(label, (r.x + (r.width - label.get_width()) // 2, r.y + 8))

    def _draw_status_bars(self, screen, player, x, y):
        """Render hunger + radiation bars at (x, y); returns new y."""
        # Hunger bar
        hl = self.small_font.render("Hunger:", True, (255, 200, 100))
        screen.blit(hl, (x, y))
        self._draw_bar(screen, x + 130, y + 2, 200, 18, player.hunger, 100, (255, 140, 0))
        hp = self.small_font.render(f"{player.hunger:.0f}%", True, (255, 255, 255))
        screen.blit(hp, (x + 340, y + 2))
        y += 30
        # Radiation bar
        rl = self.small_font.render("Radiation:", True, (100, 255, 120))
        screen.blit(rl, (x, y))
        self._draw_bar(screen, x + 130, y + 2, 200, 18,
                        player.radiation, player.RADIATION_MAX, (0, 220, 80))
        rp = self.small_font.render(f"{player.radiation:.0f}%", True, (255, 255, 255))
        screen.blit(rp, (x + 340, y + 2))
        # Resistance indicator
        resist = player.rad_resist
        if resist > 0:
            ri = self.small_font.render(f"  (-{resist*100:.0f}% resist)", True, (80, 200, 255))
            screen.blit(ri, (x + 370, y + 2))
        return y + 36

    # ---- tab renderers ----

    def _draw_tab_items(self, screen, player, panel, content_top):
        x = panel.left + 24
        y = content_top

        all_items = self._ordered_items(player)

        if not all_items:
            empty = self.text_font.render("No items in inventory.", True, (160, 160, 160))
            screen.blit(empty, (x + 20, y + 20))
        else:
            self._item_cursor = max(0, min(self._item_cursor, len(all_items) - 1))
            row_h = 48
            visible_rows = (panel.bottom - 80 - content_top) // row_h

            for idx, item_id in enumerate(all_items):
                if idx >= visible_rows:
                    more = self.small_font.render(
                        f"… +{len(all_items) - visible_rows} more", True, (100, 100, 100))
                    screen.blit(more, (x + 20, y))
                    break
                item_def = get_item_def(item_id)
                name  = item_def.get('name', item_id)
                desc  = item_def.get('description', '')
                is_equip = item_def.get('equippable', False)
                selected = (idx == self._item_cursor)

                # Row background
                row_rect = pygame.Rect(x + 10, y - 2, panel.width - 48, row_h - 4)
                if selected:
                    pygame.draw.rect(screen, (45, 60, 110), row_rect)
                    pygame.draw.rect(screen, (100, 140, 220), row_rect, 2)

                # Category badge colour
                cat = item_def.get('category', '')
                badge_colors = {
                    'food':       (80, 180, 80),
                    'consumable': (200, 140, 40),
                    'equipment':  (200, 130, 50),
                }
                badge_col = badge_colors.get(cat, (120, 120, 120))
                pygame.draw.rect(screen, badge_col, (x + 14, y + 10, 4, 26))

                # Name
                name_col = (255, 230, 140) if selected else (220, 210, 180)
                tag = " [equip]" if is_equip else " [use]"
                name_surf = self.text_font.render(name + tag, True, name_col)
                screen.blit(name_surf, (x + 26, y + 2))
                # Description
                desc_surf = self.small_font.render(desc, True, (160, 175, 200))
                screen.blit(desc_surf, (x + 26, y + 24))

                y += row_h

        # Bottom hint
        hint_y = panel.bottom - 36
        if all_items:
            hint = self.small_font.render(
                "↑/↓: select    Enter/U: use/equip    ESC/I: close", True, (120, 120, 140))
        else:
            hint = self.small_font.render("ESC / I to close", True, (120, 120, 140))
        screen.blit(hint, (panel.left + (panel.width - hint.get_width()) // 2, hint_y))

    def _draw_tab_equipment(self, screen, player, panel, content_top):
        x = panel.left + 24
        y = content_top

        # Each equipment slot gets its own labeled category section (rather
        # than one generic "Body Armour / Suit" catch-all) so distinct gear
        # types are visually separated — currently just Radiation Suits,
        # but new slots/categories can be added to this dict later.
        categories = {
            'body': 'RADIATION SUITS',
        }
        for slot, category_label in categories.items():
            cat = self.small_font.render(category_label, True, (140, 160, 200))
            screen.blit(cat, (x + 10, y))
            y += 22

            equipped = player.equipment.get(slot)
            # Slot box
            slot_rect = pygame.Rect(x + 10, y, panel.width - 48, 68)
            pygame.draw.rect(screen, (28, 38, 70), slot_rect)
            pygame.draw.rect(screen, (70, 90, 130), slot_rect, 2)

            if equipped:
                item_def = get_item_def(equipped)
                name  = item_def.get('name', equipped)
                desc  = item_def.get('description', '')
                nc = self.text_font.render(name, True, (200, 130, 50))
                screen.blit(nc, (x + 20, y + 10))
                dc = self.small_font.render(desc, True, (150, 160, 190))
                screen.blit(dc, (x + 20, y + 34))
                # Unequip hint
                uh = self.small_font.render("[R] unequip", True, (180, 100, 80))
                screen.blit(uh, (slot_rect.right - uh.get_width() - 10, y + 10))
            else:
                empty_t = self.small_font.render("— empty —", True, (80, 90, 110))
                screen.blit(empty_t, (x + 20, y + 26))

            y += 80

        # Resistance summary
        y += 10
        resist = player.rad_resist
        rs_text = self.text_font.render(
            f"Total radiation resistance: {resist*100:.0f}%", True, (80, 200, 255))
        screen.blit(rs_text, (x + 10, y));  y += 28

        # Status bars
        y = max(y + 10, panel.bottom - 76)
        self._draw_status_bars(screen, player, x, y)

        # Hint
        hint_y = panel.bottom - 36
        hint = self.small_font.render("R: unequip selected slot    ESC / I: close", True, (120, 120, 140))
        screen.blit(hint, (panel.left + (panel.width - hint.get_width()) // 2, hint_y))

    # ---- main run loop ----

    def run(self, screen, clock, player):
        """Blocks until player closes inventory. Returns False only if game should quit."""
        all_items = lambda: self._ordered_items(player)

        while True:
            dt = clock.tick(60) / 1000.0
            MUSIC.update(dt)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    panel = self._panel_rect()
                    for i in range(len(self.TABS)):
                        if self._tab_rect(panel, i).collidepoint(event.pos):
                            self._tab = i
                            self._item_cursor = 0
                            break

                if event.type == pygame.KEYDOWN:
                    # --- close ---
                    if event.key in (pygame.K_ESCAPE, KEYBINDS['inventory']):
                        return True

                    # --- tab switching: Q/E or left/right ---
                    if event.key in (pygame.K_LEFT, pygame.K_q):
                        self._tab = (self._tab - 1) % len(self.TABS)
                        self._item_cursor = 0
                    if event.key in (pygame.K_RIGHT, pygame.K_e):
                        self._tab = (self._tab + 1) % len(self.TABS)
                        self._item_cursor = 0

                    # --- Items tab controls ---
                    if self._tab == 0:
                        items = all_items()
                        if event.key == pygame.K_UP:
                            self._item_cursor = max(0, self._item_cursor - 1)
                        if event.key == pygame.K_DOWN:
                            self._item_cursor = min(len(items) - 1, self._item_cursor + 1)
                        if event.key in (pygame.K_RETURN, pygame.K_u) and items:
                            target_id = items[self._item_cursor]
                            player.use_inventory_item(target_id)
                            # Adjust cursor if list shrank
                            self._item_cursor = min(self._item_cursor, len(all_items()) - 1)
                            self._item_cursor = max(0, self._item_cursor)

                    # --- Equipment tab controls ---
                    if self._tab == 1:
                        if event.key == pygame.K_r:
                            player.unequip_slot('body')

            # --- Render ---
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((10, 14, 36, 210))
            screen.blit(overlay, (0, 0))

            panel = self._panel_rect()
            bg = pygame.Surface((panel.width, panel.height), pygame.SRCALPHA)
            bg.fill((22, 32, 68, 245))
            screen.blit(bg, panel.topleft)
            pygame.draw.rect(screen, (80, 110, 180), panel, 2)

            # Tabs row
            self._draw_tabs(screen, panel)
            content_top = panel.top + 50

            if self._tab == 0:
                self._draw_tab_items(screen, player, panel, content_top)
            elif self._tab == 1:
                self._draw_tab_equipment(screen, player, panel, content_top)

            # Tab navigation hint at top right
            nav_hint = self.small_font.render("◄ Q / E ►  switch tabs", True, (90, 100, 140))
            screen.blit(nav_hint, (panel.right - nav_hint.get_width() - 10, panel.top - 20))

            present(screen)