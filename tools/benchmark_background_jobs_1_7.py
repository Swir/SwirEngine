from __future__ import annotations

import time

from swirengine import jobs17


JOB_COUNT = 2_000
BUDGET_SECONDS = 5.0


def main() -> None:
    started = time.perf_counter()
    with jobs17.JobScheduler(max_workers=4, max_pending=JOB_COUNT) as scheduler:
        for index in range(JOB_COUNT):
            scheduler.submit(f"job-{index}", lambda context, value=index: value * 2)
        outcomes = scheduler.wait_all(timeout=BUDGET_SECONDS)
        drained = scheduler.drain_completed()
        diagnostics = scheduler.diagnostics()
    elapsed = time.perf_counter() - started

    if len(outcomes) != JOB_COUNT or len(drained) != JOB_COUNT:
        raise SystemExit("background-job workload did not retain every result")
    if any(outcome.state is not jobs17.JobState.SUCCEEDED for outcome in outcomes):
        raise SystemExit("background-job workload contains non-success outcomes")
    if diagnostics.unfinished != 0 or diagnostics.undrained != 0:
        raise SystemExit("background-job diagnostics are inconsistent after drain")
    if elapsed > BUDGET_SECONDS:
        raise SystemExit(
            f"background-job workload exceeded {BUDGET_SECONDS:.1f}s budget: {elapsed:.4f}s"
        )
    print(
        f"background_jobs_1_7: {JOB_COUNT} jobs in {elapsed:.4f}s "
        f"({diagnostics.accepted_total} accepted)"
    )


if __name__ == "__main__":
    main()
