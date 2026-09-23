from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_verifier():
    path = Path(__file__).resolve().parents[1] / "tools" / "verify_2_1_publication.py"
    spec = importlib.util.spec_from_file_location("verify_2_1_publication", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_publication_contract_passes_current_tree() -> None:
    module = _load_verifier()
    root = Path(__file__).resolve().parents[1]
    assert module.verify(root) == []


def test_publication_contract_rejects_svg_inside_pypi_block(tmp_path: Path) -> None:
    module = _load_verifier()
    root = Path(__file__).resolve().parents[1]
    for rel in (
        "pyproject.toml",
        "README.md",
        "RELEASE_NOTES_2_1.md",
        "ROADMAP_2_1.md",
        ".github/workflows/release.yml",
    ):
        source = root / rel
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    start = readme.index(module.PROGRESS_START)
    end = readme.index(module.PROGRESS_END) + len(module.PROGRESS_END)
    bad = (
        module.PROGRESS_START
        + '\n<img src="assets/readme/progress-card.svg" alt="bad" />\n'
        + module.PROGRESS_END
    )
    (tmp_path / "README.md").write_text(readme[:start] + bad + readme[end:], encoding="utf-8")

    errors = module.verify(tmp_path)
    assert any("ASCII" in error or "SVG/image" in error for error in errors)
