from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - CPython 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = "release-evidence"
PUBLICATION_MARKER = (".release", "publish-2.2.0")
EXPECTED_SDIST_EXCLUDES = ["/release-evidence", "/.release"]


class DistributionAuditDataError(RuntimeError):
    """Raised when repository-only audit data can leak into distributions."""


def _normalized_parts(name: str) -> tuple[str, ...]:
    value = str(name).replace("\\", "/").strip("/")
    raw_parts = tuple(value.split("/"))
    if ".." in raw_parts:
        raise DistributionAuditDataError(
            f"archive member contains parent traversal: {name!r}"
        )
    if any(part and part.endswith((".", " ")) for part in raw_parts):
        raise DistributionAuditDataError(
            f"archive member contains a Windows-ambiguous path component: {name!r}"
        )
    return tuple(part.casefold() for part in raw_parts if part not in {"", "."})


def _reject_audit_member(names: list[str] | tuple[str, ...], *, label: str) -> None:
    for name in names:
        if AUDIT_DIR.casefold() in _normalized_parts(name):
            raise DistributionAuditDataError(
                f"{label} contains repository-only {AUDIT_DIR!r} audit data: {name!r}"
            )


def verify_pyproject_guard(root: Path = ROOT) -> None:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    try:
        targets = data["tool"]["hatch"]["build"]["targets"]
        wheel_packages = targets["wheel"]["packages"]
        sdist_exclude = targets["sdist"]["exclude"]
    except (KeyError, TypeError) as exc:
        raise DistributionAuditDataError(
            "pyproject Hatch distribution audit-data guard is missing or malformed"
        ) from exc
    if wheel_packages != ["src/swirengine"]:
        raise DistributionAuditDataError(
            "wheel target must remain package-only ['src/swirengine']"
        )
    if sdist_exclude != EXPECTED_SDIST_EXCLUDES:
        raise DistributionAuditDataError(
            f"sdist target must explicitly exclude {EXPECTED_SDIST_EXCLUDES!r}"
        )


def _reject_publication_marker(names: list[str] | tuple[str, ...], *, label: str) -> None:
    control_root = PUBLICATION_MARKER[0].casefold()
    for name in names:
        parts = _normalized_parts(name)
        if control_root in parts:
            raise DistributionAuditDataError(
                f"{label} contains publication-control marker: {name!r}"
            )


def inspect_distributions(dist_dir: Path, *, wheel_only: bool = False) -> None:
    root = dist_dir.resolve()
    wheels = sorted(root.glob("swirengine-*.whl"))
    sdists = sorted(root.glob("swirengine-*.tar.gz"))
    expected_sdists = 0 if wheel_only else 1
    if len(wheels) != 1 or len(sdists) != expected_sdists:
        expected = "one SwirEngine wheel only" if wheel_only else "one SwirEngine wheel and one sdist"
        raise DistributionAuditDataError(
            f"expected exactly {expected} for audit-data inspection; "
            f"found wheels={len(wheels)}, sdists={len(sdists)}"
        )
    with zipfile.ZipFile(wheels[0]) as archive:
        names = tuple(archive.namelist())
        _reject_audit_member(names, label="wheel")
        _reject_publication_marker(names, label="wheel")
    if not wheel_only:
        with tarfile.open(sdists[0], mode="r:gz") as archive:
            names = tuple(member.name for member in archive.getmembers())
            _reject_audit_member(names, label="sdist")
            _reject_publication_marker(names, label="sdist")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail closed if durable repository release evidence can enter SwirEngine wheel/sdist payloads."
        )
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument(
        "--wheel-only",
        action="store_true",
        help="require and inspect exactly one wheel and no sdist in --dist-dir",
    )
    args = parser.parse_args()

    verify_pyproject_guard(args.root.resolve())
    if args.wheel_only and args.dist_dir is None:
        parser.error("--wheel-only requires --dist-dir")
    if args.dist_dir is not None:
        inspect_distributions(args.dist_dir, wheel_only=args.wheel_only)
    print("SwirEngine 2.2 distribution audit-data isolation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
