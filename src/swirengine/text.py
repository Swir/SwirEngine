from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .graphics.primitives import Text2D
from .math.types import Color

UnicodeRange = tuple[int, int]
MeasureText = Callable[[str, "FontAsset", int], tuple[float, float]]


class TextAlign(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class FontAsset:
    """A font source plus optional explicit Unicode coverage metadata."""

    source: str | Path | None = None
    name: str = "default"
    ranges: tuple[UnicodeRange, ...] = ()

    @property
    def key(self) -> str:
        return str(self.source) if self.source is not None else ""

    def supports(self, character: str) -> bool:
        if not character or character.isspace() or not self.ranges:
            return True
        codepoint = ord(character)
        return any(start <= codepoint <= end for start, end in self.ranges)


@dataclass(frozen=True, slots=True)
class FontFamily:
    name: str
    faces: tuple[FontAsset, ...]

    def __post_init__(self) -> None:
        if not self.faces:
            raise ValueError("FontFamily requires at least one FontAsset")

    def resolve(self, character: str) -> FontAsset:
        for face in self.faces:
            if face.supports(character):
                return face
        return self.faces[-1]


class FontRegistry:
    """Small creator-facing registry for named font families and fallbacks."""

    def __init__(self) -> None:
        self._families: dict[str, FontFamily] = {
            "default": FontFamily("default", (FontAsset(name="default"),))
        }

    def register(self, family: FontFamily) -> FontFamily:
        self._families[family.name] = family
        return family

    def family(self, name: str = "default") -> FontFamily:
        try:
            return self._families[name]
        except KeyError as exc:
            raise KeyError(f"Unknown font family: {name}") from exc

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._families)


@dataclass(frozen=True, slots=True)
class TextStyle:
    family: str = "default"
    font_size: int = 24
    max_width: float | None = None
    align: TextAlign = TextAlign.LEFT
    line_spacing: float = 1.0

    def normalized(self) -> TextStyle:
        width = None if self.max_width is None else max(1.0, float(self.max_width))
        return TextStyle(
            family=str(self.family),
            font_size=max(1, int(self.font_size)),
            max_width=width,
            align=TextAlign(self.align),
            line_spacing=max(0.1, float(self.line_spacing)),
        )


@dataclass(frozen=True, slots=True)
class TextRun:
    text: str
    font: FontAsset
    x: float
    width: float


@dataclass(frozen=True, slots=True)
class TextLine:
    text: str
    width: float
    x: float
    y: float
    runs: tuple[TextRun, ...]


@dataclass(frozen=True, slots=True)
class TextLayout:
    text: str
    style: TextStyle
    width: float
    height: float
    line_height: float
    lines: tuple[TextLine, ...]


@dataclass(slots=True)
class TextLayoutDiagnostics:
    requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    evictions: int = 0
    entries: int = 0
    measure_calls: int = 0
    fallback_switches: int = 0

    @property
    def hit_rate(self) -> float:
        return self.cache_hits / self.requests if self.requests else 0.0


