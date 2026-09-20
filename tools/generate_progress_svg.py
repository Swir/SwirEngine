from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

STATUS_PATH = Path("ROADMAP_2_1.md")
README_PATH = Path("README.md")
CARD_PATH = Path("assets/readme/progress-card.svg")
MINI_PATH = Path("assets/readme/progress-mini.svg")
TEMPLATE_PATH = Path("assets/readme/progress-template.svg")
COMPAT_CARD_PATH = Path("assets/readme/progress-2-1-card.svg")
COMPAT_MINI_PATH = Path("assets/readme/progress-2-1-mini.svg")

PROJECT_NAME = "SwirEngine"
MEASURED_SCOPE = "SwirEngine 2.1 — SwirEditor & Creator Workflow"
README_START = "<!-- SWIR-PYPI-PROGRESS:START -->"
README_END = "<!-- SWIR-PYPI-PROGRESS:END -->"
ROADMAP_START = "<!-- SWIR-ROADMAP-ASCII-PROGRESS:START -->"
ROADMAP_END = "<!-- SWIR-ROADMAP-ASCII-PROGRESS:END -->"
ASCII_WIDTH = 20

MILESTONE_RE = re.compile(r"^- \[(?P<state>[ xX])\] \*\*(?P<number>\d+)\.", re.MULTILINE)
SUMMARY_RE = re.compile(
    r"Current verified progress:\s*(?P<done>\d+)/(?P<total>\d+)\s+milestones\s*=\s*"
    r"(?P<percent>\d+(?:\.\d+)?)%\."
)
PROGRESS_SVG_LINE_RE = re.compile(
    r"^\s*<img[^>\n]*assets/readme/progress-(?:card|mini)\.svg[^>\n]*\/?>\s*$\n?",
    re.MULTILINE,
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
        return "N/A milestones" if self.total <= 0 else f"{self.completed} / {self.total} milestones"


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
    if abs(float(summary.group("percent")) - expected) > 0.05:
        raise ValueError("2.1 roadmap percentage disagrees with the milestone checklist")
    return data


def render_ascii(
    data: ProgressData,
    *,
    start: str = README_START,
    end: str = README_END,
) -> str:
    if data.fraction is None:
        body = "Progress: N/A\nN/A milestones"
    else:
        filled = max(0, min(ASCII_WIDTH, int(data.fraction * ASCII_WIDTH + 0.5)))
        bar = "#" * filled + "-" * (ASCII_WIDTH - filled)
        body = f"[{bar}] {data.display_percentage}\n{data.counter}"
    return f"{start}\n```text\n{body}\n```\n{end}"


def render_pypi_progress(data: ProgressData) -> str:
    return render_ascii(data)


# Legacy names are retained for imports/workflow compatibility. They return text,
# never graphical progress.
def render_card(data: ProgressData) -> str:
    return render_ascii(data)


def render_mini(data: ProgressData) -> str:
    return render_ascii(data, start=ROADMAP_START, end=ROADMAP_END)


def render_template() -> str:
    return "[--------------------] N/A\nN/A milestones"


def expected_outputs(data: ProgressData) -> dict[Path, str]:
    # Graphical progress assets are intentionally no longer canonical or generated.
    return {}


def _replace_block(text: str, *, start: str, end: str, block: str, anchor: str) -> str:
    starts = text.count(start)
    ends = text.count(end)
    if starts != ends or starts > 1:
        raise ValueError(f"Malformed ASCII progress markers: {start}")
    if starts == 1:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
        return pattern.sub(block, text, count=1)
    if anchor not in text:
        raise ValueError(f"Missing insertion anchor: {anchor.strip()}")
    return text.replace(anchor, anchor + "\n" + block + "\n", 1)


def expected_documents(readme: str, roadmap: str, data: ProgressData) -> tuple[str, str]:
    readme = PROGRESS_SVG_LINE_RE.sub("", readme)
    roadmap = PROGRESS_SVG_LINE_RE.sub("", roadmap)
    roadmap = roadmap.replace("<!-- SWIR-PROGRESS-SVG-PRO:v1 -->\n\n", "")
    readme = _replace_block(
        readme,
        start=README_START,
        end=README_END,
        block=render_ascii(data),
        anchor="## 📊 Project status\n",
    )
    roadmap = _replace_block(
        roadmap,
        start=ROADMAP_START,
        end=ROADMAP_END,
        block=render_ascii(data, start=ROADMAP_START, end=ROADMAP_END),
        anchor="# SwirEngine 2.1 — SwirEditor & Creator Workflow Roadmap\n",
    )
    return readme, roadmap


def generate(*, check: bool = False, status_path: Path = STATUS_PATH) -> int:
    roadmap = status_path.read_text(encoding="utf-8")
    data = parse_progress(roadmap, source=status_path.as_posix())
    readme = README_PATH.read_text(encoding="utf-8")
    expected_readme, expected_roadmap = expected_documents(readme, roadmap, data)

    stale: list[Path] = []
    if check:
        if readme != expected_readme:
            stale.append(README_PATH)
        if roadmap != expected_roadmap:
            stale.append(status_path)
        if stale:
            print("stale SwirEngine ASCII progress presentation:")
            for path in stale:
                print(f"  {path}")
            return 1
        print(f"verified: {data.scope} — {data.display_percentage} ({data.counter}), {data.status}")
        return 0

    if readme != expected_readme:
        README_PATH.write_text(expected_readme, encoding="utf-8")
    if roadmap != expected_roadmap:
        status_path.write_text(expected_roadmap, encoding="utf-8")
    print(f"generated: {data.scope} — {data.display_percentage} ({data.counter}), {data.status}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic ASCII-only active SwirEngine progress presentation"
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--status", type=Path, default=STATUS_PATH)
    args = parser.parse_args(argv)
    return generate(check=args.check, status_path=args.status)


if __name__ == "__main__":
    raise SystemExit(main())
