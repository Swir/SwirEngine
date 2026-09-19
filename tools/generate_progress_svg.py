from __future__ import annotations

import argparse
import math
import re
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import escape
from pathlib import Path

STATUS_PATH = Path("docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md")
CARD_PATH = Path("assets/readme/progress-card.svg")
MINI_PATH = Path("assets/readme/progress-mini.svg")
TEMPLATE_PATH = Path("assets/readme/progress-template.svg")

PROJECT_NAME = "SwirEngine"
MILESTONE_LABEL = "2.0 POST-RELEASE"
MEASURED_SCOPE = "SwirEngine 2.0 — Post-Release Audit & Hardening"
RELEASE_STATUS = "Published 2.0.0 · post-release audit active"

MILESTONE_RE = re.compile(r"^- \[(?P<state>[ xX])\] \*\*(?P<number>\d+)\.", re.MULTILINE)
SUMMARY_RE = re.compile(
    r"Current verified progress:\s*(?P<done>\d+)/(?P<total>\d+)\s+milestones\s*=\s*"
    r"(?P<percent>\d+(?:\.\d+)?)%\."
)


@dataclass(frozen=True, slots=True)
class ProgressData:
    completed: int
    total: int
    source: str
    scope: str = MEASURED_SCOPE

    @property
    def fraction(self) -> float | None:
        return None if self.total <= 0 else self.completed / self.total

    @property
    def percentage(self) -> float | None:
        fraction = self.fraction
        return None if fraction is None else fraction * 100.0

    @property
    def status(self) -> str:
        if self.total <= 0:
            return "N/A"
        return "COMPLETE" if self.completed >= self.total else "IN PROGRESS"

    @property
    def counter(self) -> str:
        return "N/A audit domains" if self.total <= 0 else f"{self.completed} / {self.total} audit domains"

    @property
    def display_percentage(self) -> str:
        percentage = self.percentage
        return "N/A" if percentage is None else f"{percentage:.1f}%"


def parse_progress(text: str, *, source: str = str(STATUS_PATH)) -> ProgressData:
    milestones = list(MILESTONE_RE.finditer(text))
    if not milestones:
        return ProgressData(completed=0, total=0, source=source)

    numbers = [int(match.group("number")) for match in milestones]
    if len(numbers) != len(set(numbers)):
        raise ValueError("audit domain numbers must be unique")

    completed = sum(match.group("state").lower() == "x" for match in milestones)
    data = ProgressData(completed=completed, total=len(milestones), source=source)

    summary = SUMMARY_RE.search(text)
    if summary is None:
        raise ValueError("status document is missing the verified progress summary")
    summary_done = int(summary.group("done"))
    summary_total = int(summary.group("total"))
    summary_percent = float(summary.group("percent"))
    expected_percent = data.percentage
    if expected_percent is None:
        raise ValueError("verified status cannot have an empty denominator")
    if summary_done != completed or summary_total != data.total:
        raise ValueError(
            "status summary disagrees with audit checklist: "
            f"summary={summary_done}/{summary_total}, checklist={completed}/{data.total}"
        )
    if not math.isclose(summary_percent, expected_percent, rel_tol=0.0, abs_tol=0.05):
        raise ValueError(
            "status percentage disagrees with audit checklist: "
            f"summary={summary_percent:.1f}%, computed={expected_percent:.1f}%"
        )
    return data


def _scope_lines(scope: str) -> list[str]:
    lines = textwrap.wrap(scope, width=72, break_long_words=False, break_on_hyphens=False)
    if not lines:
        return ["N/A"]
    if len(lines) <= 2:
        return lines
    return [lines[0], " ".join(lines[1:])]


