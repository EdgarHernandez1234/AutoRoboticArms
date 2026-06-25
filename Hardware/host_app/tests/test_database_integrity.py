import sys
import os
import pytest
from sqlmodel import SQLModel, Session, create_engine, select
from pydantic import ValidationError
from datetime import datetime
from sqlalchemy.exc import StatementError    
# Import schema blueprints from the host application
host_main = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src"))
sys.path.append(host_main)
from database_manager import TelemetryIngressQueue, NodeConfiguration, log_telemetry_state

# ---------------------------------------------------------
# 1. THE IN-MEMORY TEST FIXTURE (The Sandbox)
# ---------------------------------------------------------
# 'sqlite:///:memory:' creates a database entirely in RAM. 
# It is lightning fast and guarantees we never touch the real .db file.
@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    # Once the test completes, the memory is instantly dumped and cleared.

# ---------------------------------------------------------
# 2. TEST CASE A: The Nominal Telemetry Ingress (Happy Path)
# ---------------------------------------------------------
def test_valid_telemetry_commit(session: Session):
    """
    Simulates the serial thread pushing a valid, perfect coordinate 
    frame into the database to ensure the schema accepts it.
    """
    valid_log = TelemetryIngressQueue(
        target_x=12.5,
        target_y=5.0,
        target_z=10.0,
        base_angle=90,
        shoulder_angle=45,
        elbow_angle=135,
        status="NOMINAL",
        checksum_sent="A1"
    )
    
    session.add(valid_log)
    session.commit()
    
    # Query the RAM database to ensure the row actually saved
    statement = select(TelemetryIngressQueue).where(TelemetryIngressQueue.checksum_sent == "A1")
    retrieved_log = session.exec(statement).first()
    
    assert retrieved_log is not None
    assert retrieved_log.base_angle == 90
    assert retrieved_log.status == "NOMINAL"

# ---------------------------------------------------------
# 3. TEST CASE B: The Type-Coercion Attack (Validation Filter)
# ---------------------------------------------------------
def test_schema_rejects_corrupted_datatypes(session: Session):
    """
    Common Telemetry Bug: A sensor glitches and sends a string instead of a float.
    We assert that SQLModel acts as a strict firewall and blocks the creation.
    """
    with pytest.raises((StatementError, ValidationError)) as exc_info:
        # We intentionally pass the string "ERROR" into a float field
# STEP 1: The Trigger (Injecting the Poison Pill)
        log_telemetry_state(
            target_coords={"x": "MALFORMED_STRING", "y": 1.0, "z": 1.0}, # 'x' expects a float!
            angles={"base": 90, "shoulder": 45, "elbow": 30},
            status="NOMINAL",
            checksum="FF"
        )
        print(f"[TEST-ASSERT] Successfully caught schema rejection: {exc_info.type}")

# ---------------------------------------------------------
# 4. TEST CASE C: Configuration Uniqueness (Index Collision)
# ---------------------------------------------------------
def test_node_configuration_uniqueness(session: Session):
    """
    Common Database Bug: Accidentally creating two settings with the same name.
    We assert that the database explicitly rejects duplicate parameter names.
    """
    setting_1 = NodeConfiguration(parameter_name="MAX_SPEED", parameter_value=100.0)
    session.add(setting_1)
    session.commit()
    
    setting_2 = NodeConfiguration(parameter_name="MAX_SPEED", parameter_value=150.0)
    session.add(setting_2)
    
    # The commit should fail because 'parameter_name' requires unique=True
    with pytest.raises(Exception):
        session.commit()