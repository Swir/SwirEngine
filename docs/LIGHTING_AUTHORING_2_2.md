# Lighting, Environment and Post-FX authoring — 2.2 M7

This is runtime-backed M7 development, not completed M7 acceptance and not a public 2.2 release. The authoritative roadmap remains 6/10 = 60.0%; public stable remains 2.1.0.

## Included in this slice

`EditorLightingTooling22` owns versioned, deterministic `config/lighting.json`. Profiles are keyed by project-relative scene path, with sorted lights and canonical JSON. `EditorIntegratedProjectSession21.lighting` participates in dirty/save/reopen and unsaved-close decisions alongside existing creator tools.

3D profiles map to the existing shipping `DirectionalLight3D`, `PointLight3D`, `SpotLight3D`, `Environment3D`, `Skybox3D`, `Renderer2Settings` and `PostProcessSettings`. 2D profiles use the shipping post-processing pipeline only. Nothing in this module substitutes an editor simulation for the runtime.

Authoring includes light intensity/color/position/direction/range/cones, sky/ground lighting and an optional skybox texture, directional-shadow cascades and resolution, SSAO/bloom settings, tone mapping, exposure, gamma, contrast, saturation, vignette and FXAA.

## Unified creator panel

Open **Lighting / Environment / Post-FX…** from the SwirEditor creator menu. The panel follows the active project scene; its five tabs expose Lights, Environment, Shadows, Effects and Color grading. Light names identify add/update targets; remove operates on the selected light. Apply validates and updates the active scene profile atomically. Save lighting profiles writes the same library included in ordinary project saves. 2D disables the 3D-only authoring actions.

**Start / refresh scene** snapshots the active scene using the project's registered serializer and creates an isolated preview with its own production renderer and GPU context. No game scripts are run. **Apply** updates live lighting on the next preview tick; **Pause** retains the image and runtime, **Step** renders one frame, and **Stop** releases the owned preview. Editing project geometry requires Start / refresh scene again; the panel intentionally does not reserialize the entire authoring scene every frame.

The UI renders at most one 480x320 capture per 100 ms tick, without catch-up. The preview API caps each image dimension at 1024 and rejects snapshots over 4096 objects/entities or 4 MiB serialized data. These are editor preview budgets, not engine scene-size limits or FPS guarantees. The existing main viewport, authoring objects, game scripts and original renderer settings are never modified: closing or failing the isolated preview requires no mutation to restore them.

Switching scenes (or reopening a different Scene object at the same path) stops the preview and clears its image rather than applying the old profile to the new scene. Missing or escaping live skybox resources also stop it. A changed profile or asset metadata signature rebuilds the preview once; unchanged captures reuse the owned renderer. Skybox camera following uses a copied current editor camera. Window close cancels the tick and releases the context; reopening starts stopped.

## Source-development example

Run against a source checkout containing this slice and an existing 3D project. Adjust the scene key to match that project. Scene keys are confined relative paths; the library may be authored before the scene file is created, so this API alone does not prove the scene exists or loads. Export requires the bound scene file to exist.

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

`apply_to_game` is intentionally a **before-Game.run** API. It refuses a running game or a mismatched mode, checks combined existing/authored light budgets, mounts individually owned light/skybox objects and configures the shipping renderer. Build a fresh runtime per game. Unmount removes only this mount's scene objects; it does not restore global render settings. Skybox position is initially aligned to the camera; a moving-camera application should call the shipping `skybox.follow(game.camera)` in its update loop. This game-install API is distinct from the fully isolated editor preview described above.

3D uses Renderer2, which requires the post-processing resolve. To request a neutral resolve use supported neutral tone mapping and neutral settings rather than disabling its resolve. A 2D profile cannot silently contain ignored 3D lights or an environment.

## Portable Build/Export workflow

A present `config/lighting.json` opts the project into lighting export validation. The normal `ProjectExporter` and integrated Build/Export Wizard include that library, every bound scene file and every referenced skybox texture even when the packaging profile uses the default `assets/scenes/scripts` includes. They record the files in the export manifest with SHA-256 hashes and include them in the generated native packaging spec.

