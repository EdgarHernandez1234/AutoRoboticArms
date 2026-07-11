# models.py
# AutoRoboticArms Option C Subsystem - Hardened Relational Hybrid Schema Declarations
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel


class NodeConfiguration(SQLModel, table=True):
    """
    Persistent Storage Tier (Option B Focus).
    Stores long-term mechatronic joint calibrations, speed thresholds, and poses.
    This data is permanent and must NEVER be programmatically wiped by cleanup loops.
    """
    __tablename__ = "node_configurations"

    config_id: Optional[int] = Field(default=None, primary_key=True)
    profile_name: str = Field(index=True, unique=True, nullable=False)
    
    # Left 6-Axis Arm Hardware Constraint Profiles
    left_base_clamp: float = Field(default=180.0)
    left_shoulder_clamp: float = Field(default=180.0)
    left_elbow_clamp: float = Field(default=180.0)
    
    # Right 6-Axis Arm Hardware Constraint Profiles
    right_base_clamp: float = Field(default=180.0)
    right_shoulder_clamp: float = Field(default=180.0)
    right_elbow_clamp: float = Field(default=180.0)
    
    # Timestamping for Auditing and Change Tracking
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)}
    )


class TelemetryIngressQueue(SQLModel, table=True):
    """
    Ephemeral / Volatile Transactional Tier (Option C Focus).
    Acts as a high-speed on-disk buffer for kinematics logs waiting to be processed,
    packaged into GZIP-Protobuf frames (*.pb.gz), and synced to Google Cloud Storage.
    """
    __tablename__ = "telemetry_ingress_queue"

    record_id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: float = Field(index=True, nullable=False)  # Float Epoch Unix Time format
    system_state: str = Field(default="NOMINAL", index=True)  # e.g., 'NOMINAL', 'COMM_FAIL_HALT'
    
    # FUTURE STRATEGY PROOFING MITIGATION CONTRACT
    # Binds each payload to a specific generation of the compiled Protocol Buffer schema contract.
    # Prevents version mismatch crashes during downstream cloud processing or local data restores.
    schema_version: int = Field(default=1, index=True, nullable=False)

    # Dense, pre-serialized binary protocol buffer blobs representing 6-axis states
    left_arm_protobuf_blob: bytes = Field(default=b"")
    right_arm_protobuf_blob: bytes = Field(default=b"")
    
    watchdog_ms: int = Field(default=3000)
    
    # Status flags governing out-of-band upload transitions
    # Bounded states: 'PENDING', 'PROCESSING'
    sync_status: str = Field(default="PENDING", index=True)