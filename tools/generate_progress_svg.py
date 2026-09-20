from __future__ import annotations

import argparse
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

STATUS_PATH = Path("ROADMAP_2_1.md")
README_PATH = Path("README.md")
TEMPLATE_PATH = Path("assets/readme/progress-template.svg")

PROJECT_NAME = "SwirEngine"
MEASURED_SCOPE = "SwirEngine 2.1 — SwirEditor & Creator Workflow"
PROGRESS_START = "<!-- SWIR-PROGRESS:BEGIN -->"
PROGRESS_END = "<!-- SWIR-PROGRESS:END -->"
ROADMAP_POLICY_MARKER = "<!-- SWIR-PROGRESS-TEXT:v1 -->"
BAR_WIDTH = 10

MILESTONE_RE = re.compile(r"^- \[(?P<state>[ xX])\] \*\*(?P<number>\d+)\.", re.MULTILINE)
UNICODE_METER_RE = re.compile(r"[█▓▒░]{2,}")
GRAPHIC_PROGRESS_RE = re.compile(
    r"(?:progress-(?:card|mini|2-1-card|2-1-mini)\.svg|"
    r"!\[[^\]]*progress[^\]]*\]\([^)]*\)|"
    r"<img[^>]+(?:progress-card|progress-mini|progress-2-1)[^>]*>)",
    re.IGNORECASE,
)
OLD_PYPI_PROGRESS_MARKERS = (
    "<!-- SWIR-PYPI-PROGRESS:START -->",
    "<!-- SWIR-PYPI-PROGRESS:END -->",
)


@dataclass(frozen=True, slots=True)
class ProgressData:
    completed: int
    total: int
    source: str = str(STATUS_PATH)
    scope: str = MEASURED_SCOPE

    @property
    def fraction(self) -> float | None:
        return None if self.total <= 0 else self.completed / self.total

    @property
    def percentage(self) -> float | None:
        fraction = self.fraction
        return None if fraction is None else fraction * 100.0

    @property
    def display_percentage(self) -> str:
        percentage = self.percentage
        return "N/A" if percentage is None else f"{percentage:.1f}%"

    @property
    def status(self) -> str:
        if self.total <= 0:
            return "N/A"
        return "COMPLETE" if self.completed >= self.total else "IN PROGRESS"

    @property
    def counter(self) -> str:
        return "N/A milestones" if self.total <= 0 else f"{self.completed}/{self.total} milestones"


def parse_progress(text: str, *, source: str = str(STATUS_PATH)) -> ProgressData:
    matches = list(MILESTONE_RE.finditer(text))
    if not matches:
        return ProgressData(0, 0, source)

    numbers = [int(match.group("number")) for match in matches]
    if len(numbers) != len(set(numbers)):
        raise ValueError("2.1 milestone numbers must be unique")
    if numbers != sorted(numbers):
        raise ValueError("2.1 milestone numbers must remain ordered")

    completed = sum(match.group("state").lower() == "x" for match in matches)
    return ProgressData(completed, len(matches), source)


def render_text_meter(data: ProgressData, *, width: int = BAR_WIDTH) -> str:
    if width <= 0:
        raise ValueError("progress meter width must be positive")
    fraction = data.fraction
    if fraction is None:
        return "N/A"
    if not math.isfinite(fraction) or not 0.0 <= fraction <= 1.0:
        raise ValueError("progress fraction must be finite and between 0 and 1")
    filled = min(width, max(0, int(fraction * width + 0.5)))
    return f"[{'#' * filled}{'-' * (width - filled)}]"


def render_progress_line(data: ProgressData) -> str:
    if data.fraction is None:
        return "**Progress:** N/A (**N/A milestones**)"
    return (
        f"**Progress:** `{render_text_meter(data)}` **{data.display_percentage}** "
        f"(**{data.completed}/{data.total} milestones**)"
    )


def build_readme_progress_block(data: ProgressData) -> str:
    return "\n".join(
        (
            PROGRESS_START,
            f"Source: `{data.source}` · Verified scope: **{data.scope}** · Status: **{data.status}**",
            "",
            render_progress_line(data),
            "",
            "- **BETA READY: NO.**",
            PROGRESS_END,
        )
    )


def build_roadmap_progress_block(data: ProgressData) -> str:
    return "\n".join((PROGRESS_START, render_progress_line(data), PROGRESS_END))


