from __future__ import annotations

import time

from swirengine.session16 import SessionLifecycle, SessionPhase


class DeterministicTokens:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"benchmark-resume-token-{self.value:08d}"


def main() -> None:
    started = time.perf_counter()
    session = SessionLifecycle(
        "benchmark-room",
        "client-000",
        max_members=128,
        max_resume_tokens=128,
        max_events=512,
        token_factory=DeterministicTokens(),
    )
    for index in range(1, 96):
        session.join(f"client-{index:03d}")

    for index in range(24):
        session.claim_role(f"client-{index + 1:03d}", f"role-{index:03d}")

    resume_cycles = 0
    for round_index in range(20):
        for member in session.members:
            session.set_ready(member.client_id)
        session.start_match(session.host_client_id)
        session.end_match(session.host_client_id)

        for offset in range(8):
            client_id = f"client-{1 + ((round_index * 8 + offset) % 95):03d}"
            token = session.resume_token_for(client_id)
            session.disconnect(client_id)
            result = session.resume(token)
            assert result.member.client_id == client_id
            assert result.resume_token != token
            resume_cycles += 1

    elapsed = time.perf_counter() - started
    diagnostics = session.diagnostics()

    assert session.phase is SessionPhase.LOBBY
    assert len(session.members) == 96
    assert diagnostics["members"] == 96
    assert diagnostics["connected_members"] == 96
    assert diagnostics["failures_total"] == 0
    assert diagnostics["active_resume_tokens"] <= 128
    assert resume_cycles == 160
    assert elapsed < 5.0, f"session lifecycle workload exceeded 5.0s budget: {elapsed:.3f}s"

    print(
        "session-lifecycle benchmark:",
        f"members={diagnostics['members']}",
        f"mutations={diagnostics['successful_mutations']}",
        f"resume_cycles={resume_cycles}",
        f"events_retained={diagnostics['retained_events']}",
        f"elapsed={elapsed:.4f}s",
    )


if __name__ == "__main__":
    main()
