from swirengine.cli import new_project


def test_new_project_uses_current_engine_range(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = new_project("ExampleGame", "2d")
    config = (root / "swirproject.toml").read_text(encoding="utf-8")
    main = (root / "main.py").read_text(encoding="utf-8")
    assert 'engine = ">=1.0,<2.0"' in config
    assert "game.add(" in main
    assert 'game.key("A")' in main
    assert (root / "assets").is_dir()
    assert "dist/" in (root / ".gitignore").read_text(encoding="utf-8")
