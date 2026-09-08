import sqlite3
import threading
import queue
import time
from datetime import datetime, timezone

class DatabaseManager:
    def __init__(self, db_path="telemetry.db"):
        self.db_path = db_path
        # Bounded queue prevents infinite memory growth if disk fails
        self.queue = queue.Queue(maxsize=10000)
        self.running = True
        
        # Launch the dedicated worker thread immediately upon instantiation
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self):
        # Establish connection strictly inside the worker thread boundary
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Configure SQLite for high-frequency decoupled writes
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        
        # Initialize schema
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                joint_1 INTEGER,
                joint_2 INTEGER,
                joint_3 INTEGER,
                checksum TEXT,
                status_code TEXT,
                source TEXT
            )
        ''')
        conn.commit()

        # Batch processing loop
        while self.running or not self.queue.empty():
            try:
                # Block lightly until a telemetry frame arrives
                item = self.queue.get(timeout=0.5)
                if item is None:  # Poison pill for shutdown
                    break
                    
                batch = [item]
                
                # Drain remaining items in the queue (up to 50) for micro-batching
                while not self.queue.empty() and len(batch) < 50:
                    try:
                        next_item = self.queue.get_nowait()
                        if next_item is None:
                            self.running = False
                            break
                        batch.append(next_item)
                    except queue.Empty:
                        break
                
                # Execute single disk write for the entire batch
                cursor.executemany('''
                    INSERT INTO telemetry (timestamp, joint_1, joint_2, joint_3, checksum, status_code, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', batch)
                conn.commit()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[DB_WORKER_ERROR] {e}")
        
        conn.close()

    def log_telemetry(self, joint_1: int, joint_2: int, joint_3: int, checksum: str, status_code: str, source="DISPATCH"):
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            # Memory-only operation (typically < 5 microseconds)
            self.queue.put_nowait((timestamp, joint_1, joint_2, joint_3, checksum, status_code, source))
        except queue.Full:
            print("[DB_QUEUE_FULL] Evicting telemetry frame to prevent hardware starvation")

    def get_recent_telemetry(self, limit=100):
        # Open an ephemeral, read-only connection isolated from the worker's write lock
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM telemetry ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            conn.close()
            return rows
        except sqlite3.OperationalError:
            # Catch scenario where table doesn't exist yet on first boot
            return []

    def shutdown(self):
        self.running = False
        self.queue.put(None)
        self.worker_thread.join(timeout=2.0)