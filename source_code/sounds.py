"""
sounds.py — Sound effect and music manager for Project Orin
============================================================

Folder layout expected on disk:

    game_files/
    ├── source_code/
    │   └── sounds.py        ← this file
    └── assets/
        ├── sounds/          ← drop .wav / .ogg effect files here
        └── music/           ← drop .ogg / .mp3 music tracks here

All sound files are loaded automatically by name (no extension needed):
    SFX.play("footstep")        # plays  assets/sounds/footstep.wav
    SFX.play("collect", vol=0.6)

Music is streamed via pygame.mixer.music:
    MUSIC.play("menu")              # loops forever
    MUSIC.start_rotation(["a","b"]) # shuffles between tracks
    MUSIC.update()                  # call every frame to advance rotation
"""

import os
import random
from typing import Optional
import pygame

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSETS_DIR = os.path.join(os.path.dirname(_SOURCE_DIR), "assets")
SOUNDS_DIR  = os.path.join(_ASSETS_DIR, "sounds")
MUSIC_DIR   = os.path.join(_ASSETS_DIR, "music")

_SOUND_EXTS = {".wav", ".ogg", ".mp3"}
_MUSIC_EXTS = {".ogg", ".mp3", ".wav"}

# ---------------------------------------------------------------------------
# Sound name constants
# ---------------------------------------------------------------------------
SND_COLLECT = "collect"
SND_HIDE    = "hide"
SND_UNHIDE  = "unhide"
SND_STEP    = "step"
SND_BEEP    = "beep"
SND_DEATH   = "death"

# ---------------------------------------------------------------------------
# Music track name constants
# ---------------------------------------------------------------------------
# Only 3 tracks exist on disk (assets/music/): sfx_game1.ogg, slow_sker1.ogg,
# spokoky3.ogg. MUS_MENU/MUS_TENSE previously pointed at "menu"/"tense",
# which don't exist — MusicManager._find_file silently no-ops for a missing
# file, so the title screen and monster-proximity stinger played nothing.
MUS_MENU    = "spokoky3"    # title screen
MUS_TENSE   = "sfx_game1"   # short (~10s) one-shot stinger when monster is near
MUS_AMBIENT = ["spokoky3", "slow_sker1"]   # rotated randomly during gameplay


# ===========================================================================
# SoundManager
# ===========================================================================
class SoundManager:
    """Loads every .wav/.ogg/.mp3 in the sounds/ folder and plays on demand."""

    def __init__(self):
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._global_volume: float = 1.0

    def _load_all(self):
        if not os.path.isdir(SOUNDS_DIR):
            return
        for filename in os.listdir(SOUNDS_DIR):
            ext = os.path.splitext(filename)[1].lower()
            if ext in _SOUND_EXTS:
                name = os.path.splitext(filename)[0]
                path = os.path.join(SOUNDS_DIR, filename)
                try:
                    self._sounds[name] = pygame.mixer.Sound(path)
                except pygame.error as e:
                    print(f"[SoundManager] Could not load '{filename}': {e}")

    def play(self, name: str, vol: float = 1.0, maxtime_ms: int = 0) -> None:
        if name not in self._sounds:
            return
        snd = self._sounds[name]
        snd.set_volume(vol * self._global_volume)
        snd.play(maxtime=maxtime_ms)

    def stop(self, name: str) -> None:
        if name in self._sounds:
            self._sounds[name].stop()

    def set_volume(self, volume: float) -> None:
        self._global_volume = max(0.0, min(1.0, volume))

    def loaded(self) -> list[str]:
        return list(self._sounds.keys())


