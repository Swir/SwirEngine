from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .core.scene import Scene
from .editor_preview import EditorViewportImage
from .editor_render_backend21 import EditorRenderBackend21
from .ui_designer22 import (
    EditorUIDesignerError22,
    EditorUIDesignerTooling22,
    UIAnimationSpec22,
    UIDesignAsset22,
    UIStyleSpec22,
    UIThemeSpec22,
    UIWidgetSpec22,
)

MAX_UI_DESIGNER_PREVIEW_DIMENSION = 1024
MAX_UI_DESIGNER_PREVIEW_STEP = 0.1
DEFAULT_UI_DESIGNER_PREVIEW_STEP = 1.0 / 60.0


def _fingerprint(snapshot: Any) -> str:
    value = getattr(snapshot, "fingerprint", None)
    if callable(value):
        value = value()
    if value is None:
        value = snapshot.asset.fingerprint()
    return str(value)


def _item_key(item: Any) -> str:
    for name in ("id", "name"):
        value = getattr(item, name, None)
        if isinstance(value, str) and value:
            return value
    raise TypeError("UI designer item must expose a non-empty id or name")


def _upsert(items: tuple[Any, ...], candidate: Any) -> tuple[Any, ...]:
    key = _item_key(candidate)
    result = [item for item in items if _item_key(item) != key]
    result.append(candidate)
    return tuple(result)


def _remove(items: tuple[Any, ...], key: str, label: str) -> tuple[Any, ...]:
    normalized = str(key).strip()
    result = tuple(item for item in items if _item_key(item) != normalized)
    if len(result) == len(items):
        raise EditorUIDesignerError22(f"unknown {label} {normalized!r}")
    return result


def _bounded_step(value: float) -> tuple[float, bool]:
    requested = float(value)
    if not math.isfinite(requested) or requested <= 0.0:
        raise EditorUIDesignerError22("preview step must be finite and greater than zero")
    step = min(requested, MAX_UI_DESIGNER_PREVIEW_STEP)
    return step, step != requested


@dataclass(frozen=True, slots=True)
class UIDesignerPanelFrame22:
    path: str
    asset: UIDesignAsset22
    dirty: bool
    fingerprint: str
    preview_active: bool
    preview_running: bool
    animation: str | None
    preview_time: float
    last_step: float
    step_was_clamped: bool
    diagnostics: object | None
    image: EditorViewportImage | None
    status: str


class UIDesignerPreview22:
    """Own an isolated UI runtime and lazily allocated 2D renderer backend."""

    def __init__(
        self,
        tooling: EditorUIDesignerTooling22,
        *,
        backend_factory: Callable[..., EditorRenderBackend21] = EditorRenderBackend21.create,
    ) -> None:
        snapshot = tooling.snapshot()

        def ignore_action(*_args: object, **_kwargs: object) -> None:
            return None

        actions = {
            widget.action
            for widget in snapshot.asset.widgets
            if isinstance(widget.action, str) and widget.action
        }
        handlers = {action: ignore_action for action in actions}
        self.source_fingerprint = _fingerprint(snapshot)
        self.runtime = tooling.build_runtime(scene=Scene(), handlers=handlers)
        self._backend_factory = backend_factory
        self._backend: EditorRenderBackend21 | None = None
        self._closed = False
        self.frames = 0

    @property
    def closed(self) -> bool:
        return self._closed

    def capture(self, width: int, height: int) -> EditorViewportImage:
        if self._closed:
            raise EditorUIDesignerError22("UI designer preview is closed")
        for value in (width, height):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise EditorUIDesignerError22(
                    "preview dimensions must be positive integers"
                )
        width = min(width, MAX_UI_DESIGNER_PREVIEW_DIMENSION)
        height = min(height, MAX_UI_DESIGNER_PREVIEW_DIMENSION)
        if self._backend is None:
            self._backend = self._backend_factory(width, height)
        self.runtime.layout(width, height)
        image = self._backend.viewport.capture(
            self.runtime.scene,
            width,
            height,
            mode="2d",
        )
        self.frames += 1
        return image

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        backend, self._backend = self._backend, None
        failure: Exception | None = None
        if backend is not None:
            try:
                backend.release()
            except Exception as exc:  # noqa: BLE001 - continue closing the UI runtime
                failure = exc
        try:
            self.runtime.stop(restore=True)
        except Exception as exc:  # noqa: BLE001 - both owned resources must be attempted
            if failure is None:
                failure = exc
        try:
            self.runtime.close()
        except Exception as exc:  # noqa: BLE001 - both owned resources must be attempted
            if failure is None:
                failure = exc
        if failure is not None:
            raise failure


