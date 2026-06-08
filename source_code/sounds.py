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

Music is streamed (not loaded fully into RAM) via pygame.mixer.music:
    MUSIC.play("ambient_zone")  # streams assets/music/ambient_zone.ogg
    MUSIC.stop()
"""

import os
from typing import Optional
import pygame

# ---------------------------------------------------------------------------
# Paths — source_code/ sits inside game_files/, assets/ is its sibling
# ---------------------------------------------------------------------------
_SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))  # …/source_code
_ASSETS_DIR = os.path.join(os.path.dirname(_SOURCE_DIR), "assets")  # …/assets
SOUNDS_DIR  = os.path.join(_ASSETS_DIR, "sounds")   # …/assets/sounds
MUSIC_DIR   = os.path.join(_ASSETS_DIR, "music")    # …/assets/music

_SOUND_EXTS = {".wav", ".ogg", ".mp3"}
_MUSIC_EXTS = {".ogg", ".mp3", ".wav"}


# ---------------------------------------------------------------------------
# Sound name constants — add one for every file you put in sounds/
# ---------------------------------------------------------------------------
SND_COLLECT     = "collect"       # sounds/collect.wav
SND_HIDE        = "hide"          # sounds/hide.wav
SND_UNHIDE      = "unhide"        # sounds/unhide.wav
SND_STEP        = "step"          # sounds/step.wav
SND_BEEP        = "beep"          # sounds/beep.wav  (proximity alert)
SND_MONSTER_NEAR = "monster_near" # sounds/monster_near.wav
SND_ZONE_ENTER  = "zone_enter"    # sounds/zone_enter.wav
SND_DEATH       = "death"         # sounds/death.wav
# ... add more sound name constants here


# ---------------------------------------------------------------------------
# Music track name constants — add one for every file you put in music/
# ---------------------------------------------------------------------------
MUS_MENU        = "menu"          # music/menu.ogg
MUS_AMBIENT     = "ambient"       # music/ambient.ogg
MUS_TENSE       = "tense"         # music/tense.ogg  (monster nearby)
# ... add more music track constants here


# ---------------------------------------------------------------------------
# SoundManager — handles one-shot sound effects
# ---------------------------------------------------------------------------
class SoundManager:
    """
    Loads every .wav/.ogg file in the sounds/ folder.

    IMPORTANT: do not call play() before init_audio() has been called,
    because pygame.mixer must be fully initialised first.
    """

    def __init__(self):
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._global_volume: float = 1.0
        # _load_all() is NOT called here — call init_audio() after pygame.init()

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

    # ---- public API --------------------------------------------------------

    def play(self, name: str, vol: float = 1.0) -> None:
        """Play a sound effect by name (filename without extension)."""
        if name not in self._sounds:
            return
        snd = self._sounds[name]
        snd.set_volume(vol * self._global_volume)
        snd.play()

    def stop(self, name: str) -> None:
        """Stop all active channels playing this sound."""
        if name in self._sounds:
            self._sounds[name].stop()

    def set_volume(self, volume: float) -> None:
        """Set master sound-effect volume (0.0–1.0)."""
        self._global_volume = max(0.0, min(1.0, volume))

    def loaded(self) -> list[str]:
        """Return a list of all loaded sound names."""
        return list(self._sounds.keys())


# ---------------------------------------------------------------------------
# MusicManager — handles streaming background music
# ---------------------------------------------------------------------------
class MusicManager:
    """Wraps pygame.mixer.music for easy track management."""

    def __init__(self):
        self._current: str | None = None
        self._volume: float = 0.5

    # ---- public API --------------------------------------------------------

    def play(self, name: str, loop: bool = True, vol: Optional[float] = None) -> None:
        """
        Stream a music track from music/.
        name  — filename without extension (see MUS_* constants above)
        loop  — True loops forever, False plays once
        vol   — override volume for this track (uses last set_volume otherwise)

        Fails silently if the file is missing or unloadable so the game
        keeps running without audio.
        """
        # Mark as current immediately so missing files don't retry every frame
        self._current = name

        path = self._find_file(name)
        if path is None:
            return  # no file — silent, _current already set above
        if vol is not None:
            self._volume = max(0.0, min(1.0, vol))
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.play(-1 if loop else 0)
        except pygame.error:
            pass  # unloadable file — silent

    def stop(self) -> None:
        """Stop the current track immediately."""
        pygame.mixer.music.stop()
        self._current = None

    def pause(self) -> None:
        pygame.mixer.music.pause()

    def unpause(self) -> None:
        pygame.mixer.music.unpause()

    def fadeout(self, ms: int = 1000) -> None:
        """Fade out and stop over the given number of milliseconds."""
        pygame.mixer.music.fadeout(ms)
        self._current = None

    def set_volume(self, volume: float) -> None:
        """Set music volume (0.0–1.0); applies immediately."""
        self._volume = max(0.0, min(1.0, volume))
        pygame.mixer.music.set_volume(self._volume)

    @property
    def current(self) -> Optional[str]:
        """Name of the currently playing track, or None."""
        return self._current

    def is_playing(self) -> bool:
        return pygame.mixer.music.get_busy()

    # ---- internal ----------------------------------------------------------

    def _find_file(self, name: str) -> Optional[str]:
        """Return the full path for a track name, trying each extension."""
        if not os.path.isdir(MUSIC_DIR):
            return None
        for ext in _MUSIC_EXTS:
            path = os.path.join(MUSIC_DIR, name + ext)
            if os.path.isfile(path):
                return path
        return None


# ---------------------------------------------------------------------------
# Module-level singletons — import and use anywhere in the project:
#
#   from sounds import SFX, MUSIC, init_audio
#
#   # in Game.__init__, AFTER pygame.mixer.pre_init() and pygame.init():
#   init_audio()
#
#   SFX.play(SND_COLLECT)
#   MUSIC.play(MUS_AMBIENT)
# ---------------------------------------------------------------------------
SFX   = SoundManager()
MUSIC = MusicManager()


def init_audio() -> None:
    """
    Load all sound files into SFX.
    Must be called after pygame.mixer.pre_init() and pygame.init().
    Safe to call more than once (reloads from disk).
    """
    SFX._load_all()
