import pytest

from swirengine.render_graph18 import RenderGraphBuilder, RenderGraphError


def test_compile_orders_data_dependencies_and_priority_ties() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("camera", external=True)
    graph.add_resource("depth", transient=True, size_bytes=1024)
    graph.add_resource("hdr", transient=True, size_bytes=2048)
    graph.add_resource("backbuffer", external=True)
    graph.add_pass("depth", reads=("camera",), writes=("depth",), priority=10)
    graph.add_pass("lighting", reads=("depth",), writes=("hdr",))
    graph.add_pass("present", reads=("hdr",), writes=("backbuffer",), side_effect=True)

    plan = graph.compile()

    assert plan.passes == ("depth", "lighting", "present")
    assert plan.dependencies["lighting"] == ("depth",)
    assert plan.dependencies["present"] == ("lighting",)
    assert plan.diagnostics.active_passes == 3


def test_marked_output_culls_unrelated_work() -> None:
    graph = RenderGraphBuilder()
    for name in ("a", "b", "unused"):
        graph.add_resource(name, transient=True, size_bytes=32)
    graph.add_pass("make-a", writes=("a",))
    graph.add_pass("make-b", reads=("a",), writes=("b",))
    graph.add_pass("unused-pass", writes=("unused",))
    graph.mark_output("b")

    plan = graph.compile()

    assert plan.passes == ("make-a", "make-b")
    assert plan.culled_passes == ("unused-pass",)
    assert "unused" not in plan.lifetimes


def test_side_effect_keeps_its_upstream_dependencies() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("source", external=True)
    graph.add_resource("copy", transient=True, size_bytes=8)
    graph.add_pass("copy", reads=("source",), writes=("copy",))
    graph.add_pass("readback", reads=("copy",), side_effect=True)

    assert graph.compile().passes == ("copy", "readback")


def test_default_compile_keeps_all_passes_when_no_roots_are_declared() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("left", transient=True)
    graph.add_resource("right", transient=True)
    graph.add_pass("left-pass", writes=("left",), priority=-10)
    graph.add_pass("right-pass", writes=("right",), priority=10)

    assert graph.compile().passes == ("right-pass", "left-pass")


def test_transient_resources_alias_only_when_lifetimes_do_not_overlap() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("first", transient=True, size_bytes=100)
    graph.add_resource("bridge", transient=True, size_bytes=20)
    graph.add_resource("second", transient=True, size_bytes=80)
    graph.add_pass("first", writes=("first",))
    graph.add_pass("bridge", reads=("first",), writes=("bridge",))
    graph.add_pass("second", reads=("bridge",), writes=("second",))
    graph.add_pass("finish", reads=("second",), side_effect=True)

    plan = graph.compile()

    assert plan.lifetimes["first"].alias_slot == plan.lifetimes["second"].alias_slot
    assert plan.lifetimes["bridge"].alias_slot != plan.lifetimes["first"].alias_slot
    assert plan.diagnostics.transient_unaliased_bytes == 200
    assert plan.diagnostics.transient_reserved_bytes == 120
    assert plan.diagnostics.transient_alias_savings_bytes == 80
    assert plan.diagnostics.transient_peak_live_bytes == 120


def test_multiple_writers_are_rejected_without_partial_plan() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("target", transient=True)
    graph.add_pass("one", writes=("target",))
    graph.add_pass("two", writes=("target",))

    with pytest.raises(RenderGraphError, match="both one and two") as error:
        graph.compile()

    assert error.value.code == "multiple-writers"


def test_internal_read_requires_a_writer_but_external_read_does_not() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("internal")
    graph.add_pass("reader", reads=("internal",), side_effect=True)
    with pytest.raises(RenderGraphError) as error:
        graph.compile()
    assert error.value.code == "uninitialized-resource"

    external = RenderGraphBuilder()
    external.add_resource("swapchain", external=True)
    external.add_pass("reader", reads=("swapchain",), side_effect=True)
    assert external.compile().passes == ("reader",)


