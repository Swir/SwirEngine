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

import swirengine
from swirengine.editor_build_export_tooling21 import EditorBuildExportTooling21
from swirengine.exporting import PackagingProfile, ProjectExporter
from swirengine.ui_designer22 import (
    EditorUIDesignerError22,
    EditorUIDesignerTooling22,
    UIAnimationKeyframeSpec22,
    UIAnimationSpec22,
    UIAnimationTrackSpec22,
    UIDesignAsset22,
    UIStyleSpec22,
    UIWidgetSpec22,
)

_ENTRYPOINT = r'''
import hashlib
import json
import os
from pathlib import Path

import swirengine
from swirengine.ui_designer22 import EditorUIDesignerTooling22


class InputFrame:
    mouse_x = -10000.0
    mouse_y = -10000.0

    def __init__(self):
        self.keys = set()
        self.pad = set()

    def mouse_button_pressed(self, _button):
        return False

    def mouse_button_released(self, _button):
        return False

    def mouse_button(self, _button):
        return False

    def key_pressed(self, name):
        return name in self.keys

    def key(self, _name):
        return False

    def gamepads(self):
        return (0,)

    def gamepad_button_pressed(self, name, _device=0):
        return name in self.pad


root = Path(__file__).resolve().parent
tooling = EditorUIDesignerTooling22(root)
activated = []
runtime = tooling.build_runtime(handlers={"launch": lambda widget: activated.append(widget.id)})
report = {
    "engine_path": str(Path(swirengine.__file__).resolve()),
    "fingerprint": tooling.snapshot().fingerprint,
    "library_sha256": hashlib.sha256(tooling.target.read_bytes()).hexdigest(),
    "rendered": False,
}
backend = None
try:
    runtime.layout(1440, 720)
    menu = runtime.toolkit.find("menu")
    assert menu is not None
    wide_rect = [menu.rect.x, menu.rect.y, menu.rect.width, menu.rect.height]
    runtime.layout(720, 1280)
    tall_rect = [menu.rect.x, menu.rect.y, menu.rect.width, menu.rect.height]

    input_frame = InputFrame()
    input_frame.keys = {"tab"}
    runtime.update(input_frame, 720, 1280, dt=1.0 / 60.0)
    keyboard_focus = runtime.toolkit.focused.id
    input_frame.keys.clear()
    input_frame.pad = {"dpad_down"}
    runtime.update(input_frame, 720, 1280, dt=1.0 / 60.0)
    gamepad_focus = runtime.toolkit.focused.id
    input_frame.pad = {"dpad_up"}
    runtime.update(input_frame, 720, 1280, dt=1.0 / 60.0)
    input_frame.pad = {"a"}
    runtime.update(input_frame, 720, 1280, dt=1.0 / 60.0)

    runtime.play("pulse", restart=True)
    runtime.seek(0.5)
    play = runtime.toolkit.find("play")
    assert play is not None
    report.update(
        {
            "activated": activated,
            "animation_opacity": play.opacity,
            "gamepad_focus": gamepad_focus,
            "keyboard_focus": keyboard_focus,
            "tall_rect": tall_rect,
            "wide_rect": wide_rect,
        }
    )

    if os.environ.get("SWIR_UI_DESIGNER_REQUIRE_GL") == "1":
        import moderngl

        from swirengine.editor_render_backend21 import (
            EditorRenderBackend21,
            ResizableFramebufferTarget,
        )
        from swirengine.graphics.renderer import Renderer

        ctx = moderngl.create_standalone_context(require=330, backend="egl")
        target = ResizableFramebufferTarget(ctx, 320, 180)
        backend = EditorRenderBackend21(
            ctx=ctx,
            renderer=Renderer(ctx, 320, 180),
            target=target,
        )
        runtime.layout(320, 180)
        image = backend.viewport.capture(runtime.scene, 320, 180, mode="2d")
        assert len(image.rgb) == 320 * 180 * 3
        assert max(image.rgb) > min(image.rgb)
        assert ctx.error == "GL_NO_ERROR"
        report["rendered"] = True
        report["frame_sha256"] = hashlib.sha256(image.rgb).hexdigest()
finally:
    if backend is not None:
        backend.release()
    runtime.close()

print(json.dumps(report, sort_keys=True))
'''


