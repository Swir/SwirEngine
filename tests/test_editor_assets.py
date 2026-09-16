import pytest

from swirengine import AssetManager
from swirengine.editor_assets import (
    EditorAssetBrowser,
    EditorAssetDragPayload,
    classify_editor_asset,
)


def test_classify_editor_asset_covers_creator_facing_types():
    assert classify_editor_asset("hero.png") == "image"
    assert classify_editor_asset("music.ogg") == "audio"
    assert classify_editor_asset("ship.glb") == "model"
    assert classify_editor_asset("font.ttf") == "font"
    assert classify_editor_asset("scene.json") == "data"
    assert classify_editor_asset("lit.frag") == "shader"
    assert classify_editor_asset("game.py") == "script"
    assert classify_editor_asset("readme.txt") == "other"


def test_asset_browser_builds_metadata_filters_folders_and_aliases(tmp_path):
    root = tmp_path / "assets"
    (root / "textures" / "ui").mkdir(parents=True)
    (root / "audio").mkdir()
    (root / "models").mkdir()
    (root / "textures" / "hero.png").write_bytes(b"png")
    (root / "textures" / "ui" / "button.webp").write_bytes(b"webp")
    (root / "audio" / "theme.ogg").write_bytes(b"ogg")
    (root / "models" / "ship.glb").write_bytes(b"glb")

    manager = AssetManager(root)
    manager.register("hero", "textures/hero.png")
    manager.register_loader(".png", lambda path: path.read_bytes())
    manager.load("hero")
    browser = EditorAssetBrowser(manager)

    frame = browser.frame()
    hero = next(entry for entry in frame.entries if entry.name == "hero.png")
    assert frame.total_files == 4
    assert frame.total_bytes == 13
    assert frame.folders == ("audio", "models", "textures", "textures/ui")
    assert set(frame.kinds) == {"audio", "image", "model"}
    assert hero.aliases == ("hero",)
    assert hero.cached
    assert hero.loadable

    image_frame = browser.set_filter(kind="image", folder="textures")
    assert [entry.name for entry in image_frame.entries] == ["hero.png", "button.webp"]
    assert [entry.name for entry in browser.set_filter("hero").entries] == ["hero.png"]


def test_asset_browser_selection_survives_refresh_and_clears_when_deleted(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    path = root / "player.png"
    path.write_bytes(b"data")
    browser = EditorAssetBrowser(AssetManager(root))

    selected = browser.select("player.png")
    assert selected is not None
    assert browser.selected_key == "player.png"
    assert browser.resolve_selected() == path
    assert browser.refresh().selected_key == "player.png"

    path.unlink()
    frame = browser.refresh()
    assert frame.selected_key is None
    assert browser.selected_entry is None


def test_asset_browser_drag_payload_is_portable_and_filter_independent(tmp_path):
    root = tmp_path / "assets"
    (root / "textures").mkdir(parents=True)
    (root / "audio").mkdir()
    (root / "textures" / "hero.png").write_bytes(b"png")
    (root / "audio" / "theme.ogg").write_bytes(b"ogg")
    browser = EditorAssetBrowser(AssetManager(root))
    browser.select("textures/hero.png")

    browser.set_filter(kind="audio")
    selected_payload = browser.drag_payload()
    explicit_payload = browser.drag_payload("audio/theme.ogg")

    assert selected_payload == EditorAssetDragPayload(
        "textures/hero.png", "hero.png", "image", ".png"
    )
    assert explicit_payload == EditorAssetDragPayload(
        "audio/theme.ogg", "theme.ogg", "audio", ".ogg"
    )
    assert not selected_payload.relative_path.startswith(str(root))


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/tmp/hero.png",
        "../hero.png",
        r"C:\temp\hero.png",
        r"\\server\share\hero.png",
    ],
)
def test_asset_drag_payload_rejects_host_absolute_and_parent_paths(unsafe_path):
    with pytest.raises(ValueError, match="project-relative"):
        EditorAssetDragPayload(unsafe_path, "hero.png", "image", ".png")


def test_asset_browser_rejects_host_absolute_lookup_even_if_basename_exists(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    (root / "player.png").write_bytes(b"data")
    browser = EditorAssetBrowser(AssetManager(root))

    with pytest.raises(ValueError, match="project-relative"):
        browser.select("/player.png")
    with pytest.raises(ValueError, match="project-relative"):
        browser.drag_payload(r"C:\assets\player.png")


def test_asset_browser_drag_requires_a_real_asset(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    browser = EditorAssetBrowser(AssetManager(root))

    try:
        browser.drag_payload()
    except RuntimeError as exc:
        assert "no editor asset selected" in str(exc)
    else:
        raise AssertionError("drag without a selection should fail")

    try:
        browser.drag_payload("missing.png")
    except KeyError as exc:
        assert "unknown editor asset" in str(exc)
    else:
        raise AssertionError("dragging a missing asset should fail")


def test_asset_browser_reports_missing_aliases_without_loading_assets(tmp_path):
    manager = AssetManager(tmp_path / "assets")
    manager.register("missing", "ghost.png")
    browser = EditorAssetBrowser(manager)

    frame = browser.frame()
    assert frame.total_files == 0
    assert frame.missing_aliases == ("missing",)
    assert not frame.healthy


def test_asset_browser_unknown_selection_is_rejected(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    browser = EditorAssetBrowser(AssetManager(root))

    try:
        browser.select("missing.png")
    except KeyError as exc:
        assert "unknown editor asset" in str(exc)
    else:
        raise AssertionError("missing asset should not be selectable")
