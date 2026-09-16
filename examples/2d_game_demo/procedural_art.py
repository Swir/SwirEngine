"""Procedural original artwork for the SwirEngine 2D Game Demo.

Everything is generated locally from Pillow drawing primitives. The repository therefore keeps the
showcase source-only while the rendered game still uses real sprites instead of debug rectangles.
"""

from __future__ import annotations

import math
import struct
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw

ART_DIR = Path(tempfile.gettempdir()) / "swirengine_2d_game_demo_art_v2"


def _save(image: Image.Image, name: str) -> Path:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    path = ART_DIR / name
    image.save(path)
    return path


def _player_frame(step: int) -> Image.Image:
    img = Image.new("RGBA", (64, 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((15, 12, 49, 47), fill=(44, 188, 255, 38))
    shift = 4 if step == 1 else (-2 if step == 2 else 0)
    d.polygon([(18, 39), (4, 35 + shift), (10, 43 + shift), (20, 44)], fill=(255, 56, 84, 255))
    leg = 4 if step == 1 else (-4 if step == 2 else 0)
    d.rounded_rectangle((21 + leg, 54, 29 + leg, 72), radius=3, fill=(22, 83, 147, 255))
    d.rounded_rectangle((35 - leg, 54, 43 - leg, 72), radius=3, fill=(22, 83, 147, 255))
    d.rounded_rectangle((17 + leg, 68, 30 + leg, 74), radius=3, fill=(17, 47, 83, 255))
    d.rounded_rectangle((34 - leg, 68, 47 - leg, 74), radius=3, fill=(17, 47, 83, 255))
    d.rounded_rectangle(
        (18, 35, 46, 60), radius=7, fill=(20, 175, 247, 255), outline=(116, 230, 255, 255), width=2
    )
    d.rectangle((21, 46, 43, 52), fill=(8, 93, 164, 255))
    d.rectangle((22, 47, 26, 50), fill=(106, 236, 255, 255))
    d.rounded_rectangle(
        (18, 13, 46, 39), radius=10, fill=(223, 246, 255, 255), outline=(65, 179, 232, 255), width=2
    )
    d.rounded_rectangle((24, 20, 44, 29), radius=4, fill=(8, 39, 67, 255))
    d.rectangle((27, 22, 39, 24), fill=(64, 225, 255, 255))
    d.ellipse((20, 31, 24, 35), fill=(255, 255, 255, 255))
    return img


def _enemy_frame(step: int) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bob = 2 if step else 0
    d.ellipse((13, 13 + bob, 51, 53 + bob), fill=(255, 48, 77, 32))
    d.rounded_rectangle(
        (14, 24 + bob, 50, 48 + bob), radius=8, fill=(184, 32, 54, 255), outline=(255, 102, 115, 255), width=2
    )
    d.rounded_rectangle(
        (18, 11 + bob, 46, 30 + bob), radius=7, fill=(239, 55, 67, 255), outline=(255, 151, 131, 255), width=2
    )
    d.rounded_rectangle((22, 17 + bob, 42, 23 + bob), radius=3, fill=(40, 8, 19, 255))
    d.rectangle((26, 19 + bob, 38, 21 + bob), fill=(255, 211, 46, 255))
    foot = 3 if step else -2
    d.rounded_rectangle((13 + foot, 46 + bob, 28 + foot, 55 + bob), radius=3, fill=(82, 13, 31, 255))
    d.rounded_rectangle((36 - foot, 46 + bob, 51 - foot, 55 + bob), radius=3, fill=(82, 13, 31, 255))
    d.rectangle((8, 30 + bob, 14, 42 + bob), fill=(118, 20, 42, 255))
    d.rectangle((50, 30 + bob, 56, 42 + bob), fill=(118, 20, 42, 255))
    return img


def _shard() -> Image.Image:
    img = Image.new("RGBA", (48, 56), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((3, 7, 45, 49), fill=(36, 205, 255, 35))
    d.polygon([(24, 3), (41, 26), (24, 53), (7, 26)], fill=(51, 226, 255, 255), outline=(206, 250, 255, 255))
    d.polygon([(24, 8), (31, 26), (24, 44), (18, 26)], fill=(127, 248, 255, 255))
    return img


def _portal() -> Image.Image:
    img = Image.new("RGBA", (80, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 5, 72, 115), radius=26, outline=(39, 255, 166, 110), width=9)
    d.rounded_rectangle((17, 14, 63, 106), radius=21, outline=(103, 255, 207, 205), width=5)
    for y in range(28, 97, 11):
        d.line((26, y, 54, y - 7), fill=(118, 255, 218, 120), width=2)
    return img


def _tone(path: Path, frequency: float, duration: float, *, volume: float = 0.22) -> None:
    sample_rate = 22050
    count = int(sample_rate * duration)
    frames = bytearray()
    for i in range(count):
        t = i / sample_rate
        env = min(1.0, i / max(1, sample_rate * 0.01)) * max(0.0, 1.0 - t / duration)
        value = math.sin(2 * math.pi * frequency * t) * 0.75 + math.sin(2 * math.pi * frequency * 2.0 * t) * 0.25
        sample = int(max(-1.0, min(1.0, value * env * volume)) * 32767)
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)


def ensure_art() -> dict[str, Path]:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "player_idle": ART_DIR / "player_idle.png",
        "player_run_a": ART_DIR / "player_run_a.png",
        "player_run_b": ART_DIR / "player_run_b.png",
        "enemy_a": ART_DIR / "enemy_a.png",
        "enemy_b": ART_DIR / "enemy_b.png",
        "shard": ART_DIR / "shard.png",
        "portal": ART_DIR / "portal.png",
        "jump": ART_DIR / "jump.wav",
        "pickup": ART_DIR / "pickup.wav",
        "hit": ART_DIR / "hit.wav",
    }
    if not paths["player_idle"].exists():
        _save(_player_frame(0), "player_idle.png")
        _save(_player_frame(1), "player_run_a.png")
        _save(_player_frame(2), "player_run_b.png")
        _save(_enemy_frame(0), "enemy_a.png")
        _save(_enemy_frame(1), "enemy_b.png")
        _save(_shard(), "shard.png")
        _save(_portal(), "portal.png")
    for name, frequency, duration in (("jump", 440.0, 0.12), ("pickup", 880.0, 0.16), ("hit", 145.0, 0.13)):
        path = paths[name]
        if not path.exists():
            _tone(path, frequency, duration)
    return paths
