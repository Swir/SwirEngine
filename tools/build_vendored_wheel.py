from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import re
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

_VENDOR_ROOT = "swirengine/_vendor_native"
_PTH_NAME = "swirengine_native_vendor.pth"
_WHEEL_RE = re.compile(
    r"^(?P<name>[^-]+)-(?P<version>[^-]+)(?:-[^-]+)?-[^-]+-[^-]+-[^-]+\.whl$"
)
_TAG_RE = re.compile(r"^[A-Za-z0-9_.]+-[A-Za-z0-9_.]+-[A-Za-z0-9_.]+$")
_WINDOWS_DEVICE_RE = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?$",
    re.IGNORECASE,
)
_WINDOWS_FORBIDDEN_CHARS = frozenset('<>"|?*')


def _hash_record(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}"


def _vendor_name_from_dist_info(path: str) -> str:
    return path.split("/", 1)[0].split("-", 1)[0]


def _safe_member_name(name: str, *, wheel: Path) -> str:
    subject = f"{wheel.name}:{name!r}"
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        raise ValueError(f"unsafe wheel member path: {subject}")
    trimmed = name.removesuffix("/")
    if not trimmed or trimmed.endswith("/"):
        raise ValueError(f"unsafe wheel member path: {subject}")
    parts = tuple(trimmed.split("/"))
    if not all(parts) or any(part in {".", ".."} for part in parts):
        raise ValueError(f"unsafe wheel member path: {subject}")
    for part in parts:
        if part != unicodedata.normalize("NFC", part):
            raise ValueError(f"non-NFC wheel member path: {subject}")
        if part.endswith((".", " ")):
            raise ValueError(f"Windows-ambiguous wheel member path: {subject}")
        if ":" in part or any(
            ord(character) < 32 or character in _WINDOWS_FORBIDDEN_CHARS
            for character in part
        ):
            raise ValueError(f"Windows-forbidden wheel member path: {subject}")
        if _WINDOWS_DEVICE_RE.fullmatch(part):
            raise ValueError(f"Windows device wheel member path: {subject}")
    canonical = PurePosixPath(*parts).as_posix()
    if canonical != trimmed:
        raise ValueError(f"non-canonical wheel member path: {subject}")
    return canonical


def _read_wheel(path: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    collision_keys: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = _safe_member_name(info.orig_filename, wheel=path)
            collision_key = name.casefold()
            previous = collision_keys.get(collision_key)
            if previous is not None:
                raise ValueError(
                    f"duplicate/Windows-colliding wheel member: {previous!r} and {name!r}"
                )
            collision_keys[collision_key] = name

            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise ValueError(f"unsupported non-file wheel member: {path.name}:{name!r}")
            if info.flag_bits & 0x1:
                raise ValueError(f"encrypted wheel member is forbidden: {path.name}:{name!r}")
            if not info.is_dir():
                files[name] = archive.read(info)
    return files


def _dist_info_dir(files: dict[str, bytes]) -> str:
    candidates = {
        name.split("/", 1)[0]
        for name in files
        if name.count("/") >= 1 and name.split("/", 1)[0].endswith(".dist-info")
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
    output_keys: dict[str, str],
    dependency_wheel: Path,
    base_dist_info: str,
) -> str:
    if _WHEEL_RE.match(dependency_wheel.name) is None:
        raise ValueError(f"unsupported vendor wheel filename: {dependency_wheel.name}")
    dependency = _read_wheel(dependency_wheel)
    dependency_dist_info = _dist_info_dir(dependency)
    dependency_name = _vendor_name_from_dist_info(dependency_dist_info)

    for name, data in dependency.items():
        if name.startswith(f"{dependency_dist_info}/"):
            relative = name.removeprefix(f"{dependency_dist_info}/")
            if relative.startswith("licenses/") or relative in {"LICENSE", "LICENSE.txt"}:
                destination = (
                    f"{base_dist_info}/licenses/vendor/{dependency_name}/"
                    f"{PurePosixPath(relative).name}"
                )
                _add_output_file(output, output_keys, destination, data)
            continue
        _add_output_file(output, output_keys, f"{_VENDOR_ROOT}/{name}", data)
    return dependency_wheel.name


def _add_output_file(
    output: dict[str, bytes],
    output_keys: dict[str, str],
    name: str,
    data: bytes,
) -> None:
    key = name.casefold()
    previous = output_keys.get(key)
    if previous is not None:
        raise ValueError(f"duplicate/Windows-colliding output member: {previous!r} and {name!r}")
    output[name] = data
    output_keys[key] = name


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
    if _TAG_RE.fullmatch(tag) is None:
        raise ValueError(f"invalid platform wheel tag: {tag!r}")

    files = _read_wheel(base_path)
    output_keys = {name.casefold(): name for name in files}
    dist_info = _dist_info_dir(files)
    record_path = f"{dist_info}/RECORD"
    wheel_metadata_path = f"{dist_info}/WHEEL"
    files.pop(record_path, None)
    output_keys.pop(record_path.casefold(), None)
    files[wheel_metadata_path] = _replace_wheel_metadata(files[wheel_metadata_path], tag)

    vendored: list[str] = []
    for vendor_wheel in vendor_wheels:
        vendored.append(
            _vendor_dependency(files, output_keys, Path(vendor_wheel), dist_info)
        )

    _add_output_file(files, output_keys, _PTH_NAME, f"{_VENDOR_ROOT}\n".encode())
    _add_output_file(
        files,
        output_keys,
        f"{_VENDOR_ROOT}/VENDORED-WHEELS.txt",
        (
            "Bundled by SwirEngine for a platform where upstream binary wheels were unavailable.\n"
            + "\n".join(sorted(vendored))
            + "\n"
        ).encode(),
    )
    _add_output_file(files, output_keys, record_path, _record_bytes(files, record_path))

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
