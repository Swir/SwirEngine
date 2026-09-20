from __future__ import annotations

try:
    from .generate_progress_svg import (
        BAR_WIDTH,
        PROGRESS_END,
        PROGRESS_START,
        STATUS_PATH,
        TEMPLATE_PATH,
        ProgressData,
        build_readme_progress_block,
        build_roadmap_progress_block,
        generate,
        main,
        parse_progress,
        render_progress_line,
        render_text_meter,
        verify_progress_presentation,
    )
except ImportError:  # pragma: no cover - direct script execution
    from generate_progress_svg import (
        BAR_WIDTH,
        PROGRESS_END,
        PROGRESS_START,
        STATUS_PATH,
        TEMPLATE_PATH,
        ProgressData,
        build_readme_progress_block,
        build_roadmap_progress_block,
        generate,
        main,
        parse_progress,
        render_progress_line,
        render_text_meter,
        verify_progress_presentation,
    )

__all__ = [
    "BAR_WIDTH",
    "PROGRESS_END",
    "PROGRESS_START",
    "STATUS_PATH",
    "TEMPLATE_PATH",
    "ProgressData",
    "build_readme_progress_block",
    "build_roadmap_progress_block",
    "generate",
    "main",
    "parse_progress",
    "render_progress_line",
    "render_text_meter",
    "verify_progress_presentation",
]


if __name__ == "__main__":
    raise SystemExit(main())
