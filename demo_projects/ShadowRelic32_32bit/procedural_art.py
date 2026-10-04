from __future__ import annotations

import math
import os
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ART_VERSION = "shadow-relic-32-art-v1"


def asset_root() -> Path:
    override = os.environ.get("SHADOW_RELIC_ASSET_CACHE")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".shadow_relic_32" / "assets"


def _pixel_canvas(size: int = 64) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _save_pixel(img: Image.Image, path: Path, *, scale: int = 2) -> None:
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.Resampling.NEAREST)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _mirror(src: Path, dst: Path) -> None:
    with Image.open(src) as img:
        ImageOps.mirror(img.convert("RGBA")).save(dst)


def _hero(path: Path, pose: str, frame: int = 0) -> None:
    img, d = _pixel_canvas(64)
    cloak = (44, 34, 78, 255)
    cloak_hi = (94, 64, 136, 255)
    metal = (176, 190, 208, 255)
    skin = (212, 170, 134, 255)
    cyan = (82, 232, 236, 255)
    shadow = (17, 18, 32, 220)
    bob = 1 if pose == "idle" and frame % 2 else 0
    lean = 2 if pose == "run" and frame in {1, 2} else 0
    d.ellipse((19, 51, 47, 58), fill=shadow)
    leg = frame % 4
    if pose == "run":
        d.rectangle((26 - (leg % 2) * 4, 40, 31 - (leg % 2) * 4, 52), fill=metal)
        d.rectangle((35 + (leg % 2) * 4, 40, 40 + (leg % 2) * 4, 52), fill=metal)
    elif pose == "jump":
        d.rectangle((27, 40, 32, 49), fill=metal)
        d.rectangle((36, 38, 42, 46), fill=metal)
    else:
        d.rectangle((27, 40, 32, 53), fill=metal)
        d.rectangle((36, 40, 41, 53), fill=metal)
    d.polygon([(20 + lean, 24 + bob), (42 + lean, 22 + bob), (47 + lean, 43), (18 + lean, 43)], fill=cloak)
    d.polygon([(22 + lean, 26 + bob), (31 + lean, 23 + bob), (29 + lean, 41), (19 + lean, 41)], fill=cloak_hi)
    d.ellipse((23 + lean, 10 + bob, 41 + lean, 28 + bob), fill=cloak)
    d.rectangle((27 + lean, 16 + bob, 39 + lean, 25 + bob), fill=skin)
    d.rectangle((35 + lean, 18 + bob, 38 + lean, 20 + bob), fill=cyan)
    d.rectangle((41 + lean, 27 + bob, 48 + lean, 34 + bob), fill=metal)
    if pose == "attack":
        d.polygon([(42, 31), (58, 18), (60, 20), (47, 35)], fill=(224, 237, 245, 255))
        d.line((46, 34, 59, 19), fill=cyan, width=2)
    else:
        d.polygon([(45, 31), (55, 39), (53, 42), (43, 35)], fill=(224, 237, 245, 255))
    if pose == "hurt":
        d.rectangle((20, 12, 45, 45), outline=(255, 76, 86, 255), width=2)
    _save_pixel(img, path)


def _crawler(path: Path, frame: int = 0) -> None:
    img, d = _pixel_canvas(48)
    base = (72, 38, 90, 255)
    hi = (166, 78, 186, 255)
    eye = (255, 92, 136, 255)
    d.ellipse((6, 31, 42, 39), fill=(14, 12, 20, 220))
    d.polygon([(8, 29), (13, 16), (34, 14), (40, 29), (32, 35), (15, 35)], fill=base)
    d.rectangle((14, 17, 33, 22), fill=hi)
    d.rectangle((31, 19, 36, 23), fill=eye)
    off = 2 if frame else 0
    for x in (13, 22, 31, 38):
        d.line((x, 34, x - 5 + off, 42), fill=hi, width=2)
    _save_pixel(img, path, scale=2)


def _wisp(path: Path, frame: int = 0) -> None:
    img, d = _pixel_canvas(48)
    blue = (86, 212, 255, 210)
    core = (214, 252, 255, 255)
    shift = 2 if frame else 0
    d.ellipse((10, 7 + shift, 38, 35 + shift), fill=blue)
    d.ellipse((17, 13 + shift, 31, 27 + shift), fill=core)
    d.polygon([(15, 28), (10, 44), (23, 33), (25, 46), (34, 29)], fill=blue)
    _save_pixel(img, path, scale=2)


