from dataclasses import dataclass, field

from swirengine.animation_runtime import AnimationSystem, AnimationTimeline, Ease, State, StateMachine, Tween


@dataclass
class DemoActor:
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    alpha: float = 1.0
    speed: float = 0.0


actor = DemoActor()
events: list[str] = []

timeline = AnimationTimeline(on_marker=lambda marker: events.append(marker.name))
timeline.add(Tween(actor, "position", [6.0, 2.0, -4.0], duration=1.0, ease=Ease.IN_OUT_SINE))
timeline.add(Tween(actor, "alpha", 0.4, duration=1.0, ease=Ease.OUT_QUAD))
timeline.add_marker(0.5, "halfway")

machine = StateMachine(
    [
        State("idle"),
        State("run"),
    ],
    initial="idle",
)
machine.add_transition("idle", "run", lambda: actor.speed > 0.1)
machine.add_transition("run", "idle", lambda: actor.speed <= 0.1)

animations = AnimationSystem()
animations.add(timeline)
animations.add(machine)

for frame in range(60):
    if frame == 10:
        actor.speed = 2.0
    animations.update(1.0 / 60.0)

print("position:", [round(value, 3) for value in actor.position])
print("alpha:", round(actor.alpha, 3))
print("state:", machine.current)
print("markers:", events)