def render_card(data: ProgressData) -> str:
    lines = _scope_lines(data.scope)
    height = 180 if len(lines) == 1 else 210
    track_x = 50.0
    track_width = 1100.0
    fill_width = 0.0 if data.fraction is None else track_width * data.fraction
    if not math.isfinite(fill_width) or not 0.0 <= fill_width <= track_width:
        raise ValueError("computed card fill width is outside the progress track")
    progress_y = 125 if len(lines) == 1 else 154
    scope_markup = "\n".join(
        f'  <text x="50" y="{68 + index * 24}" class="scope">{escape(line)}</text>'
        for index, line in enumerate(lines)
    )
    fill = ""
    if fill_width > 0.0:
        fill = (
            f'  <rect x="{track_x:g}" y="{progress_y}" width="{fill_width:.6f}" height="18" '
            'rx="9" fill="url(#progressGradient)" filter="url(#softGlow)" '
            'clip-path="url(#trackClip)" />\n'
        )
    title = f"{PROJECT_NAME} progress — {data.display_percentage}"
    description = (
        f"{data.scope}. Status {data.status}. Verified {data.counter}. "
        f"Source: {data.source}. {RELEASE_STATUS}."
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">{escape(description)}</desc>
  <defs>
    <linearGradient id="panel" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#02050A"/>
      <stop offset="1" stop-color="#07111C"/>
    </linearGradient>
    <linearGradient id="progressGradient" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#0088FF"/>
      <stop offset="1" stop-color="#62E5FF"/>
    </linearGradient>
    <filter id="softGlow" x="-10%" y="-80%" width="120%" height="260%">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M 28 0 L 0 0 0 28" fill="none" stroke="#62E5FF" stroke-opacity="0.035" stroke-width="1"/>
    </pattern>
    <clipPath id="trackClip"><rect x="50" y="{progress_y}" width="1100" height="18" rx="9"/></clipPath>
    <style>
      text {{ font-family: "Segoe UI", Arial, sans-serif; }}
      .label {{ fill: #62E5FF; font-size: 13px; font-weight: 700; letter-spacing: 2px; }}
      .project {{ fill: #F4FAFF; font-size: 28px; font-weight: 700; }}
      .scope {{ fill: #8DA8B8; font-size: 17px; }}
      .meta {{ fill: #F4FAFF; font-size: 14px; font-weight: 600; }}
      .release {{ fill: #8DA8B8; font-size: 12px; }}
    </style>
  </defs>
  <rect x="1" y="1" width="1198" height="{height - 2}" rx="18" fill="url(#panel)" stroke="#0088FF" stroke-opacity="0.42"/>
  <rect x="1" y="1" width="1198" height="{height - 2}" rx="18" fill="url(#grid)"/>
  <text x="50" y="28" class="label">SWIR PROJECT · VERIFIED POST-RELEASE AUDIT</text>
  <text x="50" y="54" class="project">{escape(PROJECT_NAME)}</text>
{scope_markup}
  <text x="1150" y="38" text-anchor="end" class="project">{escape(data.display_percentage)}</text>
  <text x="1150" y="65" text-anchor="end" class="meta">{escape(data.status)} · {escape(data.counter)}</text>
  <rect x="50" y="{progress_y}" width="1100" height="18" rx="9" fill="#07111C" stroke="#0088FF" stroke-opacity="0.45"/>
{fill}  <text x="50" y="{progress_y + 40}" class="release">{escape(RELEASE_STATUS)}</text>
  <text x="1150" y="{progress_y + 40}" text-anchor="end" class="release">Source: {escape(data.source)}</text>
</svg>
'''


def render_mini(data: ProgressData) -> str:
    track_x = 170.0
    track_width = 700.0
    fill_width = 0.0 if data.fraction is None else track_width * data.fraction
    if not math.isfinite(fill_width) or not 0.0 <= fill_width <= track_width:
        raise ValueError("computed mini fill width is outside the progress track")
    fill = ""
    if fill_width > 0.0:
        fill = (
            f'  <rect x="{track_x:g}" y="43" width="{fill_width:.6f}" height="10" rx="5" '
            'fill="url(#progressGradient)" clip-path="url(#trackClip)" />\n'
        )
    description = (
        f"{PROJECT_NAME}; {data.scope}; {data.display_percentage}; {data.status}; {data.counter}."
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="72" viewBox="0 0 900 72" role="img" aria-labelledby="title desc">
  <title id="title">{escape(PROJECT_NAME)} {escape(data.display_percentage)} — {escape(data.status)}</title>
  <desc id="desc">{escape(description)}</desc>
  <defs>
    <linearGradient id="progressGradient" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#0088FF"/><stop offset="1" stop-color="#62E5FF"/>
    </linearGradient>
    <clipPath id="trackClip"><rect x="170" y="43" width="700" height="10" rx="5"/></clipPath>
    <style>text {{ font-family: "Segoe UI", Arial, sans-serif; }}</style>
  </defs>
  <rect x="1" y="1" width="898" height="70" rx="14" fill="#02050A" stroke="#0088FF" stroke-opacity="0.42"/>
  <text x="24" y="29" fill="#F4FAFF" font-size="18" font-weight="700">{escape(PROJECT_NAME)} · {escape(MILESTONE_LABEL)}</text>
  <text x="870" y="29" text-anchor="end" fill="#62E5FF" font-size="18" font-weight="700">{escape(data.display_percentage)} · {escape(data.counter)}</text>
  <text x="24" y="55" fill="#8DA8B8" font-size="12">{escape(data.status)}</text>
  <rect x="170" y="43" width="700" height="10" rx="5" fill="#07111C" stroke="#0088FF" stroke-opacity="0.38"/>
{fill}</svg>
'''


def render_template() -> str:
    return '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="180" viewBox="0 0 1200 180" role="img" aria-labelledby="title desc">
  <title id="title">SWIR Progress SVG PRO template</title>
  <desc id="desc">Reusable visual template only. TEMPLATE / NOT PROJECT DATA. Generate live progress from an authoritative source.</desc>
  <defs>
    <linearGradient id="panel" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#02050A"/>
      <stop offset="1" stop-color="#07111C"/>
    </linearGradient>
    <style>text { font-family: "Segoe UI", Arial, sans-serif; }</style>
  </defs>
  <rect x="1" y="1" width="1198" height="178" rx="18" fill="url(#panel)" stroke="#0088FF" stroke-opacity="0.42"/>
  <text x="50" y="31" fill="#62E5FF" font-size="13" font-weight="700" letter-spacing="2">SWIR PROJECT · PROGRESS TEMPLATE</text>
  <text x="50" y="67" fill="#F4FAFF" font-size="28" font-weight="700">TEMPLATE / NOT PROJECT DATA</text>
  <text x="50" y="96" fill="#8DA8B8" font-size="16">Project, scope, status, counter and percentage are inserted by the deterministic generator.</text>
  <rect x="50" y="125" width="1100" height="18" rx="9" fill="#07111C" stroke="#0088FF" stroke-opacity="0.42"/>
  <text x="50" y="166" fill="#8DA8B8" font-size="12">Never embed this template as live project progress.</text>
</svg>
'''


def _validate_svg(svg: str) -> None:
    root = ET.fromstring(svg)
    view_box = root.attrib.get("viewBox", "").split()
    if len(view_box) != 4:
        raise ValueError("SVG viewBox must contain four numeric values")
    numbers = [float(value) for value in view_box]
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError("SVG viewBox must contain finite values")
    if numbers[2] <= 0 or numbers[3] <= 0:
        raise ValueError("SVG viewBox dimensions must be positive")


def expected_outputs(data: ProgressData) -> dict[Path, str]:
    outputs = {CARD_PATH: render_card(data), MINI_PATH: render_mini(data), TEMPLATE_PATH: render_template()}
    for content in outputs.values():
        _validate_svg(content)
    return outputs


def generate(*, check: bool = False, status_path: Path = STATUS_PATH) -> int:
    text = status_path.read_text(encoding="utf-8")
    data = parse_progress(text, source=status_path.as_posix())
    outputs = expected_outputs(data)
    stale: list[Path] = []
    for path, expected in outputs.items():
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            path.write_text(expected, encoding="utf-8")

    if stale:
        print("stale SWIR progress assets:")
        for path in stale:
            print(f"  {path}")
        return 1

    action = "verified" if check else "generated"
    print(f"{action}: {PROJECT_NAME} {data.scope} — {data.display_percentage} ({data.counter}), {data.status}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic SWIR progress SVG assets")
    parser.add_argument("--check", action="store_true", help="fail when committed SVGs are stale")
    parser.add_argument("--status", type=Path, default=STATUS_PATH, help="authoritative status document")
    args = parser.parse_args(argv)
    return generate(check=args.check, status_path=args.status)


if __name__ == "__main__":
    raise SystemExit(main())
