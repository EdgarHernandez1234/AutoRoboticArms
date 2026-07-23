### 🧪 Code Asset 5: `test_conductor.py
# test_conductor.py
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
    """Validates Dr. Julian's angle bounds checking logic."""
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
        # Marcus's Rule: Guaranteed thread stop even if test crashes
        orchestrator.stop()

    # Query SQLite database to confirm background flusher executed bulk inserts
    engine = get_engine()
    with Session(engine) as session:
        statement = select(TelemetryIngressQueue)
        results = session.exec(statement).all()
        
        assert len(results) > 0, "Concurrency Error: Flusher thread failed to commit rows to database!"
        # Verify single-arm schema contract properties
        sample = results[0]
        assert sample.left_arm_protobuf_blob.startswith(b"L_ARM:")
        assert sample.right_arm_protobuf_blob == b""
        assert sample.schema_version == 1
        assert sample.sync_status == "PENDING"