def _asset() -> UIDesignAsset22:
    return UIDesignAsset22(
        reference_width=1280.0,
        reference_height=720.0,
        min_scale=0.25,
        max_scale=2.0,
        styles=(
            UIStyleSpec22(
                "primary",
                text=(1.0, 1.0, 1.0, 1.0),
                button=(0.10, 0.34, 0.72, 1.0),
                button_hover=(0.16, 0.48, 0.90, 1.0),
                button_focused=(0.24, 0.68, 1.0, 1.0),
                font_size=22.0,
            ),
        ),
        widgets=(
            UIWidgetSpec22(
                "menu",
                "panel",
                order=0,
                width=520.0,
                height=400.0,
                gap=18.0,
                padding=(24.0, 24.0, 24.0, 24.0),
                anchor="top_left",
                offset_x=24.0,
                offset_y=-24.0,
            ),
            UIWidgetSpec22(
                "title",
                "label",
                parent="menu",
                order=0,
                width=400.0,
                height=48.0,
                text="NEON CONTROL",
            ),
            UIWidgetSpec22(
                "play",
                "button",
                parent="menu",
                order=1,
                width=320.0,
                height=64.0,
                text="PLAY",
                style="primary",
                action="launch",
            ),
            UIWidgetSpec22(
                "options",
                "button",
                parent="menu",
                order=2,
                width=320.0,
                height=64.0,
                text="OPTIONS",
            ),
            UIWidgetSpec22(
                "loading",
                "progress",
                parent="menu",
                order=3,
                width=320.0,
                height=24.0,
                value=0.72,
            ),
        ),
        animations=(
            UIAnimationSpec22(
                "pulse",
                1.0,
                (
                    UIAnimationTrackSpec22(
                        "play",
                        "opacity",
                        (
                            UIAnimationKeyframeSpec22(0.0, 1.0),
                            UIAnimationKeyframeSpec22(1.0, 0.3),
                        ),
                    ),
                ),
            ),
        ),
    )


def _project(tmp_path: Path) -> tuple[Path, EditorUIDesignerTooling22]:
    root = tmp_path / "ui-shipping"
    root.mkdir()
    (root / "assets").mkdir()
    (root / "assets" / "marker.txt").write_text("ui-designer\n", encoding="utf-8")
    (root / "main.py").write_text(_ENTRYPOINT, encoding="utf-8")
    tooling = EditorUIDesignerTooling22(root)
    tooling.replace_asset(_asset())
    tooling.save()
    return root, tooling


