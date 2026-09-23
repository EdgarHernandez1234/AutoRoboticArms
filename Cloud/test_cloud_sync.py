import os
import time
import gzip
import tempfile
import pytest
from unittest.mock import MagicMock
from sqlmodel import SQLModel, Session, create_engine, select
from botocore.exceptions import ClientError

from src.cloud_sync import CloudSyncWorker
from src.models import TelemetryIngressQueue


@pytest.fixture
def test_db_session():
    """Provides an isolated temporary disk-backed SQLite database for testing."""
    fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{temp_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session, engine

    engine.dispose()
    for ext in ["", "-wal", "-shm"]:
        if os.path.exists(temp_path + ext):
            os.remove(temp_path + ext)


@pytest.fixture
def mock_s3_worker(test_db_session, monkeypatch):
    """Instantiates CloudSyncWorker with mock S3 client and isolated database."""
    session, engine = test_db_session
    monkeypatch.setenv("BUCKET_NAME", "mock-telemetry-bucket")

    worker = CloudSyncWorker(bucket_name="mock-telemetry-bucket")
    worker.engine = engine
    worker.s3_client = MagicMock()
    return worker, session


def test_boot_stale_record_sweep(mock_s3_worker):
    """Verifies stranded PROCESSING records are reset to PENDING on startup."""
    worker, session = mock_s3_worker

    # Seed 3 orphaned records in PROCESSING state
    for i in range(3):
        rec = TelemetryIngressQueue(
            timestamp=time.time(),
            system_state="NOMINAL",
            left_arm_protobuf_blob=b"blob_data",
            sync_status="PROCESSING",
        )
        session.add(rec)
    session.commit()

    recovered = worker.boot_stale_record_sweep()
    assert recovered == 3

    # Assert all 3 records reverted to PENDING
    records = session.exec(select(TelemetryIngressQueue)).all()
    assert all(r.sync_status == "PENDING" for r in records)


def test_hybrid_batch_size_trigger(mock_s3_worker):
    """Verifies that reaching batch_size_threshold (50) triggers immediate upload."""
    worker, session = mock_s3_worker
    worker.s3_client.put_object.return_value = {"ETag": '"mock_hash"'}

    # Seed 50 records
    for _ in range(50):
        rec = TelemetryIngressQueue(
            timestamp=time.time(),
            system_state="NOMINAL",
            left_arm_protobuf_blob=b"payload_bytes",
            sync_status="PENDING",
        )
        session.add(rec)
    session.commit()

    processed_count = worker.sync_cycle()
    assert processed_count == 50
    assert worker.s3_client.put_object.call_count == 1

    # Verify rows transitioned to SYNCED
    records = session.exec(select(TelemetryIngressQueue)).all()
    assert len(records) == 50
    assert all(r.sync_status == "SYNCED" for r in records)


def test_hybrid_batch_time_trigger(mock_s3_worker):
    """Verifies sub-threshold batches flush when time threshold (30s) elapses."""
    worker, session = mock_s3_worker
    worker.s3_client.put_object.return_value = {"ETag": '"mock_hash"'}

    # Seed only 10 records (below size threshold)
    for _ in range(10):
        rec = TelemetryIngressQueue(
            timestamp=time.time(),
            system_state="NOMINAL",
            left_arm_protobuf_blob=b"payload_bytes",
            sync_status="PENDING",
        )
        session.add(rec)
    session.commit()

    # Simulate 31 seconds of elapsed time
    worker.last_flush_time = time.time() - 31.0

    processed_count = worker.sync_cycle()
    assert processed_count == 10
    assert worker.s3_client.put_object.call_count == 1


def test_empty_batch_quota_protection(mock_s3_worker):
    """Verifies that an idle queue never issues S3 PutObject calls."""
    worker, session = mock_s3_worker

    # Simulate elapsed time with zero records in queue
    worker.last_flush_time = time.time() - 35.0

    processed_count = worker.sync_cycle()
    assert processed_count == 0
    assert worker.s3_client.put_object.call_count == 0


def test_circuit_breaker_trip_on_consecutive_failures(mock_s3_worker):
    """Verifies consecutive failures trip circuit breaker and roll back records."""
    worker, session = mock_s3_worker
    worker.s3_client.put_object.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "InternalError"}}, "PutObject"
    )

    # Seed 50 records
    for _ in range(50):
        rec = TelemetryIngressQueue(
            timestamp=time.time(),
            system_state="NOMINAL",
            left_arm_protobuf_blob=b"payload_bytes",
            sync_status="PENDING",
        )
        session.add(rec)
    session.commit()

    # Trigger failure 1
    worker.sync_cycle()
    assert worker.consecutive_failures == 1

    # Trigger failure 2
    worker.sync_cycle()
    assert worker.consecutive_failures == 2

    # Trigger failure 3 (trips circuit breaker)
    worker.sync_cycle()
    assert worker.consecutive_failures == 3
    assert worker.circuit_open_until > time.time()

    # While breaker is tripped, subsequent cycles immediately abort
    aborted_run = worker.sync_cycle()
    assert aborted_run == 0

    # Ensure records rolled back to PENDING rather than remaining stuck in PROCESSING
    records = session.exec(select(TelemetryIngressQueue)).all()
    assert all(r.sync_status == "PENDING" for r in records)
