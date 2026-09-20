import hashlib
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cqrs import (
    ConflictError,
    DomainError,
    abort_run,
    attach_artifact,
    complete_run,
    list_events,
    rebuild_projection_from_events,
    record_metric,
    replay_projection_at_version,
    start_run,
)
from app.database import Base
from app.models import RunProjection


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # JSONB not available on SQLite — remap via create_all with JSON
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    # For SQLite tests, compile JSONB as JSON
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_sqlite(_type, compiler, **kw):
        return "JSON"

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_start_and_complete_happy_path(db):
    run = start_run(
        db,
        actor="researcher",
        project="p1",
        name="n1",
        dataset_content_sha256=sha("ds"),
        code_commit_sha="abc1234",
        description="d",
    )
    assert run.status == "running"
    assert run.version == 1

    run = record_metric(
        db,
        run_id=run.id,
        actor="researcher",
        name="acc",
        value=0.9,
        step=1,
        expected_version=1,
    )
    assert run.version == 2
    assert len(run.metrics_json) == 1

    run = complete_run(
        db,
        run_id=run.id,
        actor="researcher",
        result_summary="done",
        expected_version=2,
    )
    assert run.status == "completed"
    assert run.version == 3

    with pytest.raises(ConflictError):
        record_metric(
            db,
            run_id=run.id,
            actor="researcher",
            name="acc",
            value=0.95,
            step=2,
            expected_version=3,
        )


def test_optimistic_lock_conflict(db):
    run = start_run(
        db,
        actor="researcher",
        project="p1",
        name="n1",
        dataset_content_sha256=sha("ds2"),
        code_commit_sha="abc1234",
        description=None,
    )
    with pytest.raises(ConflictError):
        record_metric(
            db,
            run_id=run.id,
            actor="researcher",
            name="loss",
            value=1.0,
            step=1,
            expected_version=0,
        )


def test_abort_terminal(db):
    run = start_run(
        db,
        actor="researcher",
        project="p1",
        name="n1",
        dataset_content_sha256=sha("ds3"),
        code_commit_sha="abc1234",
        description=None,
    )
    run = abort_run(
        db,
        run_id=run.id,
        actor="researcher",
        reason="OOM",
        expected_version=1,
    )
    assert run.status == "aborted"
    with pytest.raises(ConflictError):
        complete_run(
            db,
            run_id=run.id,
            actor="researcher",
            result_summary="nope",
            expected_version=2,
        )


def test_projection_matches_event_replay(db):
    run = start_run(
        db,
        actor="researcher",
        project="p1",
        name="n1",
        dataset_content_sha256=sha("ds4"),
        code_commit_sha="deadbeef",
        description="x",
        run_id=uuid4(),
    )
    run = record_metric(
        db,
        run_id=run.id,
        actor="researcher",
        name="f1",
        value=1.5,
        step=0,
        expected_version=run.version,
    )
    run = attach_artifact(
        db,
        run_id=run.id,
        actor="researcher",
        name="model.bin",
        uri="file:///tmp/model.bin",
        content_sha256=sha("model"),
        media_type="application/octet-stream",
        expected_version=run.version,
    )
    run = complete_run(
        db,
        run_id=run.id,
        actor="researcher",
        result_summary="ok",
        expected_version=run.version,
    )

    events = list_events(db, run.id)
    assert [e.event_type for e in events] == [
        "RunStarted",
        "MetricRecorded",
        "ArtifactAttached",
        "RunCompleted",
    ]

    rebuilt = rebuild_projection_from_events(db, run.id)
    stored = db.get(RunProjection, run.id)
    assert rebuilt is not None and stored is not None
    assert rebuilt.status == stored.status
    assert rebuilt.version == stored.version
    assert rebuilt.dataset_content_sha256 == stored.dataset_content_sha256
    assert rebuilt.code_commit_sha == stored.code_commit_sha
    assert len(rebuilt.metrics_json) == len(stored.metrics_json)
    assert len(rebuilt.artifacts_json) == len(stored.artifacts_json)


