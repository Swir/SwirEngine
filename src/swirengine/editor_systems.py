from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class EditorSystemMetric(tuple):
    """Immutable ``(name, value, display_value)`` metric row."""

    __slots__ = ()

    def __new__(cls, name: str, value: object, display_value: str) -> EditorSystemMetric:
        return tuple.__new__(cls, (name, value, display_value))

    @property
    def name(self) -> str:
        return self[0]

    @property
    def value(self) -> object:
        return self[1]

    @property
    def display_value(self) -> str:
        return self[2]


class EditorSystemSnapshot(tuple):
    """Immutable creator-facing diagnostics snapshot for one engine subsystem."""

    __slots__ = ()

    def __new__(
        cls,
        system_id: str,
        title: str,
        category: str,
        metrics: tuple[EditorSystemMetric, ...],
    ) -> EditorSystemSnapshot:
        return tuple.__new__(cls, (system_id, title, category, metrics))

    @property
    def system_id(self) -> str:
        return self[0]

    @property
    def title(self) -> str:
        return self[1]

    @property
    def category(self) -> str:
        return self[2]

    @property
    def metrics(self) -> tuple[EditorSystemMetric, ...]:
        return self[3]


class EditorSystemFrame(tuple):
    """Immutable filtered editor snapshot across registered engine systems."""

    __slots__ = ()

    def __new__(
        cls,
        systems: tuple[EditorSystemSnapshot, ...],
        total_systems: int,
        categories: tuple[str, ...],
        query: str = "",
        category: str | None = None,
    ) -> EditorSystemFrame:
        return tuple.__new__(cls, (systems, total_systems, categories, query, category))

    @property
    def systems(self) -> tuple[EditorSystemSnapshot, ...]:
        return self[0]

    @property
    def total_systems(self) -> int:
        return self[1]

    @property
    def categories(self) -> tuple[str, ...]:
        return self[2]

    @property
    def query(self) -> str:
        return self[3]

    @property
    def category(self) -> str | None:
        return self[4]


DiagnosticsProvider = Callable[[], object]


class _RegisteredSystem(tuple):
    __slots__ = ()

    def __new__(
        cls,
        system_id: str,
        title: str,
        category: str,
        provider: DiagnosticsProvider,
    ) -> _RegisteredSystem:
        return tuple.__new__(cls, (system_id, title, category, provider))

    @property
    def system_id(self) -> str:
        return self[0]

    @property
    def title(self) -> str:
        return self[1]

    @property
    def category(self) -> str:
        return self[2]

    @property
    def provider(self) -> DiagnosticsProvider:
        return self[3]