def _cultist(path: Path, frame: int = 0) -> None:
    img, d = _pixel_canvas(56)
    robe = (66, 25, 70, 255)
    trim = (172, 64, 140, 255)
    mask = (206, 189, 153, 255)
    red = (248, 78, 98, 255)
    d.ellipse((12, 47, 46, 53), fill=(10, 8, 16, 220))
    d.polygon([(18, 20), (38, 20), (44, 47), (12, 47)], fill=robe)
    d.rectangle((16, 31, 40, 35), fill=trim)
    d.ellipse((19, 8, 37, 27), fill=robe)
    d.polygon([(22, 13), (34, 13), (32, 24), (24, 24)], fill=mask)
    d.rectangle((29, 16, 31, 18), fill=red)
    arm = 3 if frame else 0
    d.line((38, 29, 49, 22 + arm), fill=trim, width=3)
    d.line((49, 22 + arm, 53, 12 + arm), fill=mask, width=2)
    _save_pixel(img, path, scale=2)


def _boss(path: Path, frame: int = 0) -> None:
    img, d = _pixel_canvas(96)
    black = (16, 12, 25, 255)
    purple = (74, 34, 108, 255)
    magenta = (218, 72, 188, 255)
    bone = (204, 199, 186, 255)
    eye = (255, 76, 112, 255)
    pulse = 3 if frame % 2 else 0
    d.ellipse((17, 80, 82, 90), fill=(4, 4, 10, 220))
    d.polygon([(25, 35), (71, 35), (81, 82), (15, 82)], fill=black)
    d.polygon([(31, 39), (48, 31), (67, 39), (62, 75), (33, 75)], fill=purple)
    d.ellipse((29, 10, 67, 47), fill=black)
    d.polygon([(36, 18), (60, 18), (57, 37), (39, 37)], fill=bone)
    d.rectangle((51, 24, 56 + pulse, 28), fill=eye)
    d.line((18, 44, 5, 69), fill=magenta, width=5)
    d.line((77, 44, 91, 65), fill=magenta, width=5)
    d.line((48, 43, 48, 72), fill=magenta, width=2)
    _save_pixel(img, path, scale=2)


def _npc(path: Path) -> None:
    img, d = _pixel_canvas(64)
    d.ellipse((19, 51, 47, 57), fill=(10, 10, 20, 210))
    d.polygon([(22, 25), (43, 25), (48, 52), (16, 52)], fill=(38, 67, 84, 255))
    d.ellipse((23, 11, 41, 29), fill=(142, 111, 88, 255))
    d.rectangle((18, 9, 45, 15), fill=(106, 122, 126, 255))
    d.rectangle((26, 17, 38, 20), fill=(103, 236, 218, 255))
    d.rectangle((43, 31, 48, 48), fill=(196, 171, 112, 255))
    _save_pixel(img, path)


def _sigil(path: Path, color: tuple[int, int, int, int], rune: str) -> None:
    img, d = _pixel_canvas(48)
    d.ellipse((7, 7, 41, 41), fill=(18, 16, 32, 255), outline=color, width=3)
    d.ellipse((12, 12, 36, 36), outline=(220, 230, 248, 180), width=1)
    if rune == "sun":
        d.ellipse((20, 20, 28, 28), fill=color)
        for a in range(0, 360, 45):
            x0 = 24 + math.cos(math.radians(a)) * 10
            y0 = 24 + math.sin(math.radians(a)) * 10
            x1 = 24 + math.cos(math.radians(a)) * 15
            y1 = 24 + math.sin(math.radians(a)) * 15
            d.line((x0, y0, x1, y1), fill=color, width=2)
    elif rune == "moon":
        d.ellipse((17, 15, 32, 33), fill=color)
        d.ellipse((22, 13, 34, 30), fill=(18, 16, 32, 255))
    else:
        d.polygon([(24, 12), (34, 24), (24, 36), (14, 24)], outline=color, fill=(28, 22, 42, 255))
        d.line((24, 15, 24, 33), fill=color, width=2)
    _save_pixel(img, path, scale=2)


