from swirengine import EditorConsole, EditorProfiler, Profiler

profiler = Profiler(history=120)
editor_profiler = EditorProfiler(profiler, window=60, target_fps=60.0)
console = EditorConsole(history=500)

console.write("Visual editor diagnostics online", source="runtime")
console.write("Asset scan complete", source="assets")

for frame_seconds in (1 / 60, 1 / 58, 1 / 45):
    profiler.begin_frame()
    profiler.record("update", frame_seconds * 0.20)
    profiler.record("physics", frame_seconds * 0.10)
    profiler.record("render", frame_seconds * 0.55)
    profiler.end_frame(frame_seconds)

console_frame = console.frame()
profile_frame = editor_profiler.frame()

print("Console:")
for entry in console_frame.entries:
    print(f"[{entry.level.upper():8}] {entry.source}: {entry.message}")

print("\nProfiler:")
print(f"samples: {profile_frame.sample_count}")
print(f"latest FPS: {profile_frame.latest.fps:.1f}")
print(f"average frame: {profile_frame.average.frame_ms:.2f} ms")
print(f"peak frame: {profile_frame.peak_frame_ms:.2f} ms")
print(f"over budget: {profile_frame.over_budget_frames}/{profile_frame.sample_count}")
