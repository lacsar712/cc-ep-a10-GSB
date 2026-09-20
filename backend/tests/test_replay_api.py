"""API-level tests for the read-only version-step replay endpoint."""

import hashlib
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import JSONB

from app.cqrs import attach_artifact, complete_run, record_metric, start_run
from app.database import Base, get_db
from app.main import app


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    def _get_db():
        try:
            yield session
        finally:
            pass  # session lifecycle owned by the fixture

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        c._session = session
        yield c
    app.dependency_overrides.clear()
    session.close()


def _token(client, username, password):
    resp = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _completed_run(session):
    def sha(s):
        return hashlib.sha256(s.encode()).hexdigest()

    run = start_run(
        session,
        actor="researcher",
        project="p1",
        name="api-replay",
        dataset_content_sha256=sha("ds"),
        code_commit_sha="abc1234",
        description=None,
        run_id=uuid4(),
    )
    run = record_metric(
        session,
        run_id=run.id,
        actor="researcher",
        name="m1",
        value=1.0,
        step=0,
        expected_version=run.version,
    )
    run = attach_artifact(
        session,
        run_id=run.id,
        actor="researcher",
        name="a1",
        uri="s3://x/a1",
        content_sha256=sha("a1"),
        media_type=None,
        expected_version=run.version,
    )
    complete_run(
        session,
        run_id=run.id,
        actor="researcher",
        result_summary="ok",
        expected_version=run.version,
    )
    return run.id


def test_auditor_can_replay_and_official_projection_stays_completed(client):
    run_id = _completed_run(client._session)
    token = _token(client, "auditor", "audit123456")
    headers = {"Authorization": f"Bearer {token}"}

    expected = [
        (1, "running", 0, 0, False),
        (2, "running", 1, 0, False),
        (3, "running", 1, 1, False),
        (4, "completed", 1, 1, True),
    ]
    for version, status, metrics, artifacts, at_end in expected:
        resp = client.get(f"/api/runs/{run_id}/replay?version={version}", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["version"] == version
        assert body["status"] == status
        assert body["metric_count"] == metrics
        assert body["artifact_count"] == artifacts
        assert body["at_end"] == at_end
        assert body["current_event"]["version"] == version

        # The real projection endpoint must always report the completed final state.
        official = client.get(f"/api/runs/{run_id}", headers=headers).json()
        assert official["status"] == "completed"
        assert official["version"] == 4
        assert len(official["metrics_json"]) == 1
        assert len(official["artifacts_json"]) == 1


def test_replay_requires_auth(client):
    run_id = _completed_run(client._session)
    resp = client.get(f"/api/runs/{run_id}/replay?version=1")
    assert resp.status_code == 401


def test_replay_beyond_tail_clamps(client):
    run_id = _completed_run(client._session)
    token = _token(client, "auditor", "audit123456")
    resp = client.get(
        f"/api/runs/{run_id}/replay?version=99",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 4
    assert body["requested_version"] == 99
    assert body["at_end"] is True


def test_replay_version_must_be_positive(client):
    run_id = _completed_run(client._session)
    token = _token(client, "auditor", "audit123456")
    resp = client.get(
        f"/api/runs/{run_id}/replay?version=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_replay_unknown_run_404(client):
    token = _token(client, "auditor", "audit123456")
    resp = client.get(
        f"/api/runs/{uuid4()}/replay?version=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
