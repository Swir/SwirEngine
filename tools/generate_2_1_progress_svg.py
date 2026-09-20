from __future__ import annotations

try:
    from .generate_progress_svg import (
        CARD_PATH,
        COMPAT_CARD_PATH,
        COMPAT_MINI_PATH,
        MINI_PATH,
        STATUS_PATH,
        TEMPLATE_PATH,
        ProgressData,
        expected_outputs,
        generate,
        main,
        parse_progress,
        render_card,
        render_mini,
        render_template,
    )
except ImportError:  # pragma: no cover - direct script execution
    from generate_progress_svg import (
        CARD_PATH,
        COMPAT_CARD_PATH,
        COMPAT_MINI_PATH,
        MINI_PATH,
        STATUS_PATH,
        TEMPLATE_PATH,
        ProgressData,
        expected_outputs,
        generate,
        main,
        parse_progress,
        render_card,
        render_mini,
        render_template,
    )

__all__ = [
    "CARD_PATH",
    "COMPAT_CARD_PATH",
    "COMPAT_MINI_PATH",
    "MINI_PATH",
    "STATUS_PATH",
    "TEMPLATE_PATH",
    "ProgressData",
    "expected_outputs",
    "generate",
    "main",
    "parse_progress",
    "render_card",
    "render_mini",
    "render_template",
]


if __name__ == "__main__":
    raise SystemExit(main())