class TextLayoutEngine:
    """Cached text wrapping/layout that materializes renderer-native Text2D runs."""

    def __init__(
        self,
        registry: FontRegistry | None = None,
        *,
        cache_limit: int = 256,
        measure: MeasureText | None = None,
    ) -> None:
        self.registry = registry or FontRegistry()
        self.cache_limit = max(8, int(cache_limit))
        self._measure_override = measure
        self._cache: OrderedDict[tuple[object, ...], TextLayout] = OrderedDict()
        self.diagnostics = TextLayoutDiagnostics()

    def clear_cache(self) -> None:
        self._cache.clear()
        self.diagnostics.entries = 0

    def _measure(self, text: str, face: FontAsset, size: int) -> tuple[float, float]:
        self.diagnostics.measure_calls += 1
        if self._measure_override is not None:
            width, height = self._measure_override(text, face, size)
            return max(0.0, float(width)), max(1.0, float(height))

        from PIL import ImageFont

        font_name = face.key or "DejaVuSans.ttf"
        try:
            font = ImageFont.truetype(font_name, size)
        except OSError:
            font = ImageFont.load_default()
        bbox = font.getbbox(text or " ")
        return max(0.0, float(bbox[2] - bbox[0])), max(1.0, float(bbox[3] - bbox[1]))

    @staticmethod
    def _runs_for(text: str, family: FontFamily) -> tuple[tuple[str, FontAsset], ...]:
        if not text:
            return (("", family.faces[0]),)
        groups: list[tuple[str, FontAsset]] = []
        current_font = family.resolve(text[0])
        current = [text[0]]
        for character in text[1:]:
            font = family.resolve(character)
            if font == current_font:
                current.append(character)
                continue
            groups.append(("".join(current), current_font))
            current_font = font
            current = [character]
        groups.append(("".join(current), current_font))
        return tuple(groups)

    def _measure_fallback_text(
        self,
        text: str,
        family: FontFamily,
        size: int,
    ) -> tuple[float, float, tuple[tuple[str, FontAsset, float], ...]]:
        measured: list[tuple[str, FontAsset, float]] = []
        width = 0.0
        height = 1.0
        groups = self._runs_for(text, family)
        if len(groups) > 1:
            self.diagnostics.fallback_switches += len(groups) - 1
        for value, face in groups:
            run_width, run_height = self._measure(value, face, size)
            measured.append((value, face, run_width))
            width += run_width
            height = max(height, run_height)
        return width, height, tuple(measured)

    def _wrap_paragraph(
        self,
        paragraph: str,
        family: FontFamily,
        size: int,
        max_width: float | None,
    ) -> list[str]:
        if max_width is None:
            return [paragraph]
        if not paragraph:
            return [""]

        lines: list[str] = []
        current = ""
        for word in paragraph.split(" "):
            candidate = word if not current else f"{current} {word}"
            candidate_width, _, _ = self._measure_fallback_text(candidate, family, size)
            if candidate_width <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ""

            word_width, _, _ = self._measure_fallback_text(word, family, size)
            if word_width <= max_width:
                current = word
                continue

            chunk = ""
            for character in word:
                candidate_chunk = chunk + character
                chunk_width, _, _ = self._measure_fallback_text(
                    candidate_chunk, family, size
                )
                if chunk and chunk_width > max_width:
                    lines.append(chunk)
                    chunk = character
                else:
                    chunk = candidate_chunk
            current = chunk
        lines.append(current)
        return lines

    def layout(self, text: str, style: TextStyle | None = None) -> TextLayout:
        normalized = (style or TextStyle()).normalized()
        key = (
            str(text),
            normalized.family,
            normalized.font_size,
            normalized.max_width,
            normalized.align.value,
            normalized.line_spacing,
        )
        self.diagnostics.requests += 1
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            self.diagnostics.cache_hits += 1
            return cached

        self.diagnostics.cache_misses += 1
        family = self.registry.family(normalized.family)
        raw_lines: list[str] = []
        for paragraph in str(text).split("\n"):
            raw_lines.extend(
                self._wrap_paragraph(
                    paragraph,
                    family,
                    normalized.font_size,
                    normalized.max_width,
                )
            )

        measured_lines: list[tuple[str, float, float, tuple[tuple[str, FontAsset, float], ...]]] = []
        line_height = 1.0
        for line in raw_lines or [""]:
            width, height, runs = self._measure_fallback_text(
                line, family, normalized.font_size
            )
            line_height = max(line_height, height)
            measured_lines.append((line, width, height, runs))

        block_width = (
            normalized.max_width
            if normalized.max_width is not None
            else max((line[1] for line in measured_lines), default=0.0)
        )
        step = line_height * normalized.line_spacing
        lines: list[TextLine] = []
        for index, (line_text, width, _, measured_runs) in enumerate(measured_lines):
            if normalized.align is TextAlign.CENTER:
                line_x = (block_width - width) * 0.5
            elif normalized.align is TextAlign.RIGHT:
                line_x = block_width - width
            else:
                line_x = 0.0
            run_x = 0.0
            runs: list[TextRun] = []
            for run_text, face, run_width in measured_runs:
                runs.append(TextRun(run_text, face, run_x, run_width))
                run_x += run_width
            lines.append(TextLine(line_text, width, line_x, index * step, tuple(runs)))

        height = line_height + max(0, len(lines) - 1) * step
        layout = TextLayout(str(text), normalized, block_width, height, line_height, tuple(lines))
        self._cache[key] = layout
        while len(self._cache) > self.cache_limit:
            self._cache.popitem(last=False)
            self.diagnostics.evictions += 1
        self.diagnostics.entries = len(self._cache)
        return layout

    def text_objects(
        self,
        layout: TextLayout,
        x: float = 0.0,
        y: float = 0.0,
        *,
        color: Color | None = None,
        scale: float = 1.0,
        layer: int = 0,
        screen_space: bool = False,
    ) -> tuple[Text2D, ...]:
        tint = color if color is not None else Color()
        objects: list[Text2D] = []
        for line in layout.lines:
            for run in line.runs:
                objects.append(
                    Text2D(
                        run.text,
                        x + line.x + run.x + run.width * 0.5,
                        y - line.y,
                        tint,
                        font_size=layout.style.font_size,
                        font=run.font.source,
                        scale=scale,
                        layer=layer,
                        screen_space=screen_space,
                    )
                )
        return tuple(objects)