def test_cannot_command_before_start(db):
    missing = uuid4()
    with pytest.raises(DomainError):
        record_metric(
            db,
            run_id=missing,
            actor="researcher",
            name="x",
            value=1,
            step=0,
            expected_version=0,
        )


def _build_completed_run(db):
    run = start_run(
        db,
        actor="researcher",
        project="p1",
        name="replay-demo",
        dataset_content_sha256=sha("ds-replay"),
        code_commit_sha="abc1234",
        description=None,
    )
    run = record_metric(
        db,
        run_id=run.id,
        actor="researcher",
        name="m1",
        value=0.5,
        step=0,
        expected_version=run.version,
    )
    run = attach_artifact(
        db,
        run_id=run.id,
        actor="researcher",
        name="a1",
        uri="s3://bucket/a1",
        content_sha256=sha("a1"),
        media_type=None,
        expected_version=run.version,
    )
    run = complete_run(
        db,
        run_id=run.id,
        actor="researcher",
        result_summary="done",
        expected_version=run.version,
    )
    return run


def test_replay_step_by_step_shows_running_to_completed(db):
    run = _build_completed_run(db)
    # events: v1 RunStarted, v2 MetricRecorded, v3 ArtifactAttached, v4 RunCompleted

    proj, ev, reached, total = replay_projection_at_version(db, run.id, 1)
    assert reached == 1
    assert total == 4
    assert proj.status == "running"
    assert proj.version == 1
    assert len(proj.metrics_json) == 0
    assert len(proj.artifacts_json) == 0
    assert ev.event_type == "RunStarted"

    proj, _, reached, _ = replay_projection_at_version(db, run.id, 2)
    assert reached == 2
    assert proj.status == "running"
    assert len(proj.metrics_json) == 1
    assert len(proj.artifacts_json) == 0

    proj, _, reached, _ = replay_projection_at_version(db, run.id, 3)
    assert reached == 3
    assert proj.status == "running"
    assert len(proj.metrics_json) == 1
    assert len(proj.artifacts_json) == 1

    proj, ev, reached, _ = replay_projection_at_version(db, run.id, 4)
    assert reached == 4
    assert proj.status == "completed"
    assert proj.result_summary == "done"
    assert len(proj.metrics_json) == 1
    assert len(proj.artifacts_json) == 1
    assert ev.event_type == "RunCompleted"


def test_replay_does_not_mutate_official_projection(db):
    run = _build_completed_run(db)
    stored_before = db.get(RunProjection, run.id)
    snapshot_before = (
        stored_before.status,
        stored_before.version,
        len(stored_before.metrics_json),
        len(stored_before.artifacts_json),
    )

    # Walk through every version, including a mid-run step: official row must stay at v4/completed.
    for v in range(1, 5):
        proj, _, _, _ = replay_projection_at_version(db, run.id, v)
        # mid-run replay state differs from the completed official projection
        if v < 4:
            assert proj.status == "running"
            assert proj.id == run.id

    stored_after = db.get(RunProjection, run.id)
    assert (
        stored_after.status,
        stored_after.version,
        len(stored_after.metrics_json),
        len(stored_after.artifacts_json),
    ) == snapshot_before == ("completed", 4, 1, 1)
    # The replayed object is transient (not attached/persisted); expunging must be a no-op.
    db.expunge_all()
    still = db.get(RunProjection, run.id)
    assert still is not None and still.status == "completed"


def test_replay_beyond_tail_clamps_to_last_version(db):
    run = _build_completed_run(db)
    proj, ev, reached, total = replay_projection_at_version(db, run.id, 99)
    assert total == 4
    assert reached == 4
    assert proj.status == "completed"
    assert ev.version == 4


def test_replay_rejects_version_below_one(db):
    run = _build_completed_run(db)
    with pytest.raises(DomainError):
        replay_projection_at_version(db, run.id, 0)


def test_replay_unknown_run_is_404(db):
    with pytest.raises(DomainError) as exc:
        replay_projection_at_version(db, uuid4(), 1)
    assert exc.value.status_code == 404
