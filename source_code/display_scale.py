"""
display_scale.py — presents a fixed-resolution logical surface onto the
real (possibly resized/fullscreen) window with crisp, non-blurred scaling.

pygame.SCALED delegates this scaling to SDL's renderer, whose filter
quality depends on the SDL_RENDER_SCALE_QUALITY hint — but that hint isn't
reliably honored on every GPU backend (notably Metal on macOS), so pixel
art can end up blurry regardless of the hint. pygame.transform.scale()
(unlike smoothscale()) does a plain nearest/block scale with no
interpolation, so doing the upscale ourselves guarantees crisp pixels.

Scaling to a non-integer factor (e.g. stretching 900x700 to fill an
arbitrary 1288x807 window) makes nearest-neighbor scaling itself look
"broken" — some source pixels get replicated one extra destination pixel
compared to their neighbours, so straight sprite edges turn visibly
jagged/uneven as the window is resized. Snapping to the largest whole-
number scale that fits, then letterboxing the remainder, keeps every
source pixel mapped to the same NxN block — always clean, and the logical
900x700 proportions are preserved exactly (the window can grow, but the
picture inside it never stretches/distorts).
"""

import pygame


def _fit(real_size, logical_size):
    rw, rh = real_size
    lw, lh = logical_size

    if rw >= lw and rh >= lh:
        scale = max(1, min(rw // lw, rh // lh))   # integer only: no uneven pixel blocks
    else:
        scale = min(rw / lw, rh / lh)              # window smaller than logical size

    sw, sh = max(1, round(lw * scale)), max(1, round(lh * scale))
    ox, oy = (rw - sw) // 2, (rh - sh) // 2
    return scale, sw, sh, ox, oy


def present(logical_surface: pygame.Surface) -> None:
    real = pygame.display.get_surface()
    rw, rh = real.get_size()
    lw, lh = logical_surface.get_size()

    scale, sw, sh, ox, oy = _fit((rw, rh), (lw, lh))

    if (sw, sh) == (lw, lh):
        scaled = logical_surface
    else:
        scaled = pygame.transform.scale(logical_surface, (sw, sh))

    real.fill((0, 0, 0))
    real.blit(scaled, (ox, oy))
    pygame.display.flip()


def real_to_logical_pos(pos, logical_size):
    """Map a mouse position in real-window pixels to logical-surface
    coordinates, inverting the same fit present() uses (integer scale,
    letterboxed/centered) — must stay in sync with present()'s math or
    aiming drifts out of alignment with what's drawn."""
    real = pygame.display.get_surface()
    rw, rh = real.get_size()
    lw, lh = logical_size
    scale, sw, sh, ox, oy = _fit((rw, rh), (lw, lh))
    x = (pos[0] - ox) / scale
    y = (pos[1] - oy) / scale
    return x, y
