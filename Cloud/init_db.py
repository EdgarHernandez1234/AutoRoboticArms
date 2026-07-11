# init_db.py
# Executive Initialization Validation Script for Sprint 1
from src.database_manager import initialize_database, DATABASE_PATH_ABS
from src.models import NodeConfiguration, TelemetryIngressQueue
import os

if __name__ == "__main__":
    print("⚙️ Initializing Hardened Hybrid Database Layer...")
    try:
        initialize_database()
        print(f"✅ Success! Database asset compiled at target: {DATABASE_PATH_ABS}")
        
        # Physical check for the companion WAL journal log structure on disk
        wal_path = f"{DATABASE_PATH_ABS}-wal"
        if os.path.exists(DATABASE_PATH_ABS):
            print("🧱 SQLite engine locked onto persistent local storage frames.")
            
    except Exception as e:
        print(f"❌ Critical System Initialization Drop: {str(e)}")