# database_manager.py
import os
from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import event

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

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

@event.listens_for(engine, "connect")
def activate_sqlite_wal_mode(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA cache_size=-64000;")
    cursor.close()

def initialize_database():
    """Declares table structures natively across the runtime boundary."""
    SQLModel.metadata.create_all(engine)

def get_db_session():
    with Session(engine) as session:
        yield session