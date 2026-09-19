from __future__ import annotations

import argparse
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import escape
from pathlib import Path

STATUS_PATH = Path("ROADMAP_2_1.md")
CARD_PATH = Path("assets/readme/progress-2-1-card.svg")
MINI_PATH = Path("assets/readme/progress-2-1-mini.svg")

PROJECT_NAME = "SwirEngine"
MILESTONE_LABEL = "2.1 SWIREDITOR"
MEASURED_SCOPE = "SwirEngine 2.1 — SwirEditor & Creator Workflow"
RELEASE_STATUS = "Development branch · no SwirEngine 2.1 release published"

MILESTONE_RE = re.compile(r"^- \[(?P<state>[ xX])\] \*\*(?P<number>\d+)\.", re.MULTILINE)
SUMMARY_RE = re.compile(
    r"Current verified progress:\s*(?P<done>\d+)/(?P<total>\d+)\s+milestones\s*=\s*"
    r"(?P<percent>\d+(?:\.\d+)?)%\."
)


@dataclass(frozen=True, slots=True)
class ProgressData:
    completed: int
    total: int
    source: str = str(STATUS_PATH)

    @property
    def fraction(self) -> float | None:
        return None if self.total <= 0 else self.completed / self.total

    @property
    def percentage(self) -> float | None:
        return None if self.fraction is None else self.fraction * 100.0

    @property
    def display_percentage(self) -> str:
        return "N/A" if self.percentage is None else f"{self.percentage:.1f}%"

    @property
    def status(self) -> str:
        if self.total <= 0:
            return "N/A"
        return "COMPLETE" if self.completed >= self.total else "IN PROGRESS"

    @property
    def counter(self) -> str:
        return (
            "N/A milestones"
            if self.total <= 0
            else f"{self.completed} / {self.total} milestones"
        )


def parse_progress(text: str, *, source: str = str(STATUS_PATH)) -> ProgressData:
    matches = list(MILESTONE_RE.finditer(text))
    if not matches:
        return ProgressData(0, 0, source)
    numbers = [int(match.group("number")) for match in matches]
    if len(numbers) != len(set(numbers)):
        raise ValueError("2.1 milestone numbers must be unique")
    completed = sum(match.group("state").lower() == "x" for match in matches)
    data = ProgressData(completed, len(matches), source)
    summary = SUMMARY_RE.search(text)
    if summary is None:
        raise ValueError("2.1 roadmap is missing the verified progress summary")
    expected = data.percentage
    if expected is None:
        raise ValueError("2.1 roadmap cannot have an empty denominator")
    if int(summary.group("done")) != completed or int(summary.group("total")) != data.total:
        raise ValueError("2.1 roadmap summary disagrees with the milestone checklist")
    if not math.isclose(float(summary.group("percent")), expected, rel_tol=0.0, abs_tol=0.05):
        raise ValueError("2.1 roadmap percentage disagrees with the milestone checklist")
    return data


