# ---------------------------------------------------------
# 1. ARCHITECTURAL & PATH RESOLUTION IMPORTS
# ---------------------------------------------------------
import os
import sys
import pytest
from sqlmodel import SQLModel, Session, create_engine

# BVA PATH INSULATION: Programmatically hook the root 'host_app/src' 
# directory into the system runtime path. This eliminates 
# ModuleNotFoundErrors when running pytest from the root of the workspace.
host_main = os.path.abspath(os.path.join(os.path.dirname(__file__), "../src"))
sys.path.append(host_main)
import database_manager

# ---------------------------------------------------------
# 2. GLOBAL SYSTEM TEST FIXTURES
# ---------------------------------------------------------

@pytest.fixture(scope="session", name="test_engine")
def db_engine_fixture(tmp_path_factory):
    """
    Session-Scoped Fixture: Allocates a singular, shared SQLite database 
    entirely within the host computer's volatile RAM memory (RAM).
    
    Using scope="session" ensures we only build the database tables ONCE 
    for the entire test run, maximizing testing speed. Now includes Ephemeral Disked-Backed Pattern to account for 
    filesystem mechanics, database writes, 
    and WAL performance metrics accurately without polluting production storage channels
    """
    test_dir = tmp_path_factory.mktemp("autorobot_staging")
    test_db_path = test_dir / "test_autorobot_telemetry.db"
    # Create the temporary volatile RAM database sandbox
    sqlite_url = f"sqlite:///{test_db_path}"
    engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})    

    # Materialize our models.py blueprints onto the RAM blocks
    SQLModel.metadata.create_all(engine)
    # ENFORCE SYSTEM HYPER-DRIVE PARITY: Run our precise database optimizations 
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL;")
        connection.exec_driver_sql("PRAGMA synchronous=NORMAL;")

    yield engine
    
    # Tear-down step: Clean up our temporary allocation blocks when tests finish
    SQLModel.metadata.drop_all(engine)
    if test_db_path.exists():
        os.remove(test_db_path)


@pytest.fixture(scope="function", name="db_session")
def db_session_fixture(test_engine):
    """
    Function-Scoped Fixture: Yields a brand-new, isolated transactional database 
    session for every single individual test method block.
    
    Crucially, it executes a hard ROLLBACK at the end of each test case. This 
    guarantees absolute isolation—data written by 'Test A' can never leak out 
    and corrupt the results of 'Test B'.
    """
    with Session(test_engine) as session:
        yield session
        # THE CLEAN Shield: Force an atomic rollback to return theRAM 
        # database plane to a perfectly pristine, predictable state.
        session.rollback()

@pytest.fixture(autouse=True)
def patch_production_database_engine(test_engine, monkeypatch):
    """
    SECURITY INTERCEPT: Automatically forces the production database manager 
    to route all writes into our secure, ephemeral disk-backed test engine 
    for the duration of every test.
    """
    monkeypatch.setattr(database_manager, "engine", test_engine)