## SwirEngine 1.1 animation runtime milestone

- added renderer-independent `Tween` property animation with delays, easing, repeat and yoyo playback
- added `TweenSequence` for deterministic sequential animation steps
- added parallel `AnimationTimeline` tracks with marker events and editor-friendly seek support
- added priority-driven `StateMachine` with wildcard transitions, enter/update/exit callbacks and `time_in_state`
- added `AnimationSystem` to advance timelines, sequences and gameplay state machines from one update loop
- added regression coverage for nested property paths, interpolation, completion callbacks, yoyo, timeline markers, seeking, state transitions and mixed runtime ownership
- added `docs/ANIMATION_RUNTIME.md` and runnable `examples/demo_animation_runtime.py`
- kept package version and PyPI/GitHub Release frozen until the complete 1.1 roadmap reaches verified 10/10
