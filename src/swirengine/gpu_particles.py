from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .math.types import Color, Vec3


class GPUParticleEmissionShape3D(str, Enum):
    """Spawn regions implemented by the GPU particle simulation shader."""

    POINT = "point"
    BOX = "box"
    SPHERE = "sphere"


class GPUParticleBlendMode(str, Enum):
    """Blend modes supported by the batched GPU particle pass."""

    ALPHA = "alpha"
    ADDITIVE = "additive"


@dataclass(frozen=True, slots=True)
class GPUParticleFrame:
    """One render-frame simulation command consumed by the GPU backend."""

    dt: float
    spawn_cursor: int
    spawn_count: int
    spawn_serial: int


@dataclass(frozen=True, slots=True)
class GPUParticleDiagnostics:
    """CPU-side scheduling counters; particle simulation itself stays on the GPU."""

    capacity: int
    queued: int
    emitted_total: int
    submitted_total: int
    recycled_total: int
    simulation_frames: int
    spawn_cursor: int


@dataclass(slots=True)
class GPUParticleEmitter3D:
    """GPU-simulated 3D particle emitter for the SwirEngine 1.4 Renderer 2.0 path.

    ``update()`` only schedules elapsed time and emissions. Position, velocity, lifetime and
    particle recycling are simulated in ping-pong GPU buffers by Renderer2 using OpenGL 3.3
    transform feedback. This keeps the legacy :class:`ParticleEmitter2D` path unchanged.
    """

    position: Vec3 = field(default_factory=Vec3)
    capacity: int = 4096
    rate: float = 500.0
    lifetime: tuple[float, float] = (0.75, 1.75)
    velocity_min: Vec3 = field(default_factory=lambda: Vec3(-1.5, 1.0, -1.5))
    velocity_max: Vec3 = field(default_factory=lambda: Vec3(1.5, 5.0, 1.5))
    gravity: Vec3 = field(default_factory=lambda: Vec3(0.0, -3.5, 0.0))
    drag: float = 0.15
    size_pixels: tuple[float, float] = (5.0, 14.0)
    end_size_scale: float = 0.15
    start_color: Color = field(default_factory=lambda: Color(1.0, 0.55, 0.12, 1.0))
    end_color: Color = field(default_factory=lambda: Color(1.0, 0.05, 0.01, 0.0))
    emission_shape: GPUParticleEmissionShape3D | str = GPUParticleEmissionShape3D.POINT
    emission_extent: Vec3 = field(default_factory=Vec3)
    blend_mode: GPUParticleBlendMode | str = GPUParticleBlendMode.ADDITIVE
    seed: int = 1
    emitting: bool = True
    enabled: bool = True
    visible: bool = True

    _emit_accumulator: float = field(default=0.0, init=False, repr=False)
    _simulation_dt: float = field(default=0.0, init=False, repr=False)
    _queued: int = field(default=0, init=False, repr=False)
    _spawn_cursor: int = field(default=0, init=False, repr=False)
    _spawn_serial: int = field(default=0, init=False, repr=False)
    _emitted_total: int = field(default=0, init=False, repr=False)
    _submitted_total: int = field(default=0, init=False, repr=False)
    _recycled_total: int = field(default=0, init=False, repr=False)
    _simulation_frames: int = field(default=0, init=False, repr=False)
    _gpu_reset_requested: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        if self.rate < 0.0:
            raise ValueError("rate must be non-negative")
        low_life, high_life = self.lifetime
        if low_life <= 0.0 or high_life <= 0.0:
            raise ValueError("particle lifetime must be greater than zero")
        if min(self.size_pixels) < 0.0:
            raise ValueError("size_pixels must be non-negative")
        if self.end_size_scale < 0.0:
            raise ValueError("end_size_scale must be non-negative")
        if self.drag < 0.0:
            raise ValueError("drag must be non-negative")
        if min(self.emission_extent.x, self.emission_extent.y, self.emission_extent.z) < 0.0:
            raise ValueError("emission_extent must be non-negative")
        self.capacity = int(self.capacity)
        self.rate = float(self.rate)
        self.lifetime = (float(low_life), float(high_life))
        self.size_pixels = (float(self.size_pixels[0]), float(self.size_pixels[1]))
        self.end_size_scale = float(self.end_size_scale)
        self.drag = float(self.drag)
        self.emission_shape = GPUParticleEmissionShape3D(self.emission_shape)
        self.blend_mode = GPUParticleBlendMode(self.blend_mode)
        self.start_color = self.start_color.clamped()
        self.end_color = self.end_color.clamped()
        self.seed = int(self.seed)

    @property
    def diagnostics(self) -> GPUParticleDiagnostics:
        return GPUParticleDiagnostics(
            capacity=self.capacity,
            queued=self._queued,
            emitted_total=self._emitted_total,
            submitted_total=self._submitted_total,
            recycled_total=self._recycled_total,
            simulation_frames=self._simulation_frames,
            spawn_cursor=self._spawn_cursor,
        )

    def emit(self, count: int = 1) -> int:
        """Queue a deterministic burst for the next GPU simulation frame."""
        requested = max(0, int(count))
        if requested == 0:
            return 0
        self._emitted_total += requested
        available = max(0, self.capacity - self._queued)
        accepted = min(requested, available)
        self._queued += accepted
        self._recycled_total += max(0, requested - accepted)
        return accepted

    burst = emit

    def clear(self) -> None:
        """Request a GPU-state reset and clear pending scheduling data."""
        self._queued = 0
        self._emit_accumulator = 0.0
        self._simulation_dt = 0.0
        self._spawn_cursor = 0
        self._spawn_serial += 1
        self._submitted_total = 0
        self._recycled_total = 0
        self._simulation_frames = 0
        self._gpu_reset_requested = True

    def update(self, dt: float) -> None:
        """Schedule emissions and elapsed time without visiting individual particles on the CPU."""
        if not self.enabled or dt <= 0.0:
            return
        step = min(float(dt), 0.25)
        self._simulation_dt = min(0.25, self._simulation_dt + step)
        if self.emitting and self.rate > 0.0:
            self._emit_accumulator += step * self.rate
            count = int(self._emit_accumulator)
            if count:
                self.emit(count)
                self._emit_accumulator -= count

    def _consume_gpu_frame(self) -> GPUParticleFrame:
        count = min(self._queued, self.capacity)
        frame = GPUParticleFrame(
            dt=self._simulation_dt,
            spawn_cursor=self._spawn_cursor,
            spawn_count=count,
            spawn_serial=self._spawn_serial,
        )
        if count:
            wrapped = max(0, self._spawn_cursor + count - self.capacity)
            self._recycled_total += wrapped
            self._spawn_cursor = (self._spawn_cursor + count) % self.capacity
            self._spawn_serial += count
            self._submitted_total += count
            self._queued -= count
        if self._simulation_dt > 0.0 or count:
            self._simulation_frames += 1
        self._simulation_dt = 0.0
        return frame