def _item(path: Path, kind: str) -> None:
    img, d = _pixel_canvas(40)
    if kind == "shard":
        d.polygon([(20, 3), (32, 17), (24, 36), (9, 25)], fill=(83, 227, 247, 255))
        d.polygon([(20, 7), (26, 18), (20, 30), (14, 23)], fill=(220, 255, 255, 255))
    elif kind == "potion":
        d.rectangle((16, 4, 24, 9), fill=(190, 190, 205, 255))
        d.polygon([(12, 10), (28, 10), (33, 33), (7, 33)], fill=(218, 60, 99, 255))
        d.rectangle((10, 22, 30, 30), fill=(255, 107, 139, 255))
    elif kind == "checkpoint":
        d.rectangle((18, 6, 22, 37), fill=(116, 100, 78, 255))
        d.polygon([(22, 8), (35, 13), (22, 19)], fill=(88, 224, 203, 255))
        d.ellipse((14, 33, 27, 38), fill=(40, 130, 120, 255))
    elif kind == "portal":
        d.ellipse((6, 3, 34, 37), outline=(84, 239, 214, 255), width=4)
        d.ellipse((12, 9, 28, 31), fill=(34, 36, 73, 255), outline=(165, 107, 244, 255), width=2)
    _save_pixel(img, path, scale=2)


