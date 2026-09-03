"""远程 Agent 终态回传的重试链回归。"""

from __future__ import annotations

from types import SimpleNamespace

from app.api.v1.agent import _remote_run_attempt, _schedule_remote_retry


class _FakeDb:
    def __init__(self, *runs: SimpleNamespace) -> None:
        self.runs = {run.id: run for run in runs}

    def get(self, _model: object, run_id: int) -> SimpleNamespace | None:
        return self.runs.get(run_id)


def _run(
    run_id: int,
    *,
    trigger_type: str = "scheduled",
    parent_run_id: int | None = None,
    status: str = "failure",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=run_id,
        trigger_type=trigger_type,
        parent_run_id=parent_run_id,
        status=status,
    )


def test_remote_run_attempt_counts_retry_chain() -> None:
    first = _run(1)
    retry_one = _run(2, trigger_type="retry", parent_run_id=first.id)
    retry_two = _run(3, trigger_type="retry", parent_run_id=retry_one.id)
    db = _FakeDb(first, retry_one, retry_two)

    assert _remote_run_attempt(db, first) == 1
    assert _remote_run_attempt(db, retry_one) == 2
    assert _remote_run_attempt(db, retry_two) == 3


def test_remote_failure_schedules_retry_with_next_attempt(monkeypatch) -> None:
    run = _run(10)
    db = _FakeDb(run)
    instance = SimpleNamespace(
        id=5,
        max_retries=1,
        retry_interval_sec=300,
    )
    calls: list[dict[str, int]] = []

    class _Scheduler:
        _started = True

        def schedule_retry(self, **kwargs: int) -> None:
            calls.append(kwargs)

    monkeypatch.setattr("app.deps.get_scheduler_service", lambda: _Scheduler())

    assert _schedule_remote_retry(db, run, instance) is True
    assert calls == [
        {
            "instance_id": 5,
            "parent_run_id": 10,
            "next_attempt": 2,
            "delay_sec": 300,
        }
    ]


def test_remote_success_and_retry_limit_do_not_schedule(monkeypatch) -> None:
    calls: list[dict[str, int]] = []

    class _Scheduler:
        _started = True

        def schedule_retry(self, **kwargs: int) -> None:
            calls.append(kwargs)

    monkeypatch.setattr("app.deps.get_scheduler_service", lambda: _Scheduler())

    for run, max_retries in (
        (_run(20, status="success"), 1),
        (_run(21), 0),
    ):
        instance = SimpleNamespace(
            id=5,
            max_retries=max_retries,
            retry_interval_sec=300,
        )
        assert _schedule_remote_retry(_FakeDb(run), run, instance) is False

    assert calls == []
