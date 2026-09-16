# Audio 2.0 — SwirEngine 1.5

SwirEngine 1.5 adds an opt-in Audio 2.0 layer in `swirengine.audio15`. It composes the released 1.x `AudioEngine` instead of replacing it, so existing imports, mixer behavior and projects remain unchanged.

## Goals

Audio 2.0 adds the runtime controls needed by larger games and automated validation:

- bounded sound-effect voice budgets;
- creator-defined voice priorities from `0` to `255`;
- deterministic oldest-first stealing inside the lowest eligible priority;
- protected voices that cannot be stolen;
- mixer snapshots with optional timed interpolation;
- a deterministic headless backend for CI, servers and replay validation;
- portable diagnostics and reproducible state fingerprints;
- continued reuse of the stable 1.x bus, fade and spatial attenuation behavior.

Music remains managed separately from the sound-effect voice budget because the stable engine already treats it as a dedicated stream.

## Headless runtime

The headless backend records playback state without opening an audio device:

```python
from swirengine.audio15 import AudioEngine2

audio = AudioEngine2.headless("assets", max_voices=32)
voice = audio.play("laser.wav", priority=120)
audio.update(1 / 60)
print(audio.diagnostics())
```

Assets still pass through `AssetManager.require()`, so the referenced files must exist. The backend deliberately does not decode their contents. This keeps filesystem and asset-path behavior realistic while allowing deterministic tests on machines with no audio hardware.

`HeadlessAudioBackend.events` exposes a monotonically numbered event stream for play, stop, volume and stereo changes. `AudioEngine2.state_fingerprint()` hashes portable diagnostics using canonical JSON. Asset paths are normalized relative to the asset root where possible, so equivalent runs under different temporary directories produce the same fingerprint.

## Voice budget and priorities

`AudioEngine2.play()` returns `AudioVoice2 | None`.

```python
critical = audio.play(
    "critical.wav",
    priority=220,
    protected=True,
)
```

Priority rules are deterministic:

1. priorities are integers from `0` to `255`;
2. when the SFX budget is not full, the new voice starts normally;
3. when full, protected voices are excluded from stealing;
4. only active voices with priority less than or equal to the incoming priority are eligible;
5. the lowest priority is selected first;
6. ties select the oldest voice, then the lowest internal voice id;
7. if no voice is eligible, the incoming request is rejected and `None` is returned.

Stopping or completing a fade-out immediately frees the corresponding budget entry after the next Audio 2.0 update/prune.

## Mixer snapshots

Snapshots are portable immutable target descriptions:

```python
from swirengine.audio15 import AudioSnapshot

pause = AudioSnapshot.from_mapping(
    "pause",
    {
        "sfx": {"volume": 0.25, "muted": True},
        "music": {"volume": 0.5},
    },
    master_volume=0.8,
)

audio.apply_snapshot(pause, duration=0.4)
```

Bus volume and master volume interpolate linearly using the `dt` values supplied to `AudioEngine2.update()`. This makes transition state deterministic under a deterministic game clock.

Mute transitions avoid cutting sound before a fade completes:

- a bus that must become unmuted is unmuted at transition start;
- a bus that must become muted is muted only when the transition reaches its target;
- instant snapshots apply mute state immediately.

The master bus is represented only by `master_volume`. Including `"master"` in the snapshot `buses` mapping is rejected so one snapshot cannot contain two conflicting master-volume sources.

`capture_snapshot()` records the current non-master bus state and, by default, the master volume. A caller can restrict the captured bus names or omit master volume.

## Spatial audio

Audio 2.0 delegates position, linear distance attenuation and stereo pan to the released `AudioEngine`, preserving stable 1.x behavior:

```python
voice = audio.play(
    "engine.wav",
    position=(5.0, 0.0, 0.0),
    min_distance=1.0,
    max_distance=25.0,
)
audio.set_listener_position((0.0, 0.0, 0.0))
```

The headless backend records the resulting stereo gains, which makes spatial behavior inspectable in CI without a real mixer.

## Diagnostics

`AudioEngine2.diagnostics()` reports:

- active and maximum SFX voices;
- cumulative stolen and rejected voice counts;
- current and transitioning snapshot state;
- snapshot transition progress;
- master and bus state;
- ordered per-voice priority, protection, bus, volume, pan and spatial data;
- headless backend event count.

The diagnostic payload is designed for debug UIs, test assertions, replay checks and regression captures rather than as a serialized save-game format.

## Compatibility

Audio 2.0 does not change `swirengine.__init__`, `swirengine.audio.AudioEngine`, `AudioHandle`, the existing Pygame backend or stable root imports. Projects opt in with `swirengine.audio15`.

Creating `AudioEngine2` normally still uses the optional Pygame backend from the stable engine. Use `AudioEngine2.headless()` when no real device should be initialized.

The published package remains version 1.4.0 until all ten SwirEngine 1.5 milestones and the final release gate are complete.

## Validation

The dedicated validation gate targets Python 3.10, 3.13 and 3.14 and covers:

- headless playback without desktop audio;
- deterministic voice budgeting, stealing, protection and rejection;
- music/SFX budget separation;
- instant and interpolated snapshots;
- deterministic mute timing;
- snapshot capture;
- spatial stereo diagnostics;
- portable state fingerprints;
- fade cleanup and transition cancellation;
- input validation and shutdown;
- a 5,000-operation priority/snapshot workload;
- the runnable Audio 2.0 demo.

Run locally:

```bash
pytest tests/test_audio_2_1_5.py
ruff check src/swirengine/audio15.py tests/test_audio_2_1_5.py tools/benchmark_audio_2_1_5.py examples/demo_audio_2_1_5.py
python -m compileall -q src/swirengine/audio15.py tests/test_audio_2_1_5.py tools/benchmark_audio_2_1_5.py examples/demo_audio_2_1_5.py
python tools/benchmark_audio_2_1_5.py
python examples/demo_audio_2_1_5.py
```
