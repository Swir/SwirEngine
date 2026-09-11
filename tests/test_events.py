from swirengine import EventBus


def test_event_bus_on_emit_off():
    bus = EventBus()
    values = []
    def handler(value):
        values.append(value)
    bus.on("x", handler)
    bus.emit("x", 7)
    bus.off("x", handler)
    bus.emit("x", 9)
    assert values == [7]
