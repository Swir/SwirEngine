# Expanded audio mixer

SwirEngine 1.1 extends `AudioEngine` from simple master/category gain into a creator-facing mixer that can be driven from normal gameplay code without coupling projects to a specific backend.

## Mixer buses

Every engine starts with `master`, `sfx` and `music` buses. Create additional groups for gameplay categories such as weapons, ambience, dialogue or UI:

```python
from swirengine import AudioEngine


audio = AudioEngine("assets")
audio.ensure_bus("weapons", volume=0.8)
audio.ensure_bus("ambience", volume=0.65)

shot = audio.play("audio/rifle.wav", bus="weapons")
wind = audio.play("audio/wind.ogg", bus="ambience", loop=True)

audio.set_bus_volume("weapons", 0.45)
audio.mute_bus("ambience", True)
```

`master_volume`, `sound_volume` and `music_volume` remain compatible with existing projects. Custom bus gain is composed with the appropriate category and master gain, so an options screen can keep using the old high-level controls while richer games add their own groups.

## Deterministic fades

Fades are advanced by `AudioEngine.update(dt)`, making them deterministic and independent from wall-clock timing:

```python
music = audio.music("audio/theme.ogg", volume=0.8, fade_in=1.5)

# In the gameplay update loop:
audio.update(dt)

# Later:
audio.stop_music(fade_out=1.0)
```

Handles also expose `fade_to`, `fade_in` and `fade_out`. A fade-out can stop the handle automatically at the target volume.

## Spatial controls

One-shot and looping sounds can carry a world position. SwirEngine computes linear distance attenuation between `min_distance` and `max_distance` and derives left/right pan from the listener-relative X position when the backend supports stereo channel gain.

```python
from swirengine import Vec3


audio.set_listener_position(Vec3(player.x, player.y, player.z))
engine_loop = audio.play(
    "audio/engine.wav",
    loop=True,
    bus="vehicles",
    position=Vec3(car.x, car.y, car.z),
    min_distance=2.0,
    max_distance=45.0,
)

# Move a source without recreating it:
engine_loop.set_position((car.x, car.y, car.z))
```

Backends that only implement scalar volume remain valid: distance attenuation still works and stereo pan gracefully falls back to scalar gain. `PygameAudioBackend` uses per-channel left/right volume for non-music sound channels.

## Runtime diagnostics

`audio.diagnostics()` returns a cheap immutable snapshot with active handle, music, spatial and fading counts plus bus/mute state. It is intended for debug overlays, editor tooling and tests:

```python
stats = audio.diagnostics()
print(stats.active_handles, stats.fading_handles, stats.muted_buses)
```

## Live reload compatibility

The existing asset live-reload path preserves bus selection, spatial settings, loop state and current local volume when a watched sound is restarted. Deleted assets still deactivate their handles, and failed restarts are recorded in `reload_events`.

## Backend contract

The required backend protocol remains source-compatible with 1.x custom backends: `play`, `stop`, `set_volume`, `stop_all` and `close`. Stereo panning is an optional capability discovered through `set_stereo(token, left, right)`, so older custom backends do not need immediate changes.
