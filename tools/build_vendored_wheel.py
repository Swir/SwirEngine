from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import re
import zipfile
from pathlib import Path

_VENDOR_ROOT = "swirengine/_vendor_native"
_PTH_NAME = "swirengine_native_vendor.pth"
_WHEEL_RE = re.compile(
    r"^(?P<name>[^-]+)-(?P<version>[^-]+)(?:-[^-]+)?-[^-]+-[^-]+-[^-]+\.whl$"
)


def _hash_record(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}"


def _vendor_name_from_dist_info(path: str) -> str:
    return path.split("/", 1)[0].split("-", 1)[0]


def _read_wheel(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}


def _dist_info_dir(files: dict[str, bytes]) -> str:
    candidates = {
        name.split("/", 1)[0]
        for name in files
        if ".dist-info/" in name and name.count("/") >= 1
    }
    if len(candidates) != 1:
        raise ValueError(f"expected one dist-info directory, got {sorted(candidates)!r}")
    return next(iter(candidates))


def _replace_wheel_metadata(original: bytes, tag: str) -> bytes:
    lines = original.decode("utf-8").splitlines()
    rewritten: list[str] = []
    saw_root = False
    for line in lines:
        if line.startswith("Root-Is-Purelib:"):
            rewritten.append("Root-Is-Purelib: false")
            saw_root = True
        elif line.startswith("Tag:"):
            continue
        else:
            rewritten.append(line)
    if not saw_root:
        rewritten.append("Root-Is-Purelib: false")
    rewritten.append(f"Tag: {tag}")
    return ("\n".join(rewritten).rstrip() + "\n").encode()


def _vendor_dependency(
    output: dict[str, bytes],
    dependency_wheel: Path,
    base_dist_info: str,
) -> str:
    dependency = _read_wheel(dependency_wheel)
    dependency_dist_info = _dist_info_dir(dependency)
    dependency_name = _vendor_name_from_dist_info(dependency_dist_info)

    for name, data in dependency.items():
        if name.startswith(f"{dependency_dist_info}/"):
            relative = name.removeprefix(f"{dependency_dist_info}/")
            if relative.startswith("licenses/") or relative in {"LICENSE", "LICENSE.txt"}:
                output[
                    f"{base_dist_info}/licenses/vendor/{dependency_name}/{Path(relative).name}"
                ] = data
            continue
        output[f"{_VENDOR_ROOT}/{name}"] = data
    return dependency_wheel.name


def _record_bytes(files: dict[str, bytes], record_path: str) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    for name in sorted(files):
        if name == record_path:
            continue
        data = files[name]
        writer.writerow((name, _hash_record(data), str(len(data))))
    writer.writerow((record_path, "", ""))
    return stream.getvalue().encode()


def build_vendored_wheel(
    base_wheel: str | Path,
    vendor_wheels: list[str | Path],
    *,
    tag: str,
    output_dir: str | Path,
) -> Path:
    base_path = Path(base_wheel)
    match = _WHEEL_RE.match(base_path.name)
    if match is None:
        raise ValueError(f"unsupported base wheel filename: {base_path.name}")
    if not vendor_wheels:
        raise ValueError("at least one vendor wheel is required")

    files = _read_wheel(base_path)
    dist_info = _dist_info_dir(files)
    record_path = f"{dist_info}/RECORD"
    wheel_metadata_path = f"{dist_info}/WHEEL"
    files.pop(record_path, None)
    files[wheel_metadata_path] = _replace_wheel_metadata(files[wheel_metadata_path], tag)

    vendored: list[str] = []
    for vendor_wheel in vendor_wheels:
        vendored.append(_vendor_dependency(files, Path(vendor_wheel), dist_info))

    files[_PTH_NAME] = f"{_VENDOR_ROOT}\n".encode()
    files[f"{_VENDOR_ROOT}/VENDORED-WHEELS.txt"] = (
        "Bundled by SwirEngine for a platform where upstream binary wheels were unavailable.\n"
        + "\n".join(sorted(vendored))
        + "\n"
    ).encode()
    files[record_path] = _record_bytes(files, record_path)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    filename = f"{match.group('name')}-{match.group('version')}-{tag}.whl"
    destination = output / filename
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vendor native dependency wheels into a SwirEngine platform wheel."
    )
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--vendor", required=True, action="append", type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output-dir", default=Path("dist"), type=Path)
    args = parser.parse_args()

    wheel = build_vendored_wheel(
        args.base,
        list(args.vendor),
        tag=args.tag,
        output_dir=args.output_dir,
    )
    print(wheel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
