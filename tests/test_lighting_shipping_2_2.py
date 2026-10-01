from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

import swirengine
from swirengine.editor_integrated_session21 import EditorIntegratedProjectSession21
from swirengine.editor_lighting22 import EditorLightingPanelController22, LightingSceneSource22
from swirengine.exporting import PackagingProfile, ProjectExporter
from swirengine.graphics.primitives import Cube3D, Rectangle2D
from swirengine.lighting_authoring22 import EditorLightingTooling22, LightSpec22
from swirengine.math.types import Color, Vec3
from swirengine.project_scaffold21 import new_project21

# This source-only fixture uses the same public runtime bridge a shipped game uses.
# It is relocated and executed without the authoring project present at its old path.
_ENTRYPOINT = r'''
import hashlib
import json
import os
from pathlib import Path

import swirengine
from swirengine.core.game import Game
from swirengine.graphics.lights import select_lights
from swirengine.lighting_authoring22 import EditorLightingTooling22
from swirengine.serialization import SceneSerializer

root = Path(__file__).resolve().parent
tooling = EditorLightingTooling22(root)
spec = tooling.profiles()[0]
runtime = tooling.build_runtime(spec.scene)
game = Game(mode=spec.mode, width=96, height=96)
game.scene = SceneSerializer().load_scene(root / spec.scene)
mount = runtime.apply_to_game(game)
report = {
    "fingerprint": spec.fingerprint,
    "exposure": game.postprocess.exposure,
    "mode": game.mode,
    "lights": select_lights(game.scene.objects, default_directional=False).total,
    "library_sha256": hashlib.sha256(tooling.target.read_bytes()).hexdigest(),
    "engine_path": str(Path(swirengine.__file__).resolve()),
    "rendered": False,
}
try:
    if os.environ.get("SWIR_LIGHTING_REQUIRE_GL") == "1":
        import moderngl
        from swirengine.graphics.csm_renderer import Renderer2
        from swirengine.graphics.postprocess import PostProcessRenderer
        from swirengine.editor_render_backend21 import EditorRenderBackend21, ResizableFramebufferTarget
        from swirengine.editor_lighting22 import _PreviewContext
        from swirengine.graphics.renderer import Renderer
        ctx = moderngl.create_standalone_context(require=330, backend="egl")
        target = ResizableFramebufferTarget(ctx, 96, 96)
        backend = EditorRenderBackend21(ctx=ctx, renderer=Renderer(ctx, 96, 96), target=target)
        renderer = None
        try:
            target.activate()
            screen = _PreviewContext(backend)
            renderer = (
                Renderer2(screen, 96, 96, game.mode, postprocess=game.postprocess,
                          renderer2=game.renderer2_settings)
                if game.mode == "3d" else
                PostProcessRenderer(screen, 96, 96, game.mode, postprocess=game.postprocess)
            )
            renderer.render(game.scene, camera=game.camera)
            ctx.finish()
            pixels = target.framebuffer.read(components=3, alignment=1)
            assert len(pixels) == 96 * 96 * 3 and max(pixels) > min(pixels)
            assert ctx.error == "GL_NO_ERROR"
            report["rendered"] = True
            report["frame_sha256"] = hashlib.sha256(pixels).hexdigest()
            report["nonuniform_frame"] = True
        finally:
            if renderer is not None:
                renderer.release()
            backend.release()
finally:
    mount.unmount()
print(json.dumps(report, sort_keys=True))
'''


def _project(tmp_path: Path, mode: str):
    root = new_project21("LightingShipping", mode, parent=tmp_path)
    session = EditorIntegratedProjectSession21.open(root)
    obj = (Cube3D(position=Vec3(0, 0, -4), color=Color(.6, .4, .2, 1)) if mode == "3d"
           else Rectangle2D(24, 24, 48, 48, Color(.6, .4, .2, 1)))
    session.workspace.scene.add(obj)
    source = LightingSceneSource22(session.scenes.active_path, mode, session.workspace.scene,
                                  session.controller.camera_3d if mode == "3d"
                                  else session.controller.camera_2d, session.serializer)
    panel = EditorLightingPanelController22(session.lighting, lambda: source)
    panel.update_section("postfx", exposure=1.7, fxaa=False)
    if mode == "3d":
        panel.set_light(LightSpec22("sun"))
        panel.update_section("renderer", shadow_resolution=128, shadow_cascades=2,
                             ssao_samples=8, bloom_levels=2)
        # A real decodable project image: live GL verification must not use fake bytes.
        Image.new("RGB", (16, 8), (24, 36, 64)).save(root / "assets" / "sky.png")
        panel.update_section("environment", enabled=True, skybox_texture="sky.png")
    session.save()
    (root / "main.py").write_text(_ENTRYPOINT, encoding="utf-8")
    return session, panel


