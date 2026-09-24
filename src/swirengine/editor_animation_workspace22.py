from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .animation_state_machine22 import AnimationStateMachine22
from .editor_animation_resources22 import (
    AnimationPreviewResourceRefs22,
    clear_animation_preview_resource_refs22,
    load_animation_preview_resource_refs22,
    resolve_animation_preview_resource_refs22,
    save_animation_preview_resource_refs22,
)
from .editor_animation_state_machine22 import (
    ANIMATION_MACHINE_SUFFIX22,
    AnimationMachineDocument22,
    AnimationMachineEditorSession22,
    AnimationMachineProjectStore22,
    AnimationStateNode22,
)
from .editor_animation_state_machine_frontend22 import (
    AnimationMachineEditorFrame22,
    AnimationMachinePanelController22,
)
from .graphics.skeletal import SkeletalAnimationClip3D, Skeleton3D


@dataclass(frozen=True, slots=True)
class AnimationMachineWorkspaceSnapshot22:
    assets: tuple[str, ...]
    active_asset: str | None
    dirty: bool
    preview_bound: bool
    resource_refs_configured: bool


class AnimationMachineWorkspace22:
    """Project-level M5 workspace joining asset discovery, editing and runtime preview.

    The workspace is intentionally toolkit-neutral. SwirEditor can keep one instance for
    the whole project while individual graph windows are opened and closed. Asset names
    are always resolved through ``AnimationMachineProjectStore22`` so creator input never
    escapes ``assets/animation_machines``.
    """

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).resolve()
        self.store = AnimationMachineProjectStore22(self.project_root)
        self._session: AnimationMachineEditorSession22 | None = None
        self._controller: AnimationMachinePanelController22 | None = None
        self._skeleton: Skeleton3D | None = None
        self._clips: dict[str, SkeletalAnimationClip3D] = {}
        self._resource_refs: AnimationPreviewResourceRefs22 | None = None
        self._resource_refs_dirty = False

    @property
    def active_session(self) -> AnimationMachineEditorSession22:
        if self._session is None:
            raise RuntimeError("no animation machine asset is open")
        return self._session

    @property
    def controller(self) -> AnimationMachinePanelController22:
        if self._controller is None:
            raise RuntimeError("no animation machine asset is open")
        return self._controller

    @property
    def dirty(self) -> bool:
        return bool(
            (self._session is not None and self._session.dirty) or self._resource_refs_dirty
        )

    @property
    def preview_bound(self) -> bool:
        return self._skeleton is not None and bool(self._clips)

    @property
    def resource_refs(self) -> AnimationPreviewResourceRefs22 | None:
        return self._resource_refs

    def snapshot(self) -> AnimationMachineWorkspaceSnapshot22:
        return AnimationMachineWorkspaceSnapshot22(
            assets=self.discover(),
            active_asset=None if self._session is None else self._session.asset_name,
            dirty=self.dirty,
            preview_bound=self.preview_bound,
            resource_refs_configured=self._resource_refs is not None,
        )

    def discover(self) -> tuple[str, ...]:
        root = self.store.asset_root
        if not root.exists():
            return ()
        resolved_root = root.resolve()
        assets: list[str] = []
        for path in root.rglob(f"*{ANIMATION_MACHINE_SUFFIX22}"):
            if not path.is_file():
                continue
            try:
                resolved = path.resolve()
                relative = resolved.relative_to(resolved_root).as_posix()
                # Re-run the store's confinement/suffix validation for discovered files.
                self.store.path_for(relative)
            except (OSError, ValueError):
                continue
            assets.append(relative)
        return tuple(sorted(set(assets), key=lambda item: (item.casefold(), item)))

    def create(
        self,
        asset_name: str,
        document: AnimationMachineDocument22 | None = None,
    ) -> AnimationMachineEditorFrame22:
        if document is None:
            document = AnimationMachineDocument22(
                states=(AnimationStateNode22("Idle", clip="idle"),),
                initial="Idle",
            )
        # Validate before replacing the active editor session.
        self.store.path_for(asset_name)
        self._drop_runtime_binding()
        self._resource_refs = None
        self._resource_refs_dirty = False
        self._session = AnimationMachineEditorSession22.create(
            self.project_root,
            asset_name,
            document,
        )
        self._controller = AnimationMachinePanelController22(self._session)
        return self._controller.frame()

    def open(self, asset_name: str) -> AnimationMachineEditorFrame22:
        session = AnimationMachineEditorSession22.open(self.project_root, asset_name)
        refs = load_animation_preview_resource_refs22(session.store.path_for(session.asset_name))
        self._drop_runtime_binding()
        self._session = session
        self._controller = AnimationMachinePanelController22(self._session)
        self._resource_refs = refs
        self._resource_refs_dirty = False
        return self._controller.frame()

    def save(self) -> AnimationMachineEditorFrame22:
        frame = self.controller.save()
        graph_path = self.active_session.store.path_for(self.active_session.asset_name)
        if self._resource_refs is None:
            clear_animation_preview_resource_refs22(graph_path)
        else:
            save_animation_preview_resource_refs22(graph_path, self._resource_refs)
        self._resource_refs_dirty = False
        return frame

    def configure_preview_resource_refs(
        self,
        skeleton_ref: str,
        clip_refs: Mapping[str, str],
    ) -> AnimationPreviewResourceRefs22:
        # Require an active graph so a creator cannot accidentally configure orphaned refs.
        if self._session is None:
            raise RuntimeError("no animation machine asset is open")
        refs = AnimationPreviewResourceRefs22.from_mapping(skeleton_ref, clip_refs)
        if refs != self._resource_refs:
            self._drop_runtime_binding()
            self._resource_refs = refs
            self._resource_refs_dirty = True
        return refs

    def clear_preview_resource_refs(self) -> None:
        if self._session is None:
            raise RuntimeError("no animation machine asset is open")
        if self._resource_refs is not None:
            self._drop_runtime_binding()
            self._resource_refs = None
            self._resource_refs_dirty = True

    def resolve_preview_resources(self, resolver: Callable[[str], object]) -> None:
        if self._resource_refs is None:
            raise RuntimeError("preview resource references are not configured")
        skeleton, clips = resolve_animation_preview_resource_refs22(
            self._resource_refs,
            resolver,
        )
        self.bind_preview_resources(skeleton, clips)

    def bind_preview_resources(
        self,
        skeleton: Skeleton3D,
        clips: Mapping[str, SkeletalAnimationClip3D],
    ) -> None:
        if not isinstance(skeleton, Skeleton3D):
            raise TypeError("skeleton must be Skeleton3D")
        bound = dict(clips)
        if not bound:
            raise ValueError("at least one skeletal animation clip is required")
        if any(not isinstance(clip, SkeletalAnimationClip3D) for clip in bound.values()):
            raise TypeError("preview clips must be SkeletalAnimationClip3D")
        self._skeleton = skeleton
        self._clips = bound

    def clear_preview_resources(self) -> None:
        self._drop_runtime_binding()

    def validate_runtime(self) -> tuple[str, ...]:
        if self._skeleton is None or not self._clips:
            if self._resource_refs is not None:
                return ("preview resource references are configured but not resolved",)
            return ("preview resources are not bound",)
        return self.controller.validate_runtime(self._skeleton, self._clips)

    def start_preview(self) -> AnimationMachineEditorFrame22:
        if self._skeleton is None or not self._clips:
            raise RuntimeError("preview resources are not bound")
        return self.controller.start_preview(self._skeleton, self._clips)

    def compile_active(self) -> AnimationStateMachine22:
        if self._skeleton is None or not self._clips:
            raise RuntimeError("preview resources are not bound")
        return self.active_session.compile(self._skeleton, self._clips)

    def _drop_runtime_binding(self) -> None:
        if self._controller is not None:
            self._controller.stop_preview()
        self._skeleton = None
        self._clips = {}
