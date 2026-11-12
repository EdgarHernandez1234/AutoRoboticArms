"""
database_manager.py
Thread-isolated, asynchronous SQLite WAL persistence engine.
Provides micro-batch writing and non-blocking telemetry logging.
"""
import sqlite3
import threading
import queue
import time
from typing import List, Dict, Any, Optional


class DatabaseManager:
    def __init__(self, db_path: str = "telemetry.db", batch_size: int = 10, flush_interval_sec: float = 0.5):
        self.db_path = db_path
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.log_queue: queue.Queue = queue.Queue(maxsize=10000)
        self.shutdown_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

    def _init_db(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                joint_1 INTEGER NOT NULL,
                joint_2 INTEGER NOT NULL,
                joint_3 INTEGER NOT NULL,
                validation_status TEXT NOT NULL,
                hardware_ack TEXT NOT NULL,
                command_type TEXT NOT NULL
            );
        """)
        conn.commit()

    def start(self):
        """Initializes tables and starts background flusher thread."""
        conn = sqlite3.connect(self.db_path)
        self._init_db(conn)
        conn.close()

        self.shutdown_event.clear()
        self.worker_thread = threading.Thread(target=self._flusher_loop, daemon=True)
        self.worker_thread.start()

    def stop(self):
        """Signals flusher thread to drain and cleanly exit."""
        self.shutdown_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2.0)

    def enqueue_log(self, j1: int, j2: int, j3: int, status: str, ack: str, cmd_type: str):
        record = (time.time(), int(j1), int(j2), int(j3), str(status), str(ack), str(cmd_type))
        try:
            self.log_queue.put_nowait(record)
        except queue.Full:
            pass  # Drop oldest or shed load to protect real-time timing

    def _flusher_loop(self):
        conn = sqlite3.connect(self.db_path)
        last_flush = time.time()
        batch = []

        while not self.shutdown_event.is_set() or not self.log_queue.empty():
            try:
                item = self.log_queue.get(timeout=0.1)
                batch.append(item)
            except queue.Empty:
                pass

            now = time.time()
            if (len(batch) >= self.batch_size) or (batch and (now - last_flush) >= self.flush_interval_sec) or (self.shutdown_event.is_set() and batch):
                cursor = conn.cursor()
                cursor.executemany("""
                    INSERT INTO telemetry_logs (timestamp, joint_1, joint_2, joint_3, validation_status, hardware_ack, command_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, batch)
                conn.commit()
                batch.clear()
                last_flush = now

        conn.close()

    def fetch_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, joint_1, joint_2, joint_3, validation_status, hardware_ack, command_type
            FROM telemetry_logs
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "timestamp": r[0],
                "joint_1": r[1],
                "joint_2": r[2],
                "joint_3": r[3],
                "validation_status": r[4],
                "hardware_ack": r[5],
                "command_type": r[6],
            }
            for r in rows
        ]