def test_missing_explicit_dependency_and_cycles_have_stable_codes() -> None:
    missing = RenderGraphBuilder()
    missing.add_pass("a", depends_on=("missing",))
    with pytest.raises(RenderGraphError) as error:
        missing.compile()
    assert error.value.code == "missing-pass-dependency"

    cycle = RenderGraphBuilder()
    cycle.add_pass("a", depends_on=("b",))
    cycle.add_pass("b", depends_on=("a",))
    with pytest.raises(RenderGraphError) as error:
        cycle.compile()
    assert error.value.code == "dependency-cycle"


def test_invalid_resource_and_in_place_access_are_rejected_at_authoring_time() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("image")
    with pytest.raises(RenderGraphError) as error:
        graph.add_pass("missing", reads=("nope",))
    assert error.value.code == "unknown-resource"

    with pytest.raises(RenderGraphError) as error:
        graph.add_pass("feedback", reads=("image",), writes=("image",))
    assert error.value.code == "in-place-resource"


def test_resource_and_pass_bounds_are_hard() -> None:
    graph = RenderGraphBuilder(max_resources=1, max_passes=1)
    graph.add_resource("one")
    with pytest.raises(RenderGraphError) as error:
        graph.add_resource("two")
    assert error.value.code == "resource-limit"
    graph.add_pass("one", writes=("one",))
    with pytest.raises(RenderGraphError) as error:
        graph.add_pass("two")
    assert error.value.code == "pass-limit"


def test_fingerprint_is_stable_and_changes_with_plan_contract() -> None:
    def build(size: int) -> str:
        graph = RenderGraphBuilder()
        graph.add_resource("input", external=True)
        graph.add_resource("output", transient=True, size_bytes=size)
        graph.add_pass("process", reads=("input",), writes=("output",))
        graph.mark_output("output")
        return graph.compile().fingerprint

    assert build(64) == build(64)
    assert build(64) != build(65)


def test_portable_snapshot_contains_no_callbacks_or_payload_objects() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("output", transient=True, size_bytes=4)
    graph.add_pass("draw", writes=("output",))
    graph.mark_output("output")

    portable = graph.compile().portable()

    assert portable["passes"] == ["draw"]
    assert portable["lifetimes"]["output"]["size_bytes"] == 4
    assert len(portable["fingerprint"]) == 64


def test_external_and_transient_flags_are_mutually_exclusive() -> None:
    graph = RenderGraphBuilder()
    with pytest.raises(ValueError, match="both transient and external"):
        graph.add_resource("bad", transient=True, external=True)


def test_strings_are_not_accepted_as_resource_sequences() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("image")
    with pytest.raises(TypeError, match="iterable of names"):
        graph.add_pass("bad", reads="image")


def test_uninitialized_marked_internal_output_is_rejected() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("image")
    graph.mark_output("image")
    with pytest.raises(RenderGraphError) as error:
        graph.compile()
    assert error.value.code == "uninitialized-output"


def test_priority_never_breaks_dependency_order() -> None:
    graph = RenderGraphBuilder()
    graph.add_pass("producer", priority=-100)
    graph.add_pass("consumer", depends_on=("producer",), priority=100)

    assert graph.compile().passes == ("producer", "consumer")


def test_unmark_output_reports_membership_and_validates_resource() -> None:
    graph = RenderGraphBuilder()
    graph.add_resource("image", transient=True)
    graph.mark_output("image")

    assert graph.unmark_output("image") is True
    assert graph.unmark_output("image") is False
    with pytest.raises(RenderGraphError) as error:
        graph.unmark_output("missing")
    assert error.value.code == "unknown-output"


def test_empty_graph_compiles_to_empty_deterministic_plan() -> None:
    first = RenderGraphBuilder().compile()
    second = RenderGraphBuilder().compile()

    assert first.passes == ()
    assert first.lifetimes == {}
    assert first.diagnostics.transient_peak_live_bytes == 0
    assert first.fingerprint == second.fingerprint