def test_ui_designer_survives_default_wizard_export_and_relocation(tmp_path: Path) -> None:
    root, tooling = _project(tmp_path)
    canonical = tooling.target.read_bytes()
    fingerprint = tooling.snapshot().fingerprint

    # A declared action cannot silently become an unbound production callback.
    with pytest.raises(EditorUIDesignerError22, match="(?i)(action|handler)"):
        tooling.build_runtime()
    callbacks: list[str] = []
    runtime = tooling.build_runtime(
        handlers={"launch": lambda widget: callbacks.append(widget.id)}
    )
    try:
        assert callbacks == []
    finally:
        runtime.close()

    wizard = EditorBuildExportTooling21(root, project_name="UIShipping")
    assert "config" not in wizard.config.active.include
    plan = wizard.preflight()
    assert Path("config/ui-designer.json") in plan.files

    exported = wizard.stage()
    manifest = json.loads(exported.manifest.read_text(encoding="utf-8"))
    digest = hashlib.sha256(canonical).hexdigest()
    assert manifest["sha256"]["config/ui-designer.json"] == digest
    assert "config/ui-designer.json" in exported.native_spec.read_text(encoding="utf-8")

    relocated = tmp_path / "relocated-ui"
    shutil.move(str(exported.output_dir), relocated)
    root.rename(tmp_path / "authoring-unavailable")
    assert not root.exists()

    reopened = EditorUIDesignerTooling22(relocated)
    assert reopened.target.read_bytes() == canonical
    assert reopened.snapshot().fingerprint == fingerprint

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    isolated = env.get("SWIR_UI_DESIGNER_INSTALLED_ONLY") == "1"
    if not isolated:
        env["PYTHONPATH"] = str(Path(swirengine.__file__).resolve().parent.parent)
    completed = subprocess.run(
        [sys.executable, *(["-I"] if isolated else []), str(relocated / "main.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=True,
    )
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    assert report["fingerprint"] == fingerprint
    assert report["library_sha256"] == digest
    assert report["keyboard_focus"] == "play"
    assert report["gamepad_focus"] == "options"
    assert report["activated"] == ["play"]
    assert report["animation_opacity"] == pytest.approx(0.65)
    assert report["wide_rect"] != report["tall_rect"]
    if isolated:
        assert "site-packages" in Path(report["engine_path"]).parts
        assert not Path(report["engine_path"]).is_relative_to(Path(__file__).resolve().parents[1])
    if env.get("SWIR_UI_DESIGNER_REQUIRE_GL") == "1":
        assert report["rendered"]
    assert (relocated / "config/ui-designer.json").read_bytes() == canonical
    print(json.dumps(report, sort_keys=True))


@pytest.mark.parametrize("excluded", ("config", "config/ui-designer.json"))
def test_export_rejects_explicit_ui_designer_exclusion_before_cleanup(
    tmp_path: Path,
    excluded: str,
) -> None:
    root, _tooling = _project(tmp_path)
    output = tmp_path / "previous-package"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("retained", encoding="utf-8")
    profile = PackagingProfile(app_name="ui-shipping")
    profile = replace(profile, exclude=(*profile.exclude, excluded))

    with pytest.raises(ValueError, match="excludes declared UI Designer"):
        ProjectExporter(root).export(profile, output)

    assert sentinel.read_text(encoding="utf-8") == "retained"
    assert sorted(path.name for path in output.iterdir()) == ["keep.txt"]


def test_invalid_ui_designer_fails_preflight_before_cleanup(tmp_path: Path) -> None:
    root, tooling = _project(tmp_path)
    tooling.target.write_text("{invalid", encoding="utf-8")
    output = tmp_path / "previous-package"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("retained", encoding="utf-8")

    with pytest.raises(ValueError, match="UI Designer export preflight"):
        ProjectExporter(root).export(PackagingProfile(), output)

    assert sentinel.read_text(encoding="utf-8") == "retained"


def test_ui_designer_export_rejects_symlink_escape(tmp_path: Path) -> None:
    root, tooling = _project(tmp_path)
    outside = tmp_path / "outside-ui-designer.json"
    outside.write_bytes(tooling.target.read_bytes())
    tooling.target.unlink()
    try:
        tooling.target.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    with pytest.raises(ValueError, match="UI Designer export preflight"):
        ProjectExporter(root).plan(PackagingProfile())


def test_ui_designer_directory_fails_before_export_cleanup(tmp_path: Path) -> None:
    root, tooling = _project(tmp_path)
    tooling.target.unlink()
    tooling.target.mkdir()
    output = tmp_path / "previous-directory-package"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("retained", encoding="utf-8")

    with pytest.raises(ValueError, match="UI Designer export preflight"):
        ProjectExporter(root).export(PackagingProfile(), output)

    assert sentinel.read_text(encoding="utf-8") == "retained"


def test_ui_designer_dangling_symlink_fails_before_export_cleanup(tmp_path: Path) -> None:
    root, tooling = _project(tmp_path)
    tooling.target.unlink()
    missing = tooling.target.parent / "missing-ui-designer.json"
    try:
        tooling.target.symlink_to(missing)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    output = tmp_path / "previous-dangling-package"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("retained", encoding="utf-8")

    with pytest.raises(ValueError, match="UI Designer export preflight"):
        ProjectExporter(root).export(PackagingProfile(), output)

    assert sentinel.read_text(encoding="utf-8") == "retained"


def test_ui_designer_tooling_rejects_parent_traversal(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()

    with pytest.raises(EditorUIDesignerError22, match="(?i)(project-relative|inside|traversal)"):
        EditorUIDesignerTooling22(root, path="../outside.json")


def test_project_without_ui_designer_keeps_legacy_export_inventory(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    (root / "main.py").write_text("print('legacy')\n", encoding="utf-8")
    plan = ProjectExporter(root).plan(PackagingProfile())

    assert plan.files == (Path("main.py"),)
    assert not (root / "config/ui-designer.json").exists()
