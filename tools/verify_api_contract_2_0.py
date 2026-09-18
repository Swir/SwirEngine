from __future__ import annotations

import argparse
import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = ROOT / "src" / "swirengine" / "__init__.py"
PYPROJECT_PATH = ROOT / "pyproject.toml"
BASELINE_PATH = ROOT / "docs" / "api-contracts" / "swirengine-1.5-public-api.json"
MIGRATION_PATH = ROOT / "docs" / "api-contracts" / "swirengine-2.0-migration.json"

BASELINE_VERSION = "1.5.0"
TARGET_VERSION = "2.0.0"
EXPECTED_BASELINE_TAG = "v1.5.0"
BASELINE_SCHEMA_VERSION = 1
MIGRATION_SCHEMA_VERSION = 1


class ContractError(ValueError):
    """Raised when the public API or migration ledger violates the 2.0 contract."""


@dataclass(frozen=True, slots=True)
class ApiSurface:
    version: str
    exports: tuple[str, ...]
    bound_names: frozenset[str]


@dataclass(frozen=True, slots=True)
class BaselineContract:
    version: str
    source_tag: str
    exports: tuple[str, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class Removal:
    name: str
    replacement: str | None
    rationale: str


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    baseline_version: str
    target_version: str
    graduated_exports: tuple[str, ...]
    removals: tuple[Removal, ...]


def _require_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value.strip()


def _require_string_list(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ContractError(f"{field} must be a JSON array")
    items = tuple(_require_string(item, field=f"{field}[]") for item in value)
    if len(items) != len(set(items)):
        raise ContractError(f"{field} contains duplicate names")
    return items


def _canonical_exports_digest(exports: tuple[str, ...]) -> str:
    payload = ("\n".join(exports) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _assignment_value(module: ast.Module, name: str) -> Any:
    matches: list[ast.AST] = []
    for node in module.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets: list[ast.expr]
        value: ast.AST | None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        else:
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            matches.append(value)
    if len(matches) != 1:
        raise ContractError(f"expected exactly one static assignment for {name!r}, found {len(matches)}")
    try:
        return ast.literal_eval(matches[0])
    except (ValueError, TypeError) as exc:
        raise ContractError(f"{name!r} must use a literal value") from exc


def _top_level_bound_names(module: ast.Module) -> frozenset[str]:
    names: set[str] = set()
    for node in module.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return frozenset(names)


def parse_api_surface(path: Path = INIT_PATH) -> ApiSurface:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"cannot read package surface {path}: {exc}") from exc
    try:
        module = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        raise ContractError(f"cannot parse package surface {path}: {exc}") from exc

    raw_exports = _assignment_value(module, "__all__")
    if not isinstance(raw_exports, (list, tuple)):
        raise ContractError("swirengine.__all__ must be a literal list or tuple")
    exports = tuple(_require_string(item, field="swirengine.__all__") for item in raw_exports)
    if len(exports) != len(set(exports)):
        raise ContractError("swirengine.__all__ contains duplicate exports")

    version = _require_string(_assignment_value(module, "__version__"), field="swirengine.__version__")
    bound_names = _top_level_bound_names(module)
    unbound = sorted(set(exports) - bound_names)
    if unbound:
        raise ContractError("swirengine.__all__ contains unbound names: " + ", ".join(unbound))
    return ApiSurface(version=version, exports=exports, bound_names=bound_names)


def load_baseline(path: Path = BASELINE_PATH) -> BaselineContract:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load API baseline {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError("API baseline must be a JSON object")
    if payload.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise ContractError("unsupported API baseline schema version")
    if payload.get("package") != "swirengine":
        raise ContractError("API baseline package must be 'swirengine'")

    version = _require_string(payload.get("baseline_version"), field="baseline_version")
    source_tag = _require_string(payload.get("source_tag"), field="source_tag")
    exports = _require_string_list(payload.get("public_exports"), field="public_exports")
    count = payload.get("public_export_count")
    if not isinstance(count, int) or isinstance(count, bool) or count != len(exports):
        raise ContractError("public_export_count does not match public_exports")
    digest = _require_string(payload.get("public_exports_sha256"), field="public_exports_sha256")
    computed = _canonical_exports_digest(exports)
    if digest != computed:
        raise ContractError(f"public API baseline digest mismatch: declared={digest}, computed={computed}")
    if version != BASELINE_VERSION or source_tag != EXPECTED_BASELINE_TAG:
        raise ContractError("public API baseline must remain pinned to released SwirEngine 1.5.0 / v1.5.0")
    return BaselineContract(version=version, source_tag=source_tag, exports=exports, digest=digest)


def load_migration_plan(path: Path = MIGRATION_PATH) -> MigrationPlan:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load migration plan {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError("migration plan must be a JSON object")
    if payload.get("schema_version") != MIGRATION_SCHEMA_VERSION:
        raise ContractError("unsupported migration-plan schema version")

    baseline_version = _require_string(payload.get("baseline_version"), field="baseline_version")
    target_version = _require_string(payload.get("target_version"), field="target_version")
    graduated = _require_string_list(payload.get("graduated_exports"), field="graduated_exports")
    raw_removals = payload.get("removals")
    if not isinstance(raw_removals, list):
        raise ContractError("removals must be a JSON array")

    removals: list[Removal] = []
    for index, item in enumerate(raw_removals):
        if not isinstance(item, dict):
            raise ContractError(f"removals[{index}] must be an object")
        name = _require_string(item.get("name"), field=f"removals[{index}].name")
        raw_replacement = item.get("replacement")
        replacement = None
        if raw_replacement is not None:
            replacement = _require_string(raw_replacement, field=f"removals[{index}].replacement")
        rationale = _require_string(item.get("rationale"), field=f"removals[{index}].rationale")
        if len(rationale) < 12:
            raise ContractError(f"removals[{index}].rationale must explain the migration")
        removals.append(Removal(name=name, replacement=replacement, rationale=rationale))

    removal_names = [removal.name for removal in removals]
    if len(removal_names) != len(set(removal_names)):
        raise ContractError("removals contains duplicate names")
    if set(removal_names) & set(graduated):
        raise ContractError("the same name cannot be both removed and graduated")
    if baseline_version != BASELINE_VERSION or target_version != TARGET_VERSION:
        raise ContractError("migration plan must map SwirEngine 1.5.0 to 2.0.0")
    return MigrationPlan(
        baseline_version=baseline_version,
        target_version=target_version,
        graduated_exports=graduated,
        removals=tuple(removals),
    )


def read_project_version(path: Path = PYPROJECT_PATH) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc
    in_project = False
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_project = line == "[project]"
            continue
        if in_project and line.startswith("version"):
            key, separator, value = line.partition("=")
            if separator and key.strip() == "version":
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    return _require_string(value[1:-1], field="project.version")
                raise ContractError("[project].version must be a quoted literal")
    raise ContractError("pyproject.toml is missing [project].version")


def validate_contract(
    surface: ApiSurface,
    baseline: BaselineContract,
    migration: MigrationPlan,
    *,
    project_version: str,
    release_candidate: bool = False,
) -> dict[str, Any]:
    baseline_set = set(baseline.exports)
    current_set = set(surface.exports)
    graduated_set = set(migration.graduated_exports)
    removal_by_name = {removal.name: removal for removal in migration.removals}
    removal_set = set(removal_by_name)

    unknown_removals = sorted(removal_set - baseline_set)
    if unknown_removals:
        raise ContractError("migration removals are not in the 1.5 baseline: " + ", ".join(unknown_removals))

    missing = baseline_set - current_set
    if missing != removal_set:
        undocumented = sorted(missing - removal_set)
        stale = sorted(removal_set - missing)
        details: list[str] = []
        if undocumented:
            details.append("undocumented removals=" + ",".join(undocumented))
        if stale:
            details.append("ledger removals still exported=" + ",".join(stale))
        raise ContractError("1.5 compatibility surface disagrees with migration ledger: " + "; ".join(details))

    additions = current_set - baseline_set
    if additions != graduated_set:
        undocumented = sorted(additions - graduated_set)
        stale = sorted(graduated_set - additions)
        details = []
        if undocumented:
            details.append("undocumented root exports=" + ",".join(undocumented))
        if stale:
            details.append("graduated exports not present=" + ",".join(stale))
        raise ContractError("2.0 graduated export ledger disagrees with swirengine.__all__: " + "; ".join(details))

    available_after_migration = current_set
    for removal in migration.removals:
        if removal.replacement is not None and removal.replacement not in available_after_migration:
            raise ContractError(
                f"replacement {removal.replacement!r} for removed export {removal.name!r} is not public"
            )

    expected_source_version = TARGET_VERSION if release_candidate else BASELINE_VERSION
    if surface.version != expected_source_version or project_version != expected_source_version:
        raise ContractError(
            "source/package version contract mismatch: "
            f"swirengine.__version__={surface.version}, project.version={project_version}, "
            f"expected={expected_source_version}"
        )

    return {
        "baseline_version": baseline.version,
        "baseline_source_tag": baseline.source_tag,
        "baseline_export_count": len(baseline.exports),
        "baseline_exports_sha256": baseline.digest,
        "current_export_count": len(surface.exports),
        "graduated_export_count": len(graduated_set),
        "documented_removal_count": len(removal_set),
        "source_version": surface.version,
        "project_version": project_version,
        "mode": "release-candidate" if release_candidate else "source-development",
        "target_version": TARGET_VERSION,
    }


def audit(
    *,
    init_path: Path = INIT_PATH,
    pyproject_path: Path = PYPROJECT_PATH,
    baseline_path: Path = BASELINE_PATH,
    migration_path: Path = MIGRATION_PATH,
    release_candidate: bool = False,
) -> dict[str, Any]:
    return validate_contract(
        parse_api_surface(init_path),
        load_baseline(baseline_path),
        load_migration_plan(migration_path),
        project_version=read_project_version(pyproject_path),
        release_candidate=release_candidate,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the SwirEngine 2.0 public API and migration contract")
    parser.add_argument(
        "--release-candidate",
        action="store_true",
        help="require both package version surfaces to be 2.0.0 instead of the frozen 1.5.0 development version",
    )
    parser.add_argument("--json", action="store_true", help="emit the verified contract report as JSON")
    args = parser.parse_args(argv)
    try:
        report = audit(release_candidate=args.release_candidate)
    except ContractError as exc:
        print(f"SwirEngine 2.0 API contract FAILED: {exc}")
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            "SwirEngine 2.0 API contract verified: "
            f"baseline={report['baseline_version']} ({report['baseline_export_count']} exports), "
            f"current={report['current_export_count']}, "
            f"graduated={report['graduated_export_count']}, removals={report['documented_removal_count']}, "
            f"mode={report['mode']}"
        )
        print(f"baseline-sha256: {report['baseline_exports_sha256']}")
        print("Release/PyPI: frozen until SwirEngine 2.0" if not args.release_candidate else "2.0 release-candidate versioning enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
