import os
import time
import gzip
import logging
from datetime import datetime, timezone
from typing import List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from sqlmodel import Session, select

from src.database_manager import get_engine
from src.models import TelemetryIngressQueue

# Configure module logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloud_sync")

class CloudSyncWorker:
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region_name: str = "us-east-1",
        batch_size_threshold: int = 50,
        batch_time_threshold_sec: float = 30.0,
        max_consecutive_failures: int = 3,
        circuit_cooldown_sec: float = 60.0
    ):
        self.bucket_name = bucket_name or os.getenv("BUCKET_NAME")
        if not self.bucket_name:
            raise ValueError("BUCKET_NAME environment variable or parameter must be provided.")
        
        self.batch_size_threshold = batch_size_threshold
        self.batch_time_threshold_sec = batch_time_threshold_sec
        self.max_consecutive_failures = max_consecutive_failures
        self.circuit_cooldown_sec = circuit_cooldown_sec

        self.last_flush_time = time.time()
        self.consecutive_failures = 0
        self.circuit_open_until = 0.0

        # Hard socket timeouts to prevent thread hanging on network drops
        s3_config = Config(
            connect_timeout=5,
            read_timeout=10,
            retries={'max_attempts': 3, 'mode': 'standard'}
        )
        self.s3_client = boto3.client("s3", region_name=region_name, config=s3_config)
        self.engine = get_engine()

    def boot_stale_record_sweep(self) -> int:
        """Resets orphaned 'PROCESSING' records back to 'PENDING' on daemon reboot."""
        with Session(self.engine) as session:
            statement = select(TelemetryIngressQueue).where(TelemetryIngressQueue.sync_status == "PROCESSING")
            orphaned = session.exec(statement).all()
            if orphaned:
                for record in orphaned:
                    record.sync_status = "PENDING"
                session.commit()
                logger.info(f"Re-queued {len(orphaned)} orphaned 'PROCESSING' records to 'PENDING'.")
                return len(orphaned)
            return 0

    def query_pending_batch(self, session: Session) -> List[TelemetryIngressQueue]:
        """Locks a batch by advancing status from PENDING to PROCESSING atomically."""
        statement = (
            select(TelemetryIngressQueue)
            .where(TelemetryIngressQueue.sync_status == "PENDING")
            .order_by(TelemetryIngressQueue.record_id.asc())
            .limit(self.batch_size_threshold)
        )
        records = session.exec(statement).all()
        if records:
            for r in records:
                r.sync_status = "PROCESSING"
            session.commit()
            for r in records:
                session.refresh(r)
        return records

    def assemble_gzip_chunk(self, records: List[TelemetryIngressQueue]) -> bytes:
        """Combines binary Protobuf blobs with framing length and compresses via GZIP."""
        raw_buffer = bytearray()
        for r in records:
            blob = r.left_arm_protobuf_blob or b""
            # 4-byte big-endian framing length header
            raw_buffer.extend(len(blob).to_bytes(4, byteorder="big"))
            raw_buffer.extend(blob)
        return gzip.compress(bytes(raw_buffer), compresslevel=9)

    def upload_chunk_to_s3(self, compressed_data: bytes, chunk_key: str) -> bool:
        """Transmits payload via S3 PutObject primitive with timeout protections."""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=chunk_key,
                Body=compressed_data,
                ContentType="application/x-protobuf",
                ContentEncoding="gzip"
            )
            return True
        except (ClientError, BotoCoreError) as e:
            logger.error(f"S3 PutObject failed for key {chunk_key}: {e}")
            return False

    def sync_cycle(self) -> int:
        """Executes a single evaluation pass of the hybrid batching state machine."""
        now = time.time()
        
        # Check Circuit Breaker
        if now < self.circuit_open_until:
            logger.warning(f"Circuit Breaker ACTIVE. Cooling down for {int(self.circuit_open_until - now)}s...")
            return 0

        with Session(self.engine) as session:
            # Count pending records
            count_stmt = select(TelemetryIngressQueue).where(TelemetryIngressQueue.sync_status == "PENDING")
            pending_count = len(session.exec(count_stmt).all())
            
            elapsed = now - self.last_flush_time
            size_trigger = pending_count >= self.batch_size_threshold
            time_trigger = elapsed >= self.batch_time_threshold_sec and pending_count > 0

            if not (size_trigger or time_trigger):
                return 0

            # Acquire batch and mark as PROCESSING
            records = self.query_pending_batch(session)
            if not records:
                return 0

            # Pack and compress
            compressed_payload = self.assemble_gzip_chunk(records)
            timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            chunk_key = f"telemetry/year={datetime.now(timezone.utc).year}/chunk_{timestamp_str}.pb.gz"

            # Transmit
            success = self.upload_chunk_to_s3(compressed_payload, chunk_key)

            if success:
                # Mark as SYNCED
                for r in records:
                    r.sync_status = "SYNCED"
                session.commit()
                self.consecutive_failures = 0
                self.last_flush_time = time.time()
                logger.info(f"Successfully uploaded {len(records)} records to s3://{self.bucket_name}/{chunk_key}")
                return len(records)
            else:
                # Fail back to PENDING for retry
                for r in records:
                    r.sync_status = "PENDING"
                session.commit()
                self.consecutive_failures += 1
                logger.warning(f"Batch failed. Consecutive failures: {self.consecutive_failures}")
                
                if self.consecutive_failures >= self.max_consecutive_failures:
                    self.circuit_open_until = time.time() + self.circuit_cooldown_sec
                    logger.error(f"Trip threshold hit. Opening circuit breaker for {self.circuit_cooldown_sec}s.")
                return 0