@pytest.mark.parametrize("mode", ("2d", "3d"))
def test_creator_lighting_survives_default_wizard_export_and_relocation(tmp_path: Path, mode: str) -> None:
    session, panel = _project(tmp_path, mode)
    root = session.manifest.root
    canonical = session.lighting.target.read_bytes()
    fingerprint = panel.spec().fingerprint
    # Default wizard profile does NOT explicitly include config: declared lighting must still ship.
    assert "config" not in session.build_export.config.active.include
    plan = session.build_export.preflight()
    assert Path("config/lighting.json") in plan.files
    exported = session.build_export.stage()
    manifest = json.loads(exported.manifest.read_text())
    assert manifest["sha256"]["config/lighting.json"] == hashlib.sha256(canonical).hexdigest()
    assert "config/lighting.json" in exported.native_spec.read_text()
    if mode == "3d":
        assert "assets/sky.png" in manifest["files"]
    relocated = tmp_path / "relocated-game"
    shutil.move(str(exported.output_dir), relocated)
    root.rename(tmp_path / "authoring-unavailable")
    assert not root.exists()
    reopened = EditorLightingTooling22(relocated)
    assert reopened.target.read_bytes() == canonical
    assert reopened.profiles()[0].fingerprint == fingerprint
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    isolated = env.get("SWIR_LIGHTING_INSTALLED_ONLY") == "1"
    if not isolated:
        env["PYTHONPATH"] = str(Path(swirengine.__file__).resolve().parent.parent)
    completed = subprocess.run(
        [sys.executable, *(["-I"] if isolated else []), str(relocated / "main.py")],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=90, check=True,
    )
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["mode"] == mode and report["exposure"] == 1.7
    assert report["fingerprint"] == fingerprint
    assert report["library_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert report["lights"] == (3 if mode == "3d" else 0)
    if isolated:
        assert "site-packages" in Path(report["engine_path"]).parts
        assert not Path(report["engine_path"]).is_relative_to(Path(__file__).resolve().parents[1])
    if env.get("SWIR_LIGHTING_REQUIRE_GL") == "1":
        assert report["rendered"] and report["nonuniform_frame"]
    assert (relocated / "config/lighting.json").read_bytes() == canonical
    # Preserve concrete evidence in pytest output for installed + real GL qualification.
    print(json.dumps(report, sort_keys=True))


@pytest.mark.parametrize("excluded", ("config", "config/lighting.json", "scenes", "assets"))
def test_export_rejects_excluded_lighting_dependencies_before_mutation(tmp_path: Path, excluded: str) -> None:
    session, _ = _project(tmp_path, "3d")
    output = tmp_path / "previous-package"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("retained", encoding="utf-8")
    profile = replace(session.build_export.config.active,
                      exclude=(*session.build_export.config.active.exclude, excluded))
    with pytest.raises(ValueError, match="excludes declared lighting"):
        ProjectExporter(session.manifest.root).export(profile, output)
    assert sentinel.read_text() == "retained"
    assert sorted(path.name for path in output.iterdir()) == ["keep.txt"]


@pytest.mark.parametrize("resource", ("scene", "skybox", "library"))
@pytest.mark.parametrize("failure", ("missing", "symlink"))
def test_lighting_export_fails_closed_for_invalid_resources(
    tmp_path: Path, resource: str, failure: str,
) -> None:
    session, panel = _project(tmp_path, "3d")
    paths = {"scene": session.manifest.root / panel.spec().scene,
             "skybox": session.manifest.root / "assets/sky.png", "library": session.lighting.target}
    target = paths[resource]
    saved = target.read_bytes()
    target.unlink()
    if failure == "symlink":
        outside = tmp_path / "outside-resource"
        outside.write_bytes(saved)
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable")
    elif resource == "library":
        # A present malformed config opts in; an absent library deliberately keeps legacy export.
        target.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="lighting export preflight"):
        session.build_export.preflight()


def test_projects_without_lighting_keep_the_existing_export_contract(tmp_path: Path) -> None:
    root = new_project21("LegacyExport", "2d", parent=tmp_path)
    plan = ProjectExporter(root).plan(PackagingProfile())
    assert Path("config/lighting.json") not in plan.files
    assert not (root / "config/lighting.json").exists()