def _platform(path: Path, palette: str) -> None:
    img = Image.new("RGBA", (128, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    colors = {
        "ruins": ((66, 72, 78, 255), (105, 119, 120, 255), (39, 47, 52, 255)),
        "cave": ((38, 61, 83, 255), (66, 139, 152, 255), (25, 38, 59, 255)),
        "temple": ((71, 50, 82, 255), (151, 89, 153, 255), (42, 28, 52, 255)),
    }[palette]
    base, hi, low = colors
    d.rectangle((0, 5, 127, 63), fill=base)
    d.rectangle((0, 5, 127, 10), fill=hi)
    d.rectangle((0, 53, 127, 63), fill=low)
    for x in range(0, 128, 32):
        d.line((x, 10, x + 12, 53), fill=low, width=2)
        d.line((x + 13, 14, x + 30, 14), fill=hi, width=1)
    img.save(path)


def _background(path: Path, layer: str) -> None:
    img = Image.new("RGBA", (1280, 720), (9, 12, 26, 255))
    d = ImageDraw.Draw(img)
    if layer == "far":
        for y in range(720):
            t = y / 719
            color = (8 + int(12 * t), 10 + int(15 * t), 28 + int(35 * t), 255)
            d.line((0, y, 1280, y), fill=color)
        for i in range(75):
            x = (i * 173) % 1280
            y = 25 + (i * 97) % 380
            s = 1 + i % 3
            d.rectangle((x, y, x + s, y + s), fill=(120, 180, 210, 180))
        d.ellipse((885, 80, 1030, 225), fill=(178, 194, 215, 255))
        d.ellipse((930, 52, 1055, 195), fill=(14, 18, 38, 255))
    elif layer == "mid":
        for i in range(12):
            x = -100 + i * 130
            h = 150 + (i * 37) % 170
            d.polygon([(x, 570), (x + 100, 570), (x + 50, 570 - h)], fill=(20, 30, 48, 255))
            d.line((x + 50, 570 - h, x + 100, 570), fill=(48, 66, 77, 180), width=2)
    else:
        for i in range(30):
            x = i * 48
            h = 40 + (i * 23) % 130
            d.rectangle((x, 590 - h, x + 34, 590), fill=(12, 20, 31, 255))
            for wy in range(590 - h + 14, 585, 22):
                d.rectangle((x + 8, wy, x + 11, wy + 4), fill=(47, 134, 135, 150))
    img.save(path)


def _tone(path: Path, frequency: float, duration: float, *, volume: float = 0.32) -> None:
    rate = 22050
    total = int(rate * duration)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        frames = bytearray()
        for i in range(total):
            t = i / rate
            env = min(1.0, i / max(1, rate * 0.02)) * max(0.0, 1.0 - t / duration)
            sample = math.sin(2 * math.pi * frequency * t)
            sample += 0.28 * math.sin(2 * math.pi * frequency * 2.0 * t)
            value = int(max(-1.0, min(1.0, sample * volume * env)) * 32767)
            frames.extend(value.to_bytes(2, byteorder="little", signed=True))
        stream.writeframes(frames)


def _icon_assets(root: Path) -> None:
    img = Image.new("RGBA", (64, 64), (10, 8, 20, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((4, 4, 59, 59), outline=(94, 218, 213, 255), width=3)
    d.polygon([(32, 8), (51, 24), (43, 51), (21, 51), (13, 24)], fill=(53, 36, 88, 255))
    d.polygon([(32, 14), (44, 26), (38, 44), (26, 44), (20, 26)], fill=(170, 76, 184, 255))
    d.polygon([(32, 19), (39, 29), (32, 40), (25, 29)], fill=(92, 235, 225, 255))
    d.rectangle((29, 46, 35, 55), fill=(214, 221, 227, 255))
    icon_png = root / "shadow_relic_32.png"
    icon_ico = root / "shadow_relic_32.ico"
    img.resize((256, 256), Image.Resampling.NEAREST).save(icon_png)
    img.resize((256, 256), Image.Resampling.NEAREST).save(
        icon_ico,
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


def ensure_art() -> dict[str, str]:
    root = asset_root()
    root.mkdir(parents=True, exist_ok=True)
    marker = root / ".version"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == ART_VERSION:
        return {p.stem: str(p) for p in root.iterdir() if p.is_file() and not p.name.startswith(".")}

    for frame in range(2):
        _hero(root / f"hero_idle{frame}_r.png", "idle", frame)
        _mirror(root / f"hero_idle{frame}_r.png", root / f"hero_idle{frame}_l.png")
    for frame in range(4):
        _hero(root / f"hero_run{frame}_r.png", "run", frame)
        _mirror(root / f"hero_run{frame}_r.png", root / f"hero_run{frame}_l.png")
    for pose in ("jump", "hurt", "attack"):
        _hero(root / f"hero_{pose}_r.png", pose, 0)
        _mirror(root / f"hero_{pose}_r.png", root / f"hero_{pose}_l.png")

    for frame in range(2):
        _crawler(root / f"crawler{frame}_r.png", frame)
        _mirror(root / f"crawler{frame}_r.png", root / f"crawler{frame}_l.png")
        _wisp(root / f"wisp{frame}.png", frame)
        _cultist(root / f"cultist{frame}_r.png", frame)
        _mirror(root / f"cultist{frame}_r.png", root / f"cultist{frame}_l.png")
    for frame in range(3):
        _boss(root / f"warden{frame}_r.png", frame)
        _mirror(root / f"warden{frame}_r.png", root / f"warden{frame}_l.png")
    _npc(root / "archivist.png")

    _sigil(root / "sigil_sun.png", (247, 181, 69, 255), "sun")
    _sigil(root / "sigil_moon.png", (108, 203, 247, 255), "moon")
    _sigil(root / "sigil_void.png", (192, 91, 239, 255), "void")
    for kind in ("shard", "potion", "checkpoint", "portal"):
        _item(root / f"{kind}.png", kind)
    for palette in ("ruins", "cave", "temple"):
        _platform(root / f"platform_{palette}.png", palette)
    for layer in ("far", "mid", "front"):
        _background(root / f"bg_{layer}.png", layer)

    tones: dict[str, tuple[float, float]] = {
        "jump.wav": (460, 0.13),
        "slash.wav": (220, 0.10),
        "hit.wav": (115, 0.15),
        "pickup.wav": (760, 0.16),
        "checkpoint.wav": (540, 0.24),
        "boss_hit.wav": (155, 0.18),
        "win.wav": (880, 0.55),
    }
    for name, (freq, duration) in tones.items():
        _tone(root / name, freq, duration)

    _icon_assets(root)
    marker.write_text(ART_VERSION + "\n", encoding="utf-8")
    return {p.stem: str(p) for p in root.iterdir() if p.is_file() and not p.name.startswith(".")}


if __name__ == "__main__":
    paths = ensure_art()
    print(f"Generated {len(paths)} Shadow Relic 32 assets in {asset_root()}")