Invalid libraries, missing scene/texture dependencies, escaping symlinks and packaging exclusions that would omit declared lighting data fail preflight **before the previous output directory is cleaned**. A project with no lighting library keeps its existing export behavior. Validation does not silently skip an excluded resource or publish an export with missing settings.

The game entrypoint must load its scene and apply the appropriate profile through `EditorLightingTooling22.build_runtime(...).apply_to_game(...)`, as above. Export preserves authored data; it does not inject arbitrary lighting setup into an existing game script or automatically switch profiles during gameplay. Packaged applications still use their established resource-root resolution.

The representative 2D/3D shipping tests use the real integrated editor session and default Wizard to author, save and stage a project. They relocate the stage, move the original project away, then launch the staged entrypoint in a separate process. Canonical profile bytes, fingerprint, exposure and light counts must remain unchanged. The required installed-runtime gate uses isolated Python (`-I`) and verifies that the engine comes from the installed wheel's `site-packages`, not the checkout. Under the explicit EGL gate it renders both relocated projects with real OpenGL, including a decodable project skybox for 3D. This is staged/installed-runtime evidence, not a claim that a new Windows executable or 2.2 release was published.

## Safety and deterministic persistence

- Booleans, integers and finite numeric fields are validated without lossy integer coercion. Persisted objects reject unknown fields, duplicate JSON keys, duplicate normalized light names and duplicate scene bindings.
- At most 128 scene profiles and 256 KiB canonical input/output; a rejected reload never replaces the previous live library or its dirty state.
- Save uses a same-directory temporary file, flush/fsync and atomic replacement. Replacement failure preserves the original file and unsaved changes and cleans its temporary file.
- Scene/library paths stay within the project. Skybox references stay beneath the resolved project `assets/` directory and are re-resolved on every runtime build, including nested and replaced-root symlinks. Missing resources fail closed before installation. This is not a claim against adversarial simultaneous filesystem races.
- Skybox image decoding still belongs to the shipping renderer; file existence/path validation is not proof that arbitrary image bytes decode successfully. Preview decoder/render errors close the owned preview and surface an error rather than claiming successful rendering.
- Each light kind is capped at four; enabled environment illumination consumes two directional slots. Existing scene lights are included at installation so authored lights cannot silently displace them.
- Renderer settings retain shipping validation, with editor bounds on shadow resolution and decal count (4096). This is a bounded authoring policy, not a claim of equal memory/FPS on every GPU.

## Verification

```bash
python -m pytest -q tests/test_lighting_authoring_2_2.py tests/test_lighting_editor_2_2.py tests/test_lighting_shipping_2_2.py
# Linux with Mesa/EGL and project dependencies installed:
SWIR_LIGHTING_REQUIRE_GL=1 python -m pytest -v tests/test_lighting_opengl_2_2.py tests/test_lighting_editor_opengl_2_2.py
SWIR_LIGHTING_REQUIRE_TK=1 xvfb-run -a python -m pytest -v tests/test_lighting_editor_tk_2_2.py
# Install the current source as a non-editable wheel before the isolated child-process gate:
python -m pip install ".[dev]"
SWIR_LIGHTING_REQUIRE_GL=1 SWIR_LIGHTING_INSTALLED_ONLY=1 python -m pytest -v -s tests/test_lighting_shipping_2_2.py -k survives_default_wizard_export_and_relocation
```

The focused `Editor Lighting 2.2` workflow requires real EGL tests; an unavailable context or dependency fails that step instead of skipping it. They render saved/reopened 2D and 3D profiles, live controller changes and relocated exports to real framebuffers. Native Tk tests exercise the real panel widgets/event loop with a CPU capture probe; they are not GPU evidence. The separate EGL tests exercise the production preview renderer. The generic cross-platform suite skips the environment-specific files unless their explicit required-gate switches are enabled, but still runs the shipping validation and CPU-side relocated-runtime tests. CPU-side persistence/runtime tests never count as GPU evidence.

## Remaining M7 acceptance work

The unified panel, isolated continuous preview, cleanup, scene switching and declared lighting export integration are implemented in this development branch. Exact-final-head CI, installed/EGL shipping qualification, final acceptance review and post-merge main qualification remain required before M7 can receive a checkmark. No release or additional platform support is implied by this slice.
