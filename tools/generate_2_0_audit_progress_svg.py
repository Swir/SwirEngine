from __future__ import annotations

import argparse
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import escape
from pathlib import Path

STATUS_PATH = Path("docs/SWIRENGINE_2_0_POST_RELEASE_AUDIT.md")
MINI_PATH = Path("assets/readme/progress-2-0-audit-mini.svg")
PROJECT_NAME = "SwirEngine"
MILESTONE_LABEL = "2.0 POST-RELEASE"
MEASURED_SCOPE = "SwirEngine 2.0 — Post-Release Audit & Hardening"

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
        return "N/A audit domains" if self.total <= 0 else f"{self.completed} / {self.total} audit domains"


def parse_progress(text: str, *, source: str = str(STATUS_PATH)) -> ProgressData:
    matches = list(MILESTONE_RE.finditer(text))
    if not matches:
        return ProgressData(0, 0, source)
    numbers = [int(match.group("number")) for match in matches]
    if len(numbers) != len(set(numbers)):
        raise ValueError("audit domain numbers must be unique")

    completed = sum(match.group("state").lower() == "x" for match in matches)
    data = ProgressData(completed, len(matches), source)
    summary = SUMMARY_RE.search(text)
    if summary is None:
        raise ValueError("audit document is missing the verified progress summary")
    expected = data.percentage
    if expected is None:
        raise ValueError("audit document cannot have an empty denominator")
    if int(summary.group("done")) != completed or int(summary.group("total")) != data.total:
        raise ValueError("audit summary disagrees with the domain checklist")
    if not math.isclose(float(summary.group("percent")), expected, rel_tol=0.0, abs_tol=0.05):
        raise ValueError("audit percentage disagrees with the domain checklist")
    return data


def render_mini(data: ProgressData) -> str:
    track_width = 700.0
    fill_width = 0.0 if data.fraction is None else track_width * data.fraction
    if not math.isfinite(fill_width) or not 0.0 <= fill_width <= track_width:
        raise ValueError("computed mini fill width is outside the progress track")
    fill = ""
    if fill_width > 0:
        fill = (
            f'  <rect x="170" y="43" width="{fill_width:.6f}" height="10" rx="5" '
            'fill="url(#progressGradient)" clip-path="url(#trackClip)" />\n'
        )
    desc = f"{PROJECT_NAME}; {MEASURED_SCOPE}; {data.display_percentage}; {data.status}; {data.counter}."
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="72" viewBox="0 0 900 72" role="img" aria-labelledby="title desc">
  <title id="title">{escape(PROJECT_NAME)} 2.0 audit {escape(data.display_percentage)} — {escape(data.status)}</title>
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
{fill}</svg>
'''


def _validate_svg(svg: str) -> None:
    root = ET.fromstring(svg)
    values = [float(value) for value in root.attrib.get("viewBox", "").split()]
    if len(values) != 4 or not all(math.isfinite(value) for value in values):
        raise ValueError("SVG viewBox must contain four finite values")
    if values[2] <= 0 or values[3] <= 0:
        raise ValueError("SVG viewBox dimensions must be positive")


def expected_outputs(data: ProgressData) -> dict[Path, str]:
    mini = render_mini(data)
    _validate_svg(mini)
    return {MINI_PATH: mini}


def generate(*, check: bool = False, status_path: Path = STATUS_PATH) -> int:
    data = parse_progress(status_path.read_text(encoding="utf-8"), source=status_path.as_posix())
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
        print("stale SwirEngine 2.0 audit progress assets:")
        for path in stale:
            print(f"  {path}")
        return 1
    action = "verified" if check else "generated"
    print(f"{action}: {MEASURED_SCOPE} — {data.display_percentage} ({data.counter}), {data.status}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic SwirEngine 2.0 audit SVG progress")
    parser.add_argument("--check", action="store_true", help="fail when the committed audit SVG is stale")
    parser.add_argument("--status", type=Path, default=STATUS_PATH, help="authoritative audit document")
    args = parser.parse_args(argv)
    return generate(check=args.check, status_path=args.status)


if __name__ == "__main__":
    raise SystemExit(main())
