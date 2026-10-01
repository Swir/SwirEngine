# Lighting, Environment and Post-FX authoring — 2.2 M7 foundation

This is the first runtime-backed M7 slice, not completed M7 acceptance and not a public 2.2 release. The authoritative roadmap remains 6/10 = 60.0%; public stable remains 2.1.0.

## Included in this slice

`EditorLightingTooling22` owns versioned, deterministic `config/lighting.json`. Profiles are keyed by project-relative scene path, with sorted lights and canonical JSON. `EditorIntegratedProjectSession21.lighting` participates in dirty/save/reopen and unsaved-close decisions alongside existing creator tools.

3D profiles map to the existing shipping `DirectionalLight3D`, `PointLight3D`, `SpotLight3D`, `Environment3D`, `Skybox3D`, `Renderer2Settings` and `PostProcessSettings`. 2D profiles use the shipping post-processing pipeline only. Nothing in this module substitutes an editor simulation for the runtime.

Authoring includes light intensity/color/position/direction/range/cones, sky/ground lighting and an optional skybox texture, directional-shadow cascades and resolution, SSAO/bloom settings, tone mapping, exposure, gamma, contrast, saturation, vignette and FXAA.

## Source-development example

Run against a source checkout containing this slice and an existing 3D project. Adjust the scene key to match that project. Scene keys are confined relative paths; the library may be authored before the scene file is created, so this API alone does not prove the scene exists or loads.

```python
from pathlib import Path
from swirengine import Game
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.graphics.renderer2 import Renderer2Settings
from swirengine.lighting_authoring22 import (
    EnvironmentSpec22, LightSpec22, PostFXSpec22, SceneLightingSpec22,
)

root = Path("My3DProject")
session = EditorIntegratedProjectSession21.open(root)
profile = SceneLightingSpec22(
    scene="scenes/main.swirscene",
    lights=(LightSpec22("sun", intensity=1.2),),
    environment=EnvironmentSpec22(enabled=True),
    postfx=PostFXSpec22(exposure=1.5, tone_mapping="aces"),
    renderer=Renderer2Settings(shadow_resolution=1024, shadow_cascades=2),
)
session.lighting.set_profile(profile)
session.save()

reopened = EditorIntegratedProjectSession21.open(root)
runtime = reopened.lighting.build_runtime(profile.scene)
game = Game("Lighting profile", mode="3d")
# Add/load the game's scene objects here; this library does not load the scene itself.
mount = runtime.apply_to_game(game)
try:
    game.run()
finally:
    mount.unmount()
```

`apply_to_game` is intentionally a **before-Game.run** API. It refuses a running game or a mismatched mode, checks combined existing/authored light budgets, mounts individually owned light/skybox objects and configures the shipping renderer. Build a fresh runtime per game. Unmount removes only this mount's scene objects; it does not restore global render settings. Skybox position is initially aligned to the camera; a moving-camera application should call the shipping `skybox.follow(game.camera)` in its update loop.

3D uses Renderer2, which requires the post-processing resolve. To request a neutral resolve use supported neutral tone mapping and neutral settings rather than disabling its resolve. A 2D profile cannot silently contain ignored 3D lights or an environment.

## Safety and deterministic persistence

- Booleans, integers and finite numeric fields are validated without lossy integer coercion. Persisted objects reject unknown fields, duplicate JSON keys, duplicate normalized light names and duplicate scene bindings.
- At most 128 scene profiles and 256 KiB canonical input/output; a rejected reload never replaces the previous live library or its dirty state.
- Save uses a same-directory temporary file, flush/fsync and atomic replacement. Replacement failure preserves the original file and unsaved changes and cleans its temporary file.
- Scene/library paths stay within the project. Skybox references stay beneath the resolved project `assets/` directory and are re-resolved on every runtime build, including nested and replaced-root symlinks. Missing resources fail closed before installation. This is not a claim against adversarial simultaneous filesystem races.
- Skybox image decoding still belongs to the shipping renderer; file existence/path validation is not proof that arbitrary image bytes decode successfully.
- Each light kind is capped at four; enabled environment illumination consumes two directional slots. Existing scene lights are included at installation so authored lights cannot silently displace them.
- Renderer settings retain shipping validation, with editor bounds on shadow resolution and decal count (4096). This is a bounded authoring policy, not a claim of equal memory/FPS on every GPU.

## Verification

```bash
python -m pytest -q tests/test_lighting_authoring_2_2.py
# Linux with Mesa/EGL and project dependencies installed:
SWIR_LIGHTING_REQUIRE_GL=1 python -m pytest -v tests/test_lighting_opengl_2_2.py
```

The focused `Editor Lighting 2.2` workflow requires the real EGL tests; an unavailable context or dependency fails that step instead of skipping it. They render saved/reopened 2D and 3D profiles to real framebuffers and compare exposure-dependent output. The generic cross-platform test suite skips that optional GL file unless the explicit EGL gate is enabled. CPU-side persistence/runtime tests never count as GPU evidence.

## Remaining M7 acceptance work

The unified creator-facing Lighting/Environment/Post-FX panel, continuous viewport preview updates with safe state restoration, scene-switch lifecycle and staged/exported representative game validation still need implementation and qualification. This foundation deliberately does not claim those surfaces exist. Complete M7 also requires full final-head repository CI, real renderer validation and post-merge main qualification before the next roadmap checkmark.
