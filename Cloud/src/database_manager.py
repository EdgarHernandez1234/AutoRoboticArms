# database_manager.py
import os
from typing import Optional
from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import event
from sqlalchemy.engine import Engine

# Global reference handles for deferred tracking states
_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """
    Marcus's Dynamic Import Order Shield.
    Evaluates filesystem paths and environment states lazily upon dynamic execution call.
    Prevents import-ordering leakage bugs between test harnesses and production servers.
    """
    global _engine
    
    # Return the existing cached engine instance if it has already been initialized
    if _engine is not None:
        return _engine

# HARDENING PASS: Read environmental targets, fall back cleanly to a dedicated local directory
DATABASE_DIR = os.getenv("TELEMETRY_STORAGE_DIR", "storage_chunks")

# Convert path strictly to an absolute string to clear Anaconda / Python 3.13 edge bugs
DATABASE_DIR_ABS = os.path.abspath(DATABASE_DIR)
DATABASE_PATH_ABS = os.path.join(DATABASE_DIR_ABS, "production_node.db")

# MANDATORY ENGINE GUARDRAIL: Folders MUST exist on disk before the create_engine call evaluates!
os.makedirs(DATABASE_DIR_ABS, exist_ok=True)

# SQLAlchemy Absolute Connection URI Pattern (Resolves to 4 slashes total on Linux/macOS)
DATABASE_URL = f"sqlite:///{DATABASE_PATH_ABS}"

connect_args = {
    "timeout": 60.0,
    "check_same_thread": False
}
    
# Instantiate the secure multi-threaded engine reference link safely
_engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

# Attach our high-concurrency WAL pragma connection listeners programmatically
@event.listens_for(_engine, "connect")
def activate_sqlite_wal_mode(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA cache_size=-64000;")
    cursor.close()

    return _engine

def initialize_database():
    """Natively constructs database constraints utilizing the deferred factory link."""
    active_engine = get_engine()
    SQLModel.metadata.create_all(active_engine)

def get_db_session():
    """Yields active transactional contexts bound directly to the dynamic factory core."""
    active_engine = get_engine()
    with Session(active_engine) as session:
        yield session