class EditorSystemRegistry:
    """Lazy toolkit-neutral registry for creator/editor subsystem diagnostics.

    Registration stores metadata and a provider only. Providers are called *after* category/query
    filtering when ``frame()`` is requested, so editor diagnostics add no engine-frame polling and
    filtered panels do not touch unrelated subsystems.
    """

    def __init__(self) -> None:
        self._systems: dict[str, _RegisteredSystem] = {}

    def register(
        self,
        system_id: str,
        source: object | None = None,
        *,
        title: str | None = None,
        category: str = "runtime",
        provider: DiagnosticsProvider | None = None,
    ) -> None:
        normalized_id = system_id.strip()
        if not normalized_id:
            raise ValueError("system_id cannot be empty")
        normalized_category = category.strip().lower()
        if not normalized_category:
            raise ValueError("system category cannot be empty")
        normalized_title = (title or normalized_id.replace("-", " ").replace("_", " ").title()).strip()
        if not normalized_title:
            raise ValueError("system title cannot be empty")
        if provider is not None and source is not None:
            raise ValueError("pass either source or provider, not both")
        if provider is None:
            if source is None:
                raise ValueError("source or provider is required")
            provider = self._provider_for(source)
        if not callable(provider):
            raise TypeError("system diagnostics provider must be callable")
        self._systems[normalized_id] = _RegisteredSystem(
            normalized_id,
            normalized_title,
            normalized_category,
            provider,
        )

    def unregister(self, system_id: str) -> bool:
        return self._systems.pop(system_id.strip(), None) is not None

    def clear(self) -> None:
        self._systems.clear()

    @property
    def system_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._systems))

    def frame(
        self,
        *,
        query: str = "",
        category: str | None = None,
    ) -> EditorSystemFrame:
        normalized_query = query.strip().casefold()
        normalized_category = None if category is None else category.strip().lower()
        if normalized_category == "":
            normalized_category = None
        registrations = tuple(
            sorted(
                self._systems.values(),
                key=lambda item: (item.category, item.title.casefold(), item.system_id),
            )
        )
        categories = tuple(sorted({item.category for item in registrations}))
        selected = (
            item
            for item in registrations
            if (normalized_category is None or item.category == normalized_category)
            and (
                not normalized_query
                or normalized_query in item.system_id.casefold()
                or normalized_query in item.title.casefold()
                or normalized_query in item.category.casefold()
            )
        )
        snapshots = tuple(self._snapshot(item) for item in selected)
        return EditorSystemFrame(
            snapshots,
            len(registrations),
            categories,
            normalized_query,
            normalized_category,
        )

    @staticmethod
    def _provider_for(source: object) -> DiagnosticsProvider:
        def provider() -> object:
            diagnostics = getattr(source, "diagnostics", source)
            return diagnostics

        return provider

    def _snapshot(self, registered: _RegisteredSystem) -> EditorSystemSnapshot:
        diagnostics = registered.provider()
        metrics = tuple(
            EditorSystemMetric(name, value, self._display_value(value))
            for name, value in self._metric_items(diagnostics)
        )
        return EditorSystemSnapshot(
            registered.system_id,
            registered.title,
            registered.category,
            metrics,
        )

    @staticmethod
    def _metric_items(diagnostics: object) -> tuple[tuple[str, object], ...]:
        if is_dataclass(diagnostics) and not isinstance(diagnostics, type):
            return tuple((field.name, getattr(diagnostics, field.name)) for field in fields(diagnostics))
        if isinstance(diagnostics, Mapping):
            return tuple((str(key), diagnostics[key]) for key in sorted(diagnostics, key=str))
        if hasattr(diagnostics, "__dict__"):
            return tuple(
                (name, value)
                for name, value in sorted(vars(diagnostics).items())
                if not name.startswith("_") and not callable(value)
            )
        raise TypeError(
            "diagnostics must be a dataclass, mapping or object with public attributes; "
            "use an explicit provider for another representation"
        )

    @classmethod
    def _display_value(cls, value: object) -> str:
        if isinstance(value, Enum):
            return str(value.value)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, float):
            return f"{value:.6g}"
        if isinstance(value, (tuple, list)):
            return ", ".join(cls._display_value(item) for item in value)
        if isinstance(value, Mapping):
            return ", ".join(
                f"{key}={cls._display_value(value[key])}" for key in sorted(value, key=str)
            )
        return str(value)


class CreatorEditorFrame(tuple):
    """One combined snapshot of the existing editor frontend plus 1.3 system diagnostics."""

    __slots__ = ()

    def __new__(cls, frontend: object, systems: EditorSystemFrame) -> CreatorEditorFrame:
        return tuple.__new__(cls, (frontend, systems))

    @property
    def frontend(self) -> object:
        return self[0]

    @property
    def systems(self) -> EditorSystemFrame:
        return self[1]


class CreatorEditorIntegration:
    """Additive bridge between the existing editor shell and SwirEngine 1.3 diagnostics.

    The bridge deliberately wraps the existing frontend controller instead of replacing it. This
    keeps hierarchy, inspector, viewport, undo/redo, assets, console, profiler and playtest state on
    their established 1.x path while exposing 1.3 subsystem snapshots beside them.
    """

    def __init__(self, frontend: object, *, systems: EditorSystemRegistry | None = None) -> None:
        if not callable(getattr(frontend, "frame", None)):
            raise TypeError("frontend must provide a frame() method")
        self.frontend = frontend
        self.systems = systems or EditorSystemRegistry()
        self._query = ""
        self._category: str | None = None

    def set_system_filter(self, query: str = "", *, category: str | None = None) -> None:
        self._query = query
        self._category = category

    def frame(self) -> CreatorEditorFrame:
        return CreatorEditorFrame(
            self.frontend.frame(),
            self.systems.frame(query=self._query, category=self._category),
        )
