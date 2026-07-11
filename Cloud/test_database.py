# test_database.py
# AutoRoboticArms Option C Subsystem - Sprint 1 Relational Testing Module
import os
import sys
import shutil
import pytest
from sqlmodel import Session, select, inspect
from sqlalchemy.exc import IntegrityError

# Set environmental override BEFORE importing modules to intercept database directory routing
TEST_STORAGE_DIR = "./test_storage_sandbox"
os.environ["TELEMETRY_STORAGE_DIR"] = TEST_STORAGE_DIR


from src.database_manager import engine, initialize_database
from src.models import NodeConfiguration, TelemetryIngressQueue


@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown_test_environment():
    """
    Volume Path Isolation Test Fixture.
    Guarantees test executions land strictly inside the unprivileged local directory sandbox.
    Cleans up all generated filesystem structures upon test teardown passes.
    """
    # Force a clean folder creation slate
    if os.path.exists(TEST_STORAGE_DIR):
        shutil.rmtree(TEST_STORAGE_DIR)
    
    # FIX: Re-create the empty directory after wiping it so SQLite has a valid path handle!
    os.makedirs(os.path.abspath(TEST_STORAGE_DIR), exist_ok=True)
    
    initialize_database()
    yield
    
    # Teardown pass: Purge test artifact database files from disk
    if os.path.exists(TEST_STORAGE_DIR):
        shutil.rmtree(TEST_STORAGE_DIR)


def test_sqlite_wal_mode_activation():
    """
    Vulnerability Guardrail Proof: Concurrency Shielding.
    Asserts that our SQLAlchemy connection listener natively forces the engine driver
    into Write-Ahead Logging (WAL) Mode to eliminate core loop lock contention stalls.
    """
    with engine.connect() as connection:
        result = connection.exec_driver_sql("PRAGMA journal_mode;").fetchone()
        assert result is not None
        assert result[0].lower() == "wal", "Vulnerability Error: Database failed to force WAL journal mode!"


def test_database_table_compilation():
    """
    Lifecycle Validation: Reflective Structural Pass.
    Inspects disk topology mappings via SQLAlchemy reflection to verify tables compiled correctly.
    """
    inspector = inspect(engine)
    discovered_tables = inspector.get_table_names()
    
    assert "node_configurations" in discovered_tables, "Schema Error: node_configurations table missing!"
    assert "telemetry_ingress_queue" in discovered_tables, "Schema Error: telemetry_ingress_queue table missing!"


def test_node_configuration_default_clamps():
    """
    Model Functional Validation: Safe Bounds Defaulting.
    Asserts that unpopulated configurations default automatically to our 180.0-degree safety bounds.
    """
    config = NodeConfiguration(profile_name="alpha_test_bench")
    assert config.left_base_clamp == 180.0
    assert config.right_elbow_clamp == 180.0
    assert config.config_id is None  # Primary Key must remain unassigned before insert


def test_profile_name_uniqueness_constraint():
    """
    Model Functional Validation: Identity Constraints.
    Verifies that the database strictly rejects duplicate configuration names, preventing profile overwrites.
    """
    with Session(engine) as session:
        # Commit first record cleanly
        config1 = NodeConfiguration(profile_name="unique_bench_profile")
        session.add(config1)
        session.commit()
        
        # Intentional duplication attempt to verify transactional armoring
        config2 = NodeConfiguration(profile_name="unique_bench_profile")
        session.add(config2)
        
        with pytest.raises(IntegrityError):
            session.commit()
            
        session.rollback()


def test_telemetry_ingress_queue_future_proofing_tag():
    """
    Model Functional Validation: Elena's Future Strategy Proofing.
    Asserts that every ingestion snap automatically logs a default schema version integer tag
    to ensure complete backward compatibility during downstream cloud processing runs.
    """
    with Session(engine) as session:
        ingress_record = TelemetryIngressQueue(
            timestamp=1719792000.0,
            left_arm_protobuf_blob=b"\x08\x5a\x12\x04\x12\x02\x00\x01",
            right_arm_protobuf_blob=b"\x08\x2d\x12\x04\x12\x02\x00\x02"
        )
        session.add(ingress_record)
        session.commit()
        session.refresh(ingress_record)
        
        # Verify from database select query that the version tag resolved on disk
        statement = select(TelemetryIngressQueue).where(TelemetryIngressQueue.record_id == ingress_record.record_id)
        queried_record = session.exec(statement).one()
        
        assert queried_record.schema_version == 1, "Strategy Error: Telemetry snap dropped without schema_version field!"
        assert queried_record.sync_status == "PENDING"