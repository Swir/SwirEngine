"""Procedural original textures and sound cues for the SwirEngine 3D Game Demo."""

from __future__ import annotations

import math
import random
import struct
import tempfile
import wave
from pathlib import Path

from PIL import Image, ImageDraw

ART_DIR = Path(tempfile.gettempdir()) / "swirengine_3d_game_demo_art_v2"


def _steel(seed: int = 17) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new("RGB", (128, 128), (31, 43, 55))
    d = ImageDraw.Draw(img)
    for x in range(0, 128, 32):
        d.line((x, 0, x, 128), fill=(20, 28, 37), width=2)
        d.line((x + 2, 0, x + 2, 128), fill=(47, 63, 78), width=1)
    for y in range(0, 128, 32):
        d.line((0, y, 128, y), fill=(20, 28, 37), width=2)
        d.line((0, y + 2, 128, y + 2), fill=(47, 63, 78), width=1)
    for x in range(16, 128, 32):
        for y in range(16, 128, 32):
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(94, 111, 124))
    for _ in range(26):
        x, y = rng.randrange(8, 120), rng.randrange(8, 120)
        length = rng.randrange(5, 17)
        shade = rng.randrange(45, 74)
        d.line((x, y, min(127, x + length), y + rng.choice((-1, 0, 1))), fill=(shade, shade + 4, shade + 7), width=1)
    return img


def _floor() -> Image.Image:
    img = Image.new("RGB", (128, 128), (25, 29, 34))
    d = ImageDraw.Draw(img)
    for y in range(0, 128, 16):
        for x in range(0, 128, 16):
            offset = 8 if (y // 16) % 2 else 0
            x0 = (x + offset) % 128
            d.rectangle((x0, y, min(127, x0 + 13), y + 13), outline=(46, 54, 62))
            if (x + y) % 48 == 0:
                d.line((x0 + 3, y + 7, min(127, x0 + 10), y + 7), fill=(70, 94, 104))
    d.line((0, 63, 128, 63), fill=(31, 145, 176), width=2)
    d.line((0, 65, 128, 65), fill=(10, 57, 74), width=1)
    return img


def _hazard() -> Image.Image:
    img = Image.new("RGB", (128, 128), (30, 32, 34))
    d = ImageDraw.Draw(img)
    stripe = 24
    for x in range(-128, 256, stripe * 2):
        d.polygon([(x, 128), (x + stripe, 128), (x + 128 + stripe, 0), (x + 128, 0)], fill=(224, 160, 26))
    d.rectangle((0, 0, 127, 127), outline=(87, 91, 91), width=3)
    return img


def _panel() -> Image.Image:
    img = Image.new("RGB", (128, 128), (17, 29, 42))
    d = ImageDraw.Draw(img)
    d.rectangle((7, 7, 121, 121), outline=(51, 90, 112), width=3)
    for y in (28, 64, 100):
        d.rounded_rectangle((18, y - 8, 110, y + 8), radius=4, fill=(11, 20, 29), outline=(40, 110, 139))
        for x in range(27, 104, 18):
            color = (26, 202, 231) if (x + y) % 3 else (234, 73, 86)
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color)
    return img


def _tone(path: Path, frequency: float, duration: float, *, noise: bool = False) -> None:
    sample_rate = 22050
    rng = random.Random(int(frequency))
    frames = bytearray()
    count = int(sample_rate * duration)
    for i in range(count):
        t = i / sample_rate
        envelope = max(0.0, 1.0 - t / duration) ** 1.8
        base = math.sin(2 * math.pi * frequency * t)
        if noise:
            base = base * 0.55 + rng.uniform(-1.0, 1.0) * 0.45
        sample = int(max(-1.0, min(1.0, base * envelope * 0.24)) * 32767)
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)


def ensure_art() -> dict[str, Path]:
    ART_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "steel": ART_DIR / "steel.png",
        "floor": ART_DIR / "floor.png",
        "hazard": ART_DIR / "hazard.png",
        "panel": ART_DIR / "panel.png",
        "shot": ART_DIR / "shot.wav",
        "pickup": ART_DIR / "pickup.wav",
        "damage": ART_DIR / "damage.wav",
    }
    if not paths["steel"].exists():
        _steel().save(paths["steel"])
        _floor().save(paths["floor"])
        _hazard().save(paths["hazard"])
        _panel().save(paths["panel"])
    for name, frequency, duration, noise in (
        ("shot", 105.0, 0.11, True),
        ("pickup", 760.0, 0.17, False),
        ("damage", 82.0, 0.18, True),
    ):
        if not paths[name].exists():
            _tone(paths[name], frequency, duration, noise=noise)
    return paths
