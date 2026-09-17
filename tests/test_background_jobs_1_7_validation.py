from __future__ import annotations

import pytest

from swirengine.jobs17 import JobRejectedError, JobScheduler


@pytest.mark.parametrize(
    "dependencies",
    [None, 42, {"root"}, {"root": "value"}, object()],
)
def test_malformed_dependency_containers_use_stable_rejection_code(dependencies: object) -> None:
    with JobScheduler(max_workers=1, max_pending=4) as scheduler:
        scheduler.submit("root", lambda context: context.job_id)
        with pytest.raises(JobRejectedError) as rejected:
            scheduler.submit("child", lambda context: context.job_id, dependencies=dependencies)

        assert rejected.value.code == "invalid_dependencies"
        diagnostics = scheduler.diagnostics()
        assert diagnostics.accepted_total == 1
        assert diagnostics.rejected_total == 1
