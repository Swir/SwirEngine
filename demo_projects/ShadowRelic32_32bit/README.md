# Shadow Relic 32 — The Moon Temple

**Shadow Relic 32** is an original 32-bit-console-era platform adventure built as a real
**SwirEngine 2.2.x** demo project. It is designed to feel like a late-90s 2D action-adventure
while using SwirEngine systems for the actual runtime rather than embedding a separate mini-engine.

## What is in the game

- large scrolling world split into **Drowned Ruins**, **Crystal Caverns** and **Moon Temple**
- SwirEngine `PhysicsWorld2D` / `RigidBody2D` / `CollisionWorld2D` player movement
- sword combat (`X` / `J`) plus stomp combat
- crawler, wisp and cultist enemies
- an NPC Archivist with multi-line interaction (`E`)
- three persistent Moon Temple sigils that unlock the temple gate
- checkpoints with real `SaveStore` persistence
- healing potions and optional crystal shards
- final **Shadow Warden** boss with 7 HP
- ending portal and persistent boss completion
- parallax backgrounds, particles, HUD, screen-space overlays and optional generated audio
- deterministic headless physics/save probe for CI or quick validation
- original procedural 32-bit-style artwork and sound generated on first launch
- original **Shadow Relic** application icon (`shadow_relic_icon.ppm` source + generated PNG/ICO)

No third-party game artwork, characters, level layouts or music are used.

## Run

From this directory:

```bash
python -m swirengine doctor . --profile windows
python -m swirengine run .
```

or on Windows double-click:

```text
run_demo.bat
```

Direct source launch also works:

```bash
python main.py
```

## Controls

- `A` / `D` or Left / Right — move
- `Space` — jump
- `X` or `J` — relic-blade attack
- `E` — talk to the Archivist
- `R` — respawn at the latest checkpoint
- `N` — erase adventure progress and start a new run

## Headless validation

```bash
set SHADOW_RELIC_HEADLESS=1
python main.py
```

The probe exercises the real SwirEngine 2D collision/rigid-body stack plus `SaveStore`.

For a renderer smoke boot, for example:

```bash
set SHADOW_RELIC_SMOKE_FRAMES=180
python main.py
```

## SwirEngine native export

The project contains a real `swirproject.toml` with Windows/Linux/macOS profiles.
On a matching host with PyInstaller installed:

```bash
python -m swirengine export . --profile windows --build-native
```

## True 32-bit Windows EXE

The game itself uses a **32-bit-era visual style** on any supported SwirEngine host. If you also
want a literal 32-bit Windows executable, run `build_win32.bat` from a **32-bit Python** environment
whose SwirEngine/OpenGL dependencies support x86. The script refuses to claim Win32 when Python is
actually 64-bit.

The build script generates the original ICO from source before invoking PyInstaller.
