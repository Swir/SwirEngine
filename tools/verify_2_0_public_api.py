from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "public_api_2_0.json"
INIT_PATH = ROOT / "src" / "swirengine" / "__init__.py"
PYPROJECT_PATH = ROOT / "pyproject.toml"
MIGRATION_PATH = ROOT / "docs" / "MIGRATING_TO_2_0.md"
API_STABILITY_PATH = ROOT / "docs" / "API_STABILITY.md"
ROADMAP_PATH = ROOT / "ROADMAP_2_0.md"
PUBLIC_VERSION_FLOOR = "1.5.0"


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported public API contract schema_version")
    exports = data.get("documented_root_exports")
    if not isinstance(exports, list) or not exports or not all(isinstance(item, str) for item in exports):
        raise ValueError("documented_root_exports must be a non-empty string list")
    if len(exports) != len(set(exports)):
        raise ValueError("documented_root_exports contains duplicates")
    if data.get("baseline_release") != PUBLIC_VERSION_FLOOR:
        raise ValueError("public API contract baseline must remain the published 1.5.0 release")
    return data


def read_static_all(path: Path = INIT_PATH) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("swirengine.__all__ must be a literal list of strings for contract verification")
        if len(value) != len(set(value)):
            raise ValueError("swirengine.__all__ contains duplicate exports")
        return value
    raise ValueError("swirengine.__all__ assignment was not found")


def read_project_version(path: Path = PYPROJECT_PATH) -> str:
    text = path.read_text(encoding="utf-8")
    project_match = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", text)
    if project_match is None:
        raise ValueError("pyproject.toml is missing [project]")
    version_match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', project_match.group(1))
    if version_match is None:
        raise ValueError("[project] is missing a simple literal version")
    return version_match.group(1)


def verify(root: Path = ROOT) -> list[str]:
    manifest_path = root / "docs" / "public_api_2_0.json"
    init_path = root / "src" / "swirengine" / "__init__.py"
    pyproject_path = root / "pyproject.toml"
    migration_path = root / "docs" / "MIGRATING_TO_2_0.md"
    api_stability_path = root / "docs" / "API_STABILITY.md"
    roadmap_path = root / "ROADMAP_2_0.md"

    manifest = load_manifest(manifest_path)
    expected = list(manifest["documented_root_exports"])
    actual = read_static_all(init_path)
    if actual != expected:
        missing = [name for name in expected if name not in actual]
        undocumented = [name for name in actual if name not in expected]
        raise ValueError(
            "swirengine.__all__ drifted from the 2.0 public API contract: "
            f"missing={missing}, undocumented={undocumented}, order_changed={set(actual) == set(expected)}"
        )

    version = read_project_version(pyproject_path)
    if version != PUBLIC_VERSION_FLOOR:
        raise ValueError(
            "source-development project version must stay at 1.5.0 until the verified 2.0 final release gate; "
            f"found {version}"
        )

    migration = migration_path.read_text(encoding="utf-8")
    api_stability = api_stability_path.read_text(encoding="utf-8")
    roadmap = roadmap_path.read_text(encoding="utf-8")
    required_references = {
        "migration guide": (migration, "public_api_2_0.json"),
        "API stability policy": (api_stability, "public_api_2_0.json"),
        "2.0 roadmap": (roadmap, "Public API & Migration Contract"),
    }
    for label, (text, needle) in required_references.items():
        if needle not in text:
            raise ValueError(f"{label} is missing required reference {needle!r}")

    stable = manifest.get("stable_behavior_exports")
    compatibility = manifest.get("compatibility_exports")
    if not isinstance(stable, list) or not isinstance(compatibility, list):
        raise ValueError("manifest stability groups must be lists")
    classified = [*stable, *compatibility]
    if sorted(classified) != sorted(expected):
        raise ValueError("stable_behavior_exports + compatibility_exports must classify every root export exactly once")
    if len(classified) != len(set(classified)):
        raise ValueError("public API stability groups overlap")

    return [
        f"baseline={manifest['baseline_release']}",
        f"root-exports={len(expected)}",
        f"project-version={version}",
        "migration-ledger=present",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the SwirEngine 2.0 public API and migration floor")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    args = parser.parse_args(argv)
    try:
        evidence = verify(args.root.resolve())
    except (OSError, ValueError, json.JSONDecodeError, SyntaxError) as exc:
        print(f"SwirEngine 2.0 public API contract FAILED: {exc}")
        return 1
    print("SwirEngine 2.0 public API contract verified: " + ", ".join(evidence))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
