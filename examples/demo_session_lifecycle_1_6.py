from __future__ import annotations

from swirengine.session16 import SessionLifecycle


class DemoTokens:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"demo-resume-token-{self.value:04d}"


def main() -> None:
    session = SessionLifecycle(
        "creator-demo",
        "host",
        token_factory=DemoTokens(),
    )
    pilot = session.join("pilot")
    session.join("support")
    session.claim_role("pilot", "driver")
    session.claim_role("support", "medic")

    for member in session.members:
        session.set_ready(member.client_id)

    match = session.start_match("host")
    print("match:", match.phase.value, [member.client_id for member in match.members])

    session.disconnect("pilot")
    resumed = session.resume(pilot.resume_token)
    print("resumed:", resumed.member.client_id, "token_rotated=", resumed.resume_token != pilot.resume_token)

    session.end_match("host")
    print("roles:", session.role_owners)
    print("events:", [(event.sequence, event.kind) for event in session.events()])
    print("diagnostics:", session.diagnostics())


if __name__ == "__main__":
    main()