class EditorUIDesignerPanelController22:
    """Toolkit-neutral UI Designer authoring and bounded preview controller."""

    def __init__(
        self,
        tooling: EditorUIDesignerTooling22,
        *,
        preview_factory: Callable[..., UIDesignerPreview22] = UIDesignerPreview22,
    ) -> None:
        self.tooling = tooling
        self._preview_factory = preview_factory
        self._preview: UIDesignerPreview22 | None = None
        self._preview_fingerprint: str | None = None
        self._preview_running = False
        self._animation: str | None = None
        self._preview_time = 0.0
        self._last_step = 0.0
        self._step_was_clamped = False
        self.image: EditorViewportImage | None = None
        self.status = "UI Designer 2.0 ready"

    @property
    def active(self) -> bool:
        return self._preview is not None

    @property
    def running(self) -> bool:
        return self._preview_running

    @property
    def preview(self) -> UIDesignerPreview22 | None:
        return self._preview

    def frame(self) -> UIDesignerPanelFrame22:
        snapshot = self.tooling.snapshot()
        diagnostics = None
        if self._preview is not None:
            self._ensure_preview_current(snapshot)
            if self._preview is not None:
                try:
                    diagnostics = self._preview.runtime.diagnostics()
                except Exception as exc:
                    self._fail_closed("diagnostics", exc)
                    raise
                self._preview_time = float(getattr(diagnostics, "time", self._preview_time))
        path = getattr(snapshot, "path", getattr(self.tooling, "relative_path", ""))
        return UIDesignerPanelFrame22(
            str(path),
            snapshot.asset,
            bool(snapshot.dirty),
            _fingerprint(snapshot),
            self._preview is not None,
            self._preview_running,
            self._animation,
            self._preview_time,
            self._last_step,
            self._step_was_clamped,
            diagnostics,
            self.image,
            self.status,
        )

    def replace_asset(self, asset: UIDesignAsset22) -> UIDesignerPanelFrame22:
        setter = getattr(self.tooling, "replace_asset", None)
        if not callable(setter):
            setter = self.tooling.set_asset
        snapshot = setter(asset)
        if self._preview is not None:
            self._ensure_preview_current(snapshot)
        self.status = "Updated UI design asset"
        return self.frame()

    set_asset = replace_asset

    def set_theme(self, theme: UIThemeSpec22) -> UIDesignerPanelFrame22:
        asset = replace(self.tooling.snapshot().asset, theme=theme)
        frame = self.replace_asset(asset)
        self.status = "Updated UI theme"
        return replace(frame, status=self.status)

    def upsert_style(self, style: UIStyleSpec22) -> UIDesignerPanelFrame22:
        asset = self.tooling.snapshot().asset
        frame = self.replace_asset(replace(asset, styles=_upsert(tuple(asset.styles), style)))
        self.status = f"Updated UI style {style.name}"
        return replace(frame, status=self.status)

    add_style = upsert_style
    update_style = upsert_style

    def set_style_fields(self, name: str, **changes: Any) -> UIDesignerPanelFrame22:
        asset = self.tooling.snapshot().asset
        normalized = str(name).strip()
        current = next(
            (style for style in asset.styles if style.name == normalized),
            None,
        )
        if current is None:
            raise EditorUIDesignerError22(f"unknown UI style {normalized!r}")
        return self.upsert_style(replace(current, **changes))

    def remove_style(self, name: str) -> UIDesignerPanelFrame22:
        asset = self.tooling.snapshot().asset
        frame = self.replace_asset(
            replace(asset, styles=_remove(tuple(asset.styles), name, "UI style"))
        )
        self.status = f"Removed UI style {str(name).strip()}"
        return replace(frame, status=self.status)

    def upsert_widget(self, widget: UIWidgetSpec22) -> UIDesignerPanelFrame22:
        asset = self.tooling.snapshot().asset
        frame = self.replace_asset(replace(asset, widgets=_upsert(tuple(asset.widgets), widget)))
        self.status = f"Updated UI widget {widget.id}"
        return replace(frame, status=self.status)

    add_widget = upsert_widget
    update_widget = upsert_widget

    def set_widget_fields(self, widget_id: str, **changes: Any) -> UIDesignerPanelFrame22:
        asset = self.tooling.snapshot().asset
        normalized = str(widget_id).strip()
        current = next(
            (widget for widget in asset.widgets if widget.id == normalized),
            None,
        )
        if current is None:
            raise EditorUIDesignerError22(f"unknown UI widget {normalized!r}")
        return self.upsert_widget(replace(current, **changes))

    def remove_widget(self, widget_id: str) -> UIDesignerPanelFrame22:
        asset = self.tooling.snapshot().asset
        frame = self.replace_asset(
            replace(asset, widgets=_remove(tuple(asset.widgets), widget_id, "UI widget"))
        )
        self.status = f"Removed UI widget {str(widget_id).strip()}"
        return replace(frame, status=self.status)

    def upsert_animation(self, animation: UIAnimationSpec22) -> UIDesignerPanelFrame22:
        asset = self.tooling.snapshot().asset
        frame = self.replace_asset(
            replace(asset, animations=_upsert(tuple(asset.animations), animation))
        )
        self.status = f"Updated UI animation {animation.name}"
        return replace(frame, status=self.status)

    add_animation = upsert_animation
    update_animation = upsert_animation

    def remove_animation(self, name: str) -> UIDesignerPanelFrame22:
        asset = self.tooling.snapshot().asset
        frame = self.replace_asset(
            replace(asset, animations=_remove(tuple(asset.animations), name, "UI animation"))
        )
        self.status = f"Removed UI animation {str(name).strip()}"
        return replace(frame, status=self.status)

    def save(self) -> UIDesignerPanelFrame22:
        self.tooling.save()
        self.status = "Saved UI design asset"
        return self.frame()

    def reload(self) -> UIDesignerPanelFrame22:
        loader = getattr(self.tooling, "reload", None)
        if not callable(loader):
            loader = self.tooling.load
        snapshot = loader()
        if self._preview is not None:
            self._ensure_preview_current(snapshot)
        self.status = "Reloaded UI design asset"
        return self.frame()

    def start(self, animation: str | None = None) -> UIDesignerPanelFrame22:
        self.stop()
        candidate: UIDesignerPreview22 | None = None
        try:
            candidate = self._preview_factory(self.tooling)
            self._preview = candidate
            self._preview_fingerprint = _fingerprint(self.tooling.snapshot())
            self._preview_running = True
            self._animation = None if animation is None else str(animation).strip()
            self._preview_time = 0.0
            self._last_step = 0.0
            self._step_was_clamped = False
            if self._animation:
                candidate.runtime.play(self._animation, restart=True)
            else:
                diagnostics = candidate.runtime.diagnostics()
                self._animation = getattr(diagnostics, "active_animation", None)
                self._preview_time = float(getattr(diagnostics, "time", 0.0))
        except Exception as exc:
            cleanup_error: Exception | None = None
            if candidate is not None:
                try:
                    candidate.close()
                except Exception as close_exc:  # noqa: BLE001 - report both failures
                    cleanup_error = close_exc
            self._clear_preview_state()
            suffix = "" if cleanup_error is None else f"; cleanup failed: {cleanup_error}"
            self.status = f"UI designer preview blocked: {exc}{suffix}"
            raise
        self.status = "UI designer preview started"
        return self.frame()

    start_preview = start

    def play(self, animation: str, *, restart: bool = True) -> UIDesignerPanelFrame22:
        preview = self._require_preview()
        try:
            name = str(animation).strip()
            preview.runtime.play(name, restart=restart)
            self._animation = name
            self._preview_running = True
            self._preview_time = float(getattr(preview.runtime.diagnostics(), "time", 0.0))
            self.image = None
        except Exception as exc:
            self._fail_closed("play", exc)
            raise
        self.status = f"Playing UI animation {self._animation}"
        return self.frame()

    def pause(self) -> UIDesignerPanelFrame22:
        preview = self._require_preview()
        try:
            if preview.runtime.diagnostics().active_animation is not None:
                preview.runtime.pause()
            self._preview_running = False
        except Exception as exc:
            self._fail_closed("pause", exc)
            raise
        self.status = "UI designer preview paused"
        return self.frame()

    pause_preview = pause

    def resume(self) -> UIDesignerPanelFrame22:
        preview = self._require_preview()
        try:
            if preview.runtime.diagnostics().active_animation is not None:
                preview.runtime.resume()
            self._preview_running = True
        except Exception as exc:
            self._fail_closed("resume", exc)
            raise
        self.status = "UI designer preview resumed"
        return self.frame()

    resume_preview = resume

    def step(self, dt: float = DEFAULT_UI_DESIGNER_PREVIEW_STEP) -> UIDesignerPanelFrame22:
        preview = self._require_preview()
        step, clamped = _bounded_step(dt)
        try:
            preview.runtime.step(step)
            self._preview_time = float(
                getattr(preview.runtime.diagnostics(), "time", self._preview_time + step)
            )
            self._last_step = step
            self._step_was_clamped = clamped
            self.image = None
        except Exception as exc:
            self._fail_closed("step", exc)
            raise
        suffix = " (clamped)" if clamped else ""
        self.status = f"UI designer preview stepped {step:.4f}s{suffix}"
        return self.frame()

    step_preview = step

    def seek(self, time: float) -> UIDesignerPanelFrame22:
        preview = self._require_preview()
        requested = float(time)
        if not math.isfinite(requested) or requested < 0.0:
            raise EditorUIDesignerError22("preview seek time must be finite and non-negative")
        try:
            preview.runtime.seek(requested)
            self._preview_time = float(
                getattr(preview.runtime.diagnostics(), "time", requested)
            )
            self.image = None
        except Exception as exc:
            self._fail_closed("seek", exc)
            raise
        self.status = f"UI designer preview moved to {self._preview_time:.3f}s"
        return self.frame()

    seek_preview = seek

    def capture(
        self,
        width: int = 640,
        height: int = 360,
        *,
        force: bool = False,
    ) -> EditorViewportImage | None:
        preview = self._require_preview()
        if not self._preview_running and self.image is not None and not force:
            return self.image
        try:
            self.image = preview.capture(width, height)
        except Exception as exc:
            self._fail_closed("render", exc)
            raise
        return self.image

    def update_preview(
        self,
        dt: float,
        width: int = 640,
        height: int = 360,
    ) -> EditorViewportImage | None:
        preview = self._require_preview()
        if not self._preview_running and self.image is not None:
            return self.image
        try:
            if self._preview_running:
                step, clamped = _bounded_step(dt)
                preview.runtime.step(step)
                self._preview_time = float(
                    getattr(preview.runtime.diagnostics(), "time", self._preview_time + step)
                )
                self._last_step = step
                self._step_was_clamped = clamped
            self.image = preview.capture(width, height)
        except Exception as exc:
            self._fail_closed("update", exc)
            raise
        return self.image

    def stop(self) -> UIDesignerPanelFrame22:
        preview = self._preview
        self._clear_preview_state()
        self.status = "UI designer preview stopped"
        if preview is not None:
            try:
                preview.close()
            except Exception as exc:
                self.status = f"UI designer preview cleanup failed: {exc}"
                raise
        return self.frame()

    stop_preview = stop

    def _require_preview(self) -> UIDesignerPreview22:
        snapshot = self.tooling.snapshot()
        self._ensure_preview_current(snapshot)
        if self._preview is None:
            raise EditorUIDesignerError22("UI designer preview is not active")
        return self._preview

    def _ensure_preview_current(self, snapshot: Any) -> None:
        if self._preview is None or _fingerprint(snapshot) == self._preview_fingerprint:
            return
        was_running = self._preview_running
        animation = self._animation
        preview_time = self._preview_time
        old = self._preview
        self._clear_preview_state()
        try:
            old.close()
            replacement = self._preview_factory(self.tooling)
            self._preview = replacement
            self._preview_fingerprint = _fingerprint(snapshot)
            self._preview_running = was_running
            self._animation = animation
            if animation:
                replacement.runtime.play(animation, restart=True)
                if preview_time > 0.0:
                    replacement.runtime.seek(preview_time)
                if not was_running:
                    replacement.runtime.pause()
            self._preview_time = preview_time
            self.image = None
        except Exception as exc:
            self._fail_closed("refresh", exc)
            raise
        self.status = "UI designer preview refreshed after asset change"

    def _clear_preview_state(self) -> None:
        self._preview = None
        self._preview_fingerprint = None
        self._preview_running = False
        self._animation = None
        self._preview_time = 0.0
        self._last_step = 0.0
        self._step_was_clamped = False
        self.image = None

    def _fail_closed(self, operation: str, exc: Exception) -> None:
        preview = self._preview
        self._clear_preview_state()
        cleanup_error: Exception | None = None
        if preview is not None:
            try:
                preview.close()
            except Exception as close_exc:  # noqa: BLE001 - preserve the triggering error
                cleanup_error = close_exc
        suffix = "" if cleanup_error is None else f"; cleanup failed: {cleanup_error}"
        self.status = f"UI designer preview {operation} failed: {exc}{suffix}"
