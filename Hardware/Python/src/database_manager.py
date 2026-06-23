# ---------------------------------------------------------
# 1. STRUCTURAL CORE DEPENDENCIES
# ---------------------------------------------------------
import os
from sqlmodel import SQLModel, Session, create_engine, select, func
from models import TelemetryIngressQueue, NodeConfiguration

# The data store target filename. Sitting as a relative string,
# it materializes in whatever directory you invoke python from.
SQLITE_FILE_NAME = "autorobot_telemetry.db"
sqlite_url = f"sqlite:///{SQLITE_FILE_NAME}"

# MAX CAPACITY SETTING: Limit table size to 50,000 frames to prevent disk overflow
MAX_TELEMETRY_ROWS = 50000
PRUNE_BATCH_SIZE = 5000  # Delete in batches to minimize table lock times

# ---------------------------------------------------------
# 2. THE THREAD-INSULATED DB ENGINE ENGINE
# ---------------------------------------------------------
# check_same_thread=False allows multiple threads (like serial workers and upcoming 
# Web API dashboards) to concurrently leverage the same persistent engine instance.
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

def initialize_database():
    """
    Constructs the database tables dynamically on the storage disk if they 
    do not exist, and forces the SQLite engine into high-speed WAL mode.
    """
    # CRITICAL: auto_vacuum must be enabled BEFORE the tables are physically built
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA auto_vacuum = FULL;")

    # Create tables based on schemas registered inside models.py
    SQLModel.metadata.create_all(engine)
    
    # SYSTEM HYPER-DRIVE CONFIGURATION: Inject raw SQLite PRAGMA commands
    # to enforce industrial multi-threaded performance constraints.
    with engine.connect() as connection:
        # WAL Mode (Write-Ahead Logging) allows concurrent reads and writes 
        # without blockages or data locks on the mechatronic serial thread.
        connection.exec_driver_sql("PRAGMA journal_mode=WAL;")
        # Synchronous NORMAL drops flash memory sync barriers, accelerating 
        # append loops while preserving file system block alignment.
        connection.exec_driver_sql("PRAGMA synchronous=NORMAL;")
    print(f"[DATABASE] System initialized securely with Auto-Vacuum enabled. Persistence file bound: {SQLITE_FILE_NAME}")

# ---------------------------------------------------------
# 3. DATABASE PRUNING & MAINTENANCE
# ---------------------------------------------------------
def prune_old_telemetry(session: Session):
    """
    Evaluates current record allocations. If the row count exceeds limits,
    it systematically drops the oldest batch and flushes the sectors.
    """
    # Count total entries in our logging stream
    total_rows = session.exec(select(func.count(TelemetryIngressQueue.id))).one()
    
    if total_rows > MAX_TELEMETRY_ROWS:
        # Programmatic Warning Action: Intercept and escalate state
        print(f"[WARN] Database usage threshold breached ({total_rows} rows). Triggering Auto-Prune...")
        
        # Identify the boundary ID of the oldest batch to remove
        oldest_boundary_subquery = (
            select(TelemetryIngressQueue.id)
            .order_by(TelemetryIngressQueue.id.asc())
            .limit(PRUNE_BATCH_SIZE)
        )
        oldest_ids = session.exec(oldest_boundary_subquery).all()
        # Execute deletion of the identified oldest records
        if oldest_ids:
            # Batch execute the delete operation
            for record_id in oldest_ids:
                record = session.get(TelemetryIngressQueue, record_id)
                if record:
                    session.delete(record)
            
            session.commit()
            print(f"[DATABASE] Clean sweep executed. Removed oldest {len(oldest_ids)} tracking rows.")

# ---------------------------------------------------------
# 4. HIGH-FREQUENCY DATA WRITING WRAPPERS
# ---------------------------------------------------------
def log_telemetry_state(target_coords: dict, angles: dict, status: str, checksum: str):
    """
    Appends real-time operational transactions straight onto the storage medium.
    Accepts target data maps, downscaled integer configurations, and forensic flags.
    """
    # Unpack properties dynamically to preserve safety layers if calculation exceptions occur
    base = angles["base"] if angles else 0
    shoulder = angles["shoulder"] if angles else 0
    elbow = angles["elbow"] if angles else 0
    
    telemetry_record = TelemetryIngressQueue(
        target_x=target_coords["x"],
        target_y=target_coords["y"],
        target_z=target_coords["z"],
        base_angle=base,
        shoulder_angle=shoulder,
        elbow_angle=elbow,
        status=status,
        checksum_sent=checksum
    )
    
    # Establish a context-managed transactional session block
    with Session(engine) as session:
        session.add(telemetry_record)
        session.commit() # Safely flush transaction buffers straight down to disk sectors

        # Automatically monitor database health at the end of the write transaction
        prune_old_telemetry(session)