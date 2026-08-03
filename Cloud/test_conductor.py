# Sprint 2 Automated Concurrency & Micro-Batching Test Harness
import os
import shutil
import time
import pytest
from sqlmodel import Session, select

TEST_STORAGE_DIR = "test_conductor_sandbox"
os.environ["TELEMETRY_STORAGE_DIR"] = TEST_STORAGE_DIR

from src.database_manager import get_engine, initialize_database
from src.models import TelemetryIngressQueue
from src.conductor_host import ConductorOrchestrator, validate_arm_telemetry


@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown_conductor_environment():
    """Volume Path Isolation & Guaranteed Teardown Fixture."""
    if os.path.exists(TEST_STORAGE_DIR):
        shutil.rmtree(TEST_STORAGE_DIR)
        
    os.makedirs(os.path.abspath(TEST_STORAGE_DIR), exist_ok=True)
    initialize_database()
    
    yield  # Test execution phase
    
    # GUARANTEED CLEANUP: Executes on pass or fail
    if os.path.exists(TEST_STORAGE_DIR):
        shutil.rmtree(TEST_STORAGE_DIR)


def test_telemetry_validation_logic():
    """Validates angle bounds checking logic."""
    assert validate_arm_telemetry(90.0, 45.0, 180.0) is True
    assert validate_arm_telemetry(-5.0, 45.0, 90.0) is False
    assert validate_arm_telemetry(90.0, 185.0, 90.0) is False
    assert validate_arm_telemetry("invalid", 45.0, 90.0) is False


def test_conductor_queue_batch_flushing():
    """
    Verifies multi-threaded queue producer/flusher lifecycle, 
    bulk database insertions, and atomic shutdown handling.
    """
    orchestrator = ConductorOrchestrator(queue_maxsize=50)
    
    try:
        orchestrator.start()
        # Allow threads to run for 1.2 seconds to produce and flush several batches
        time.sleep(1.2)
    finally:
        # Guaranteed thread stop even if test crashes
        orchestrator.stop()

    # Query SQLite database to confirm background flusher executed bulk inserts
    engine = get_engine()
    with Session(engine) as session:
        records = session.exec(select(TelemetryIngressQueue)).all()
        assert len(records) > 0

        # Verify Protobuf schema column key exists and contains bytes
        latest_record = records[-1]
        assert hasattr(latest_record, "left_arm_protobuf_blob")
        assert isinstance(latest_record.left_arm_protobuf_blob, bytes)
        assert len(latest_record.left_arm_protobuf_blob) > 0
        assert latest_record.system_state == "NOMINAL"