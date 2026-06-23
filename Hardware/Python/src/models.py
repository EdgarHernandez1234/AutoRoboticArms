# ---------------------------------------------------------
# 1. ARCHITECTURAL IMPORTS
# ---------------------------------------------------------
from typing import Optional
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel

# ---------------------------------------------------------
# 2. PERSISTENT SYSTEM STATE TABLE (NodeConfiguration)
# ---------------------------------------------------------
# The 'table=True' flag tells SQLModel to create a real SQLite table for this class.
class NodeConfiguration(SQLModel, table=True):
    """
    This table stores permanent, slow-changing systemic settings.
    Things like maximum safe angles, calibration offsets, or port names live here.
    If the Docker container restarts, the arm remembers its exact configuration.
    """
    
    # Primary Key: A unique integer ID for the database row. 
    # 'default=None' allows the database to auto-increment this number automatically.
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # The name of the setting (e.g., "MAX_SHOULDER_ANGLE"). 
    # 'index=True' makes searching for this specific name incredibly fast.
    parameter_name: str = Field(index=True, unique=True)
    
    # The actual numerical value of the setting.
    parameter_value: float
    
    # Automatically logs the exact time this setting was last updated.
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------
# 3. HIGH-FREQUENCY DATA LOGGING TABLE (TelemetryIngressQueue)
# ---------------------------------------------------------
class TelemetryIngressQueue(SQLModel, table=True):
    """
    This table stores high-frequency, ephemeral data snap matrices.
    Every time the Python orchestrator calculates a new angle and sends it to the Arduino,
    a permanent receipt (row) is written here for auditing, debugging, and dashboarding.
    """
    
    # Primary Key for the telemetry log
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Timestamp of the command.
    # 'index=True' is CRITICAL here: It allows your Web Dashboard to instantly 
    # fetch the "last 5 seconds of data" without scanning the entire massive database.
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    
    # -----------------------------------------------------
    # The Input: The spatial target requested by the network
    # -----------------------------------------------------
    target_x: float
    target_y: float
    target_z: float
    
    # -----------------------------------------------------
    # The Output: The translated integer angles sent to the hardware
    # -----------------------------------------------------
    base_angle: int
    shoulder_angle: int
    elbow_angle: int
    
    # -----------------------------------------------------
    # Safety & Security Audit Trail
    # -----------------------------------------------------
    # Status tracks if the command was sent successfully or blocked by safety limits
    status: str = Field(default="NOMINAL") # e.g., "NOMINAL", "FAULT", "BLOCKED"
    
    # The exact 2-character hexadecimal XOR string that was sent down the wire
    checksum_sent: str