# ===========================================================================
# MusicManager
# ===========================================================================
class MusicManager:
    """
    Crossfades between music tracks using two alternating pygame.mixer
    Channels (pygame.mixer.music is a single stream and can't overlap two
    tracks, which is required to fade one out while fading the next in).

    Random rotation (frame-polling — no end-event required)
    -------------------------------------------------------
    Call start_rotation(tracks) to begin cycling through a list of tracks.
    The manager plays each track once and then, when it detects that playback
    has stopped, automatically crossfades into the next random track
    (different from the one that just played).

    Call MUSIC.update(dt) once per frame in your game loop — dt drives both
    the rotation polling and the crossfade ramp.

    Example
    -------
        MUSIC.start_rotation(["spopoky", "slow_sker1"])

        # game loop:
        while running:
            MUSIC.update(dt)
            ...

        # switch to tense music (interrupts rotation, crossfades in):
        MUSIC.play("tense")          # loops forever, no polling needed

        # resume ambient rotation:
        MUSIC.start_rotation(MUS_AMBIENT)
    """

    FADE_SECONDS = 1.5

    def __init__(self):
        self._current: str | None  = None
        self._volume: float        = 0.5
        self._rotation: list[str]  = []     # track names currently rotating
        self._in_rotation: bool    = False

        self._channels_ready = False
        self._channels: list = [None, None]   # pygame.mixer.Channel, lazily created
        self._active = 0                      # index of the channel in front
        self._sound_cache: dict[str, pygame.mixer.Sound] = {}

        self._fading     = False
        self._fade_timer = 0.0

    # ------------------------------------------------------------------
    # Lazy setup (pygame.mixer isn't initialised yet when the module-level
    # MUSIC singleton below is constructed)
    # ------------------------------------------------------------------

    def _ensure_channels(self) -> bool:
        if self._channels_ready:
            return True
        if not pygame.mixer.get_init():
            return False
        pygame.mixer.set_reserved(2)
        self._channels = [pygame.mixer.Channel(0), pygame.mixer.Channel(1)]
        self._channels_ready = True
        return True

    def _load_sound(self, name: str) -> Optional[pygame.mixer.Sound]:
        if name in self._sound_cache:
            return self._sound_cache[name]
        path = self._find_file(name)
        if path is None:
            return None
        try:
            snd = pygame.mixer.Sound(path)
        except pygame.error:
            return None
        self._sound_cache[name] = snd
        return snd

    # ------------------------------------------------------------------
    # Single-track play (loops forever by default)
    # ------------------------------------------------------------------

    def play(self, name: str, loop: bool = True,
             vol: Optional[float] = None) -> None:
        """Crossfade into a single music track.  Clears any active rotation."""
        self._in_rotation = False
        self._rotation    = []
        if vol is not None:
            self._volume = max(0.0, min(1.0, vol))
        self._crossfade_to(name, loop)

    # ------------------------------------------------------------------
    # Random rotation
    # ------------------------------------------------------------------

    def start_rotation(self, tracks,
                       vol: Optional[float] = None) -> None:
        """
        Begin a random rotation through *tracks*.

        Pre-filters to tracks whose files actually exist so a missing
        file never silently kills the rotation.

        If the identical rotation is already playing, does nothing so
        a call every frame is harmless.
        """
        if not tracks:
            return
        if isinstance(tracks, str):
            tracks = [tracks]

        # Keep only tracks we can actually find on disk
        valid = [t for t in tracks if self._find_file(t) is not None]
        if not valid:
            return   # none of the files exist — stay silent

        # Already playing the same rotation → leave it alone
        if (self._in_rotation and set(self._rotation) == set(valid)
                and self._channels_ready and self._channels[self._active].get_busy()):
            return

        self._rotation    = valid
        self._in_rotation = True
        if vol is not None:
            self._volume = max(0.0, min(1.0, vol))
        self._advance_rotation(exclude=None)

    def update(self, dt: float = 0.0) -> None:
        """
        Call once per frame.  Advances any in-progress crossfade and
        advances the rotation when the current track has finished playing.
        """
        if not self._ensure_channels():
            return

        if self._fading:
            self._fade_timer += dt
            t = min(1.0, self._fade_timer / self.FADE_SECONDS)
            out_idx = 1 - self._active
            self._channels[self._active].set_volume(self._volume * t)
            self._channels[out_idx].set_volume(self._volume * (1.0 - t))
            if t >= 1.0:
                self._channels[out_idx].stop()
                self._fading = False

        if (self._in_rotation and not self._fading
                and not self._channels[self._active].get_busy()):
            self._advance_rotation(exclude=self._current)

    def _advance_rotation(self, exclude: Optional[str]) -> None:
        """Pick the next track, avoiding *exclude* where possible."""
        candidates = [t for t in self._rotation if t != exclude]
        if not candidates:
            candidates = self._rotation   # only one track — repeat it
        chosen = random.choice(candidates)
        self._crossfade_to(chosen, loop=False)   # play once; update() picks next

    def _crossfade_to(self, name: str, loop: bool) -> None:
        """Fade the currently-playing channel out while fading *name* in on
        the other channel, over FADE_SECONDS."""
        self._current = name
        if not self._ensure_channels():
            return
        snd = self._load_sound(name)
        if snd is None:
            return
        incoming_idx = 1 - self._active
        self._channels[incoming_idx].set_volume(0.0)
        self._channels[incoming_idx].play(snd, loops=(-1 if loop else 0))
        self._active     = incoming_idx
        self._fade_timer = 0.0
        self._fading     = True

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def stop(self) -> None:
        if self._channels_ready:
            for ch in self._channels:
                ch.stop()
        self._current     = None
        self._in_rotation = False
        self._fading       = False

    def pause(self) -> None:
        if self._channels_ready:
            for ch in self._channels:
                ch.pause()

    def unpause(self) -> None:
        if self._channels_ready:
            for ch in self._channels:
                ch.unpause()

    def fadeout(self, ms: int = 1000) -> None:
        if self._channels_ready:
            for ch in self._channels:
                ch.fadeout(ms)
        self._current     = None
        self._in_rotation = False
        self._fading       = False

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        if self._channels_ready and not self._fading:
            self._channels[self._active].set_volume(self._volume)

    @property
    def current(self) -> Optional[str]:
        return self._current

    @property
    def in_rotation(self) -> bool:
        return self._in_rotation

    def is_playing(self) -> bool:
        if not self._ensure_channels():
            return False
        return self._channels[self._active].get_busy()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_file(self, name: str) -> Optional[str]:
        if not isinstance(name, str):
            return None
        if not os.path.isdir(MUSIC_DIR):
            return None
        for ext in _MUSIC_EXTS:
            path = os.path.join(MUSIC_DIR, name + ext)
            if os.path.isfile(path):
                return path
        return None


# ===========================================================================
# Module-level singletons
# ===========================================================================
SFX   = SoundManager()
MUSIC = MusicManager()


def init_audio() -> None:
    """
    Load all sound files into SFX.
    Must be called after pygame.mixer.pre_init() and pygame.init().
    Safe to call more than once (reloads from disk).
    """
    SFX._load_all()