def render_card(data: ProgressData) -> str:
    width = 1100.0
    fill_width = 0.0 if data.fraction is None else width * data.fraction
    if not math.isfinite(fill_width) or not 0.0 <= fill_width <= width:
        raise ValueError("computed card fill width is outside the progress track")
    fill = ""
    if fill_width > 0:
        fill = (
            f'  <rect x="50" y="125" width="{fill_width:.6f}" height="18" rx="9" '
            'fill="url(#progressGradient)" filter="url(#softGlow)" '
            'clip-path="url(#trackClip)" />\n'
        )
    desc = (
        f"{MEASURED_SCOPE}. Status {data.status}. Verified {data.counter}. "
        f"Source: {data.source}. {RELEASE_STATUS}."
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="180" viewBox="0 0 1200 180" role="img" aria-labelledby="title desc">
  <title id="title">{escape(PROJECT_NAME)} 2.1 progress — {escape(data.display_percentage)}</title>
  <desc id="desc">{escape(desc)}</desc>
  <defs>
    <linearGradient id="panel" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#02050A"/><stop offset="1" stop-color="#07111C"/>
    </linearGradient>
    <linearGradient id="progressGradient" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#0088FF"/><stop offset="1" stop-color="#62E5FF"/>
    </linearGradient>
    <filter id="softGlow" x="-10%" y="-80%" width="120%" height="260%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M 28 0 L 0 0 0 28" fill="none" stroke="#62E5FF" stroke-opacity="0.035" stroke-width="1"/>
    </pattern>
    <clipPath id="trackClip"><rect x="50" y="125" width="1100" height="18" rx="9"/></clipPath>
    <style>
      text {{ font-family: "Segoe UI", Arial, sans-serif; }}
      .label {{ fill:#62E5FF;font-size:13px;font-weight:700;letter-spacing:2px; }}
      .project {{ fill:#F4FAFF;font-size:28px;font-weight:700; }}
      .scope {{ fill:#8DA8B8;font-size:17px; }}
      .meta {{ fill:#F4FAFF;font-size:14px;font-weight:600; }}
      .release {{ fill:#8DA8B8;font-size:12px; }}
    </style>
  </defs>
  <rect x="1" y="1" width="1198" height="178" rx="18" fill="url(#panel)" stroke="#0088FF" stroke-opacity="0.42"/>
  <rect x="1" y="1" width="1198" height="178" rx="18" fill="url(#grid)"/>
  <text x="50" y="28" class="label">SWIR PROJECT · VERIFIED DEVELOPMENT ROADMAP</text>
  <text x="50" y="54" class="project">{escape(PROJECT_NAME)}</text>
  <text x="50" y="68" class="scope">{escape(MEASURED_SCOPE)}</text>
  <text x="1150" y="38" text-anchor="end" class="project">{escape(data.display_percentage)}</text>
  <text x="1150" y="65" text-anchor="end" class="meta">{escape(data.status)} · {escape(data.counter)}</text>
  <rect x="50" y="125" width="1100" height="18" rx="9" fill="#07111C" stroke="#0088FF" stroke-opacity="0.45"/>
{fill}  <text x="50" y="165" class="release">{escape(RELEASE_STATUS)}</text>
  <text x="1150" y="165" text-anchor="end" class="release">Source: {escape(data.source)}</text>
</svg>\n'''


def render_mini(data: ProgressData) -> str:
    width = 700.0
    fill_width = 0.0 if data.fraction is None else width * data.fraction
    if not math.isfinite(fill_width) or not 0.0 <= fill_width <= width:
        raise ValueError("computed mini fill width is outside the progress track")
    fill = ""
    if fill_width > 0:
        fill = (
            f'  <rect x="170" y="43" width="{fill_width:.6f}" height="10" rx="5" '
            'fill="url(#progressGradient)" clip-path="url(#trackClip)" />\n'
        )
    desc = (
        f"{PROJECT_NAME}; {MEASURED_SCOPE}; {data.display_percentage}; "
        f"{data.status}; {data.counter}."
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="72" viewBox="0 0 900 72" role="img" aria-labelledby="title desc">
  <title id="title">{escape(PROJECT_NAME)} 2.1 {escape(data.display_percentage)} — {escape(data.status)}</title>
  <desc id="desc">{escape(desc)}</desc>
  <defs>
    <linearGradient id="progressGradient" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0088FF"/><stop offset="1" stop-color="#62E5FF"/></linearGradient>
    <clipPath id="trackClip"><rect x="170" y="43" width="700" height="10" rx="5"/></clipPath>
    <style>text {{ font-family: "Segoe UI", Arial, sans-serif; }}</style>
  </defs>
  <rect x="1" y="1" width="898" height="70" rx="14" fill="#02050A" stroke="#0088FF" stroke-opacity="0.42"/>
  <text x="24" y="29" fill="#F4FAFF" font-size="18" font-weight="700">{escape(PROJECT_NAME)} · {escape(MILESTONE_LABEL)}</text>
  <text x="870" y="29" text-anchor="end" fill="#62E5FF" font-size="18" font-weight="700">{escape(data.display_percentage)} · {escape(data.counter)}</text>
  <text x="24" y="55" fill="#8DA8B8" font-size="12">{escape(data.status)}</text>
  <rect x="170" y="43" width="700" height="10" rx="5" fill="#07111C" stroke="#0088FF" stroke-opacity="0.38"/>
{fill}</svg>\n'''


def _validate_svg(svg: str) -> None:
    root = ET.fromstring(svg)
    view_box = root.attrib.get("viewBox", "").split()
    if len(view_box) != 4:
        raise ValueError("SVG viewBox must contain four numeric values")
    values = [float(value) for value in view_box]
    if not all(math.isfinite(value) for value in values) or values[2] <= 0 or values[3] <= 0:
        raise ValueError("SVG viewBox must contain finite positive dimensions")


def expected_outputs(data: ProgressData) -> dict[Path, str]:
    outputs = {CARD_PATH: render_card(data), MINI_PATH: render_mini(data)}
    for value in outputs.values():
        _validate_svg(value)
    return outputs


def generate(*, check: bool = False) -> int:
    data = parse_progress(STATUS_PATH.read_text(encoding="utf-8"))
    stale: list[Path] = []
    for path, expected in expected_outputs(data).items():
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            path.write_text(expected, encoding="utf-8")
    if stale:
        print("stale SwirEngine 2.1 progress assets:")
        for path in stale:
            print(f"  {path}")
        return 1
    print(f"verified SwirEngine 2.1 progress: {data.display_percentage} ({data.counter})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate SwirEngine 2.1 roadmap SVG progress")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    return generate(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
