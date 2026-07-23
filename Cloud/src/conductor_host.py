#  Hardened Multi-Threaded Host Orchestrator
import os
import time
import queue
import signal
import logging
import threading
from typing import Dict, Any, Optional

from sqlmodel import Session
from src.database_manager import get_engine, initialize_database
from src.models import TelemetryIngressQueue

# Configure System Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(threadName)s: %(message)s")
logger = logging.getLogger("ConductorHost")

# Environmental & Thread Operational Constants
QUEUE_MAX_SIZE = 100
FLUSH_BATCH_SIZE = 10
PRODUCER_INTERVAL_SEC = 0.05  # 20 Hz tick loop


def validate_arm_telemetry(base: float, shoulder: float, elbow: float) -> bool:
    """Dr. Julian's Gatekeeper: Validates active arm joint boundaries (0.0 to 180.0 deg)."""
    for joint in (base, shoulder, elbow):
        if not isinstance(joint, (int, float)):
            return False
        if not (0.0 <= float(joint) <= 180.0):
            return False
    return True


class ConductorOrchestrator:
    """
    Master Application Control Plane for Option C.
    Manages high-frequency mechatronic ingestion (Thread 1) and out-of-band
    micro-batch database storage flushes (Thread 2) with bounded memory safety.
    """
    def __init__(self, queue_maxsize: int = QUEUE_MAX_SIZE):
        self.telemetry_queue: queue.Queue = queue.Queue(maxsize=queue_maxsize)
        self.shutdown_event = threading.Event()
        
        self.producer_thread: Optional[threading.Thread] = None
        self.flusher_thread: Optional[threading.Thread] = None

    def start(self):
        """Boots database schema and launches asynchronous worker threads."""
        logger.info("⚙️ Initializing ConductorHost Storage Tier & Worker Threads...")
        initialize_database()

        self.producer_thread = threading.Thread(
            target=self._producer_loop,
            name="TelemetryProducerThread",
            daemon=True
        )
        self.flusher_thread = threading.Thread(
            target=self._flusher_loop,
            name="DatabaseFlusherThread",
            daemon=True
        )

        self.producer_thread.start()
        self.flusher_thread.start()
        logger.info("🚀 All ConductorHost worker threads engaged successfully.")

    def stop(self):
        """Jax's Atomic Shutdown: Sets flag and triggers graceful thread join sequence."""
        if self.shutdown_event.is_set():
            return
            
        logger.info("🛑 Stop signal captured. Triggering graceful thread shutdown...")
        self.shutdown_event.set()

        if self.producer_thread and self.producer_thread.is_alive():
            self.producer_thread.join(timeout=2.0)

        if self.flusher_thread and self.flusher_thread.is_alive():
            self.flusher_thread.join(timeout=3.0)

        logger.info("✅ ConductorHost shutdown sequence complete.")

    def _producer_loop(self):
        """
        Thread 1: High-Frequency Mechatronic Kinematics Producer Loop (20 Hz).
        Captures single-arm (left arm) joint telemetry, validates bounds,
        and pushes snapshot dictionaries to the in-memory queue non-blockingly.
        """
        simulated_step = 0
        while not self.shutdown_event.is_set():
            start_time = time.time()
            
            # Simulate active left arm motion coordinates
            left_base = 90.0 + (simulated_step % 45)
            left_shoulder = 45.0
            left_elbow = 120.0
            simulated_step += 1

            if validate_arm_telemetry(left_base, left_shoulder, left_elbow):
                # Construct snapshot payload (right arm intentionally unpopulated/empty bytes)
                snapshot = {
                    "timestamp": time.time(),
                    "system_state": "NOMINAL",
                    "schema_version": 1,
                    # Mock serialized Protobuf bytes matching single-arm specification
                    "left_arm_protobuf_blob": f"L_ARM:{left_base:.1f},{left_shoulder:.1f},{left_elbow:.1f}".encode("utf-8"),
                    "right_arm_protobuf_blob": b"",  # Single-arm option A strategy marker
                    "watchdog_ms": 3000,
                    "sync_status": "PENDING"
                }

                # Non-blocking put with overflow drop policy
                try:
                    self.telemetry_queue.put_nowait(snapshot)
                except queue.Full:
                    logger.warning("⚠️ Telemetry queue FULL (maxsize=100)! Dropping stale frame to prevent latency.")
            else:
                logger.error("❌ Rejected malformed mechatronic telemetry frame at producer boundary!")

            # Maintain deterministic tick rate
            elapsed = time.time() - start_time
            sleep_time = max(0.0, PRODUCER_INTERVAL_SEC - elapsed)
            time.sleep(sleep_time)

    def _flusher_loop(self):
        """
        Thread 2: Out-of-Band Micro-Batch Database Flusher Worker.
        Drains up to FLUSH_BATCH_SIZE queue items and bulk-commits them to SQLite WAL tables.
        """
        engine = get_engine()
        
        while not self.shutdown_event.is_set() or not self.telemetry_queue.empty():
            batch = []
            
            # Collect micro-batch records from the queue
            while len(batch) < FLUSH_BATCH_SIZE:
                try:
                    # Timeout allows checking shutdown_event periodically
                    item = self.telemetry_queue.get(timeout=0.5)
                    batch.append(item)
                    self.telemetry_queue.task_done()
                except queue.Empty:
                    break

            if batch:
                try:
                    with Session(engine) as session:
                        db_records = [TelemetryIngressQueue(**record) for record in batch]
                        session.add_all(db_records)
                        session.commit()
                        logger.info(f"💾 Bulk-committed micro-batch of {len(db_records)} telemetry rows to SQLite WAL storage.")
                except Exception as fatal_db_err:
                    logger.critical(f"❌ Fatal SQLite Write Exception encountered: {fatal_db_err}")
                    # Broadcast shutdown signal on storage failure
                    self.shutdown_event.set()
                    break
