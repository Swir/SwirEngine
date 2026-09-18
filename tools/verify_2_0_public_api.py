#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
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
    if data.get("baseline_release") != PUBLIC_VERSION_FLOOR:
        raise ValueError("public API contract baseline must remain the published 1.5.0 release")
    count = data.get("baseline_root_export_count")
    digest = data.get("baseline_root_exports_sha256")
    if not isinstance(count, int) or count <= 0:
        raise ValueError("baseline_root_export_count must be a positive integer")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("baseline_root_exports_sha256 must be a lowercase SHA-256 digest")
    return data


def read_static_all_text(text: str, *, source: str) -> list[str]:
    tree = ast.parse(text, filename=source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{source}: swirengine.__all__ must be a literal list of strings")
        if len(value) != len(set(value)):
            raise ValueError(f"{source}: swirengine.__all__ contains duplicate exports")
        return value
    raise ValueError(f"{source}: swirengine.__all__ assignment was not found")


def read_static_all(path: Path = INIT_PATH) -> list[str]:
    return read_static_all_text(path.read_text(encoding="utf-8"), source=str(path))


def _git(*args: str, root: Path = ROOT) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail or 'unknown git error'}")
    return completed.stdout


def baseline_ref_available(root: Path = ROOT, ref: str = "v1.5.0") -> bool:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def read_baseline_source(manifest: dict[str, object], *, root: Path = ROOT) -> bytes:
    ref = manifest.get("baseline_ref")
    path = manifest.get("baseline_path")
    if not isinstance(ref, str) or not ref or not isinstance(path, str) or not path:
        raise ValueError("manifest baseline_ref and baseline_path must be non-empty strings")
    return _git("show", f"{ref}:{path}", root=root)


def git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def export_digest(exports: list[str]) -> str:
    return hashlib.sha256("\n".join(exports).encode("utf-8")).hexdigest()


def read_project_version(path: Path = PYPROJECT_PATH) -> str:
    text = path.read_text(encoding="utf-8")
    project_match = re.search(r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", text)
    if project_match is None:
        raise ValueError("pyproject.toml is missing [project]")
    version_match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', project_match.group(1))
    if version_match is None:
        raise ValueError("[project] is missing a simple literal version")
    return version_match.group(1)


def read_module_version(path: Path = INIT_PATH) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, str):
            break
        return value
    raise ValueError("swirengine.__version__ literal assignment was not found")


def verify(root: Path = ROOT) -> list[str]:
    manifest_path = root / "docs" / "public_api_2_0.json"
    init_path = root / "src" / "swirengine" / "__init__.py"
    pyproject_path = root / "pyproject.toml"
    migration_path = root / "docs" / "MIGRATING_TO_2_0.md"
    api_stability_path = root / "docs" / "API_STABILITY.md"
    roadmap_path = root / "ROADMAP_2_0.md"

    manifest = load_manifest(manifest_path)
    ref = manifest.get("baseline_ref")
    if not isinstance(ref, str) or not baseline_ref_available(root, ref):
        raise ValueError(
            f"published baseline ref {ref!r} is unavailable; run this contract from a full checkout with tags"
        )

    baseline_bytes = read_baseline_source(manifest, root=root)
    expected_blob = manifest.get("baseline_init_blob_sha")
    actual_blob = git_blob_sha(baseline_bytes)
    if actual_blob != expected_blob:
        raise ValueError(f"published baseline blob mismatch: expected {expected_blob}, found {actual_blob}")

    baseline_text = baseline_bytes.decode("utf-8")
    baseline_exports = read_static_all_text(
        baseline_text,
        source=f"{manifest['baseline_ref']}:{manifest['baseline_path']}",
    )
    if len(baseline_exports) != manifest["baseline_root_export_count"]:
        raise ValueError("published baseline export count disagrees with manifest")
    if export_digest(baseline_exports) != manifest["baseline_root_exports_sha256"]:
        raise ValueError("published baseline export digest disagrees with manifest")

    current_exports = read_static_all(init_path)
    missing = [name for name in baseline_exports if name not in current_exports]
    if missing:
        raise ValueError(f"2.0 source removed published 1.5.0 root exports: {missing}")

    project_version = read_project_version(pyproject_path)
    module_version = read_module_version(init_path)
    if project_version != PUBLIC_VERSION_FLOOR or module_version != PUBLIC_VERSION_FLOOR:
        raise ValueError(
            "source-development versions must stay at 1.5.0 until the verified 2.0 final release gate; "
            f"project={project_version}, module={module_version}"
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

    additive = [name for name in current_exports if name not in baseline_exports]
    return [
        f"baseline={manifest['baseline_release']}",
        f"baseline-root-exports={len(baseline_exports)}",
        f"additive-root-exports={len(additive)}",
        f"project-version={project_version}",
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