def _progress_block(text: str, *, label: str) -> str:
    starts = text.count(PROGRESS_START)
    ends = text.count(PROGRESS_END)
    if starts != 1 or ends != 1:
        raise ValueError(f"{label} must contain exactly one SWIR progress block")
    start = text.index(PROGRESS_START)
    end = text.index(PROGRESS_END, start) + len(PROGRESS_END)
    return text[start:end]


def _replace_progress_block(text: str, replacement: str, *, label: str) -> str:
    current = _progress_block(text, label=label)
    return text.replace(current, replacement, 1)


def _validate_template() -> None:
    if not TEMPLATE_PATH.is_file():
        raise ValueError("progress-template.svg is required as an internal labelled template")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if "TEMPLATE / NOT PROJECT DATA" not in template:
        raise ValueError("progress-template.svg must remain explicitly labelled TEMPLATE / NOT PROJECT DATA")
    root = ET.fromstring(template)
    if not root.tag.endswith("svg"):
        raise ValueError("progress-template.svg must remain valid SVG")


def verify_progress_presentation(readme: str, roadmap: str, data: ProgressData) -> None:
    readme_block = _progress_block(readme, label="README.md")
    roadmap_block = _progress_block(roadmap, label="ROADMAP_2_1.md")

    if readme_block != build_readme_progress_block(data):
        raise ValueError("README active progress block is stale")
    if roadmap_block != build_roadmap_progress_block(data):
        raise ValueError("ROADMAP_2_1 active progress block is stale")
    if not roadmap.startswith(ROADMAP_POLICY_MARKER):
        raise ValueError("ROADMAP_2_1.md is missing the SwirEngine text-progress policy marker")

    for label, text in (("README.md", readme), ("ROADMAP_2_1.md", roadmap)):
        if GRAPHIC_PROGRESS_RE.search(text):
            raise ValueError(f"{label} must not embed graphical progress assets")
        if UNICODE_METER_RE.search(text):
            raise ValueError(f"{label} must not use Unicode block progress meters")

    if any(marker in readme for marker in OLD_PYPI_PROGRESS_MARKERS):
        raise ValueError("README contains the retired duplicate PyPI progress block")

    meter = render_text_meter(data)
    if meter != "N/A":
        if readme_block.count(meter) != 1 or roadmap_block.count(meter) != 1:
            raise ValueError("canonical text progress meter must appear exactly once per active progress block")

    _validate_template()


def generate(*, check: bool = False, status_path: Path = STATUS_PATH) -> int:
    if status_path != STATUS_PATH:
        raise ValueError("SwirEngine active progress generation only supports ROADMAP_2_1.md")
    if not STATUS_PATH.is_file() or not README_PATH.is_file():
        raise ValueError("README.md and ROADMAP_2_1.md are required")

    roadmap = STATUS_PATH.read_text(encoding="utf-8")
    data = parse_progress(roadmap, source=STATUS_PATH.as_posix())
    readme = README_PATH.read_text(encoding="utf-8")

    expected_readme = _replace_progress_block(
        readme,
        build_readme_progress_block(data),
        label="README.md",
    )
    expected_roadmap = _replace_progress_block(
        roadmap,
        build_roadmap_progress_block(data),
        label="ROADMAP_2_1.md",
    )

    if check:
        stale: list[Path] = []
        if readme != expected_readme:
            stale.append(README_PATH)
        if roadmap != expected_roadmap:
            stale.append(STATUS_PATH)
        try:
            verify_progress_presentation(readme, roadmap, data)
        except ValueError as exc:
            print(f"invalid SWIR active progress presentation: {exc}")
            return 1
        if stale:
            print("stale SWIR active progress presentation:")
            for path in stale:
                print(f"  {path}")
            return 1
    else:
        if readme != expected_readme:
            README_PATH.write_text(expected_readme, encoding="utf-8")
            readme = expected_readme
        if roadmap != expected_roadmap:
            STATUS_PATH.write_text(expected_roadmap, encoding="utf-8")
            roadmap = expected_roadmap
        verify_progress_presentation(readme, roadmap, data)

    action = "verified" if check else "generated"
    print(f"{action}: {data.scope} — {data.display_percentage} ({data.counter}), {data.status}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic text-only active SwirEngine progress presentation"
    )
    parser.add_argument("--check", action="store_true", help="fail when committed progress output is stale")
    parser.add_argument("--status", type=Path, default=STATUS_PATH, help="authoritative active roadmap")
    args = parser.parse_args(argv)
    return generate(check=args.check, status_path=args.status)


if __name__ == "__main__":
    raise SystemExit(main())
