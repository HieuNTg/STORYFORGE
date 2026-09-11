"""BatchCheckpointManager - Quản lý checkpoint batch cho Phase 1.

Mục tiêu:
- Giảm checkpoint overhead bằng cách gộp nhiều operations
- Chạy checkpoint ở background để không blocking pipeline
- Tự động prune các checkpoint cũ để tiết kiệm disk space
- Hỗ trợ async checkpointing cho hiệu năng cao
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CheckpointRequest:
    """Yêu cầu checkpoint cần được xử lý."""
    checkpoint_id: str
    data: dict
    path: str
    priority: int = 0  # 0 = normal, 1 = high, 2 = critical
    timestamp: float = 0.0
    retry_count: int = 0
    max_retries: int = 3
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class BatchCheckpointManager:
    """Quản lý checkpoint với batching và async processing.
    
    Usage:
        manager = BatchCheckpointManager(max_batch_size=5, flush_interval=2.0)
        
        # Queue checkpoints (non-blocking)
        manager.queue_checkpoint("layer1", output_data, priority=1)
        manager.queue_checkpoint("chapter_5", chapter_data, priority=0)
        
        # Start background processor
        await manager.start_processor()
        
        # Get metrics
        metrics = manager.get_metrics()
        
        # Graceful shutdown
        await manager.shutdown()
    """
    
    def __init__(
        self,
        max_batch_size: int = 5,
        flush_interval: float = 2.0,
        max_queue_size: int = 100,
        max_workers: int = 3,
        auto_prune: bool = True,
        keep_last_per_type: int = 5,
    ):
        self.max_batch_size = max_batch_size
        self.flush_interval = flush_interval
        self.max_queue_size = max_queue_size
        self.max_workers = max_workers
        self.auto_prune = auto_prune
        self.keep_last_per_type = keep_last_per_type
        
        # Queue for checkpoint requests
        self._queue: deque[CheckpointRequest] = deque(maxlen=max_queue_size)
        self._queue_lock = threading.Lock()
        
        # Processing state
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self._current_batch: List[CheckpointRequest] = []
        self._batch_lock = threading.Lock()
        
        # Metrics tracking
        self.metrics = {
            "queued": 0,
            "processed": 0,
            "failed": 0,
            "batches_flushed": 0,
            "total_write_time_ms": 0.0,
            "avg_write_time_ms": 0.0,
            "queue_drops": 0,
            "retries": 0,
        }
        self._metrics_lock = threading.Lock()
        
        # Track recent checkpoints per type for pruning
        self._recent_checkpoints: Dict[str, List[Tuple[str, float]]] = {}  # type -> [(path, timestamp)]
        self._recent_lock = threading.Lock()
        
        # Event loop for async operations
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        logger.info(
            f"[BATCH_CHECKPOINT] Initialized with batch_size={max_batch_size}, "
            f"flush_interval={flush_interval}s, max_workers={max_workers}"
        )
    
    def queue_checkpoint(
        self,
        checkpoint_type: str,
        data: dict,
        priority: int = 0,
        metadata: Optional[dict] = None,
    ) -> str:
        """Queue một checkpoint để xử lý sau (non-blocking).
        
        Args:
            checkpoint_type: Loại checkpoint (e.g., "layer1", "chapter_5")
            data: Dữ liệu cần lưu
            priority: Mức độ ưu tiên (0=normal, 1=high, 2=critical)
            metadata: Metadata bổ sung
            
        Returns:
            checkpoint_id: ID của checkpoint
        """
        # Generate checkpoint ID
        timestamp = time.time()
        hash_input = f"{checkpoint_type}:{timestamp}:{id(data)}"
        checkpoint_id = hashlib.md5(hash_input.encode()).hexdigest()[:12]
        
        # Generate file path
        safe_type = re.sub(r'[^\\w\\-]', '_', checkpoint_type)[:30]
        filename = f"checkpoint_{safe_type}_{checkpoint_id}.json"
        
        # Use existing checkpoint directory structure
        from services.output_paths import OUTPUT_ROOT
        checkpoint_dir = os.path.join(OUTPUT_ROOT, "checkpoints", "batch")
        os.makedirs(checkpoint_dir, exist_ok=True)
        
        path = os.path.join(checkpoint_dir, filename)
        
        # Create request
        request = CheckpointRequest(
            checkpoint_id=checkpoint_id,
            data={
                "type": checkpoint_type,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata or {},
                **data,
            },
            path=path,
            priority=priority,
            timestamp=timestamp,
        )
        
        # Add to queue
        with self._queue_lock:
            if len(self._queue) >= self.max_queue_size:
                # Queue full - drop lowest priority item
                dropped = self._drop_lowest_priority()
                self.metrics["queue_drops"] += 1
                logger.warning(
                    f"[BATCH_CHECKPOINT] Queue full, dropped checkpoint: {dropped.checkpoint_id}"
                )
            
            # Insert by priority (simple approach: append and sort later)
            self._queue.append(request)
            self.metrics["queued"] += 1
        
        logger.debug(
            f"[BATCH_CHECKPOINT] Queued {checkpoint_type} (priority={priority}, id={checkpoint_id})"
        )
        return checkpoint_id
    
    def _drop_lowest_priority(self) -> CheckpointRequest:
        """Drop checkpoint có priority thấp nhất khỏi queue."""
        if not self._queue:
            return None
        
        # Find lowest priority (oldest if tie)
        min_priority = min(req.priority for req in self._queue)
        for i, req in enumerate(self._queue):
            if req.priority == min_priority:
                return self._queue[i]
        
        return self._queue[0]
    
    async def start_processor(self) -> None:
        """Start background processor task."""
        if self._running:
            logger.warning("[BATCH_CHECKPOINT] Processor already running")
            return
        
        self._running = True
        self._loop = asyncio.get_event_loop()
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info("[BATCH_CHECKPOINT] Background processor started")
    
    async def stop_processor(self) -> None:
        """Stop background processor gracefully."""
        self._running = False
        
        if self._processor_task:
            # Wait for current batch to complete
            try:
                await asyncio.wait_for(self._processor_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("[BATCH_CHECKPOINT] Processor shutdown timeout")
                self._processor_task.cancel()
        
        logger.info("[BATCH_CHECKPOINT] Background processor stopped")
    
    async def _process_loop(self) -> None:
        """Main processing loop - runs in background."""
        last_flush_time = time.time()
        
        while self._running:
            try:
                # Check if we should flush
                should_flush = False
                
                with self._queue_lock:
                    # Flush if batch is full
                    if len(self._queue) >= self.max_batch_size:
                        should_flush = True
                    # Or if interval has passed and queue not empty
                    elif self._queue and (time.time() - last_flush_time) >= self.flush_interval:
                        should_flush = True
                
                if should_flush:
                    await self._flush_batch()
                    last_flush_time = time.time()
                
                # Small sleep to prevent busy-waiting
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BATCH_CHECKPOINT] Process loop error: {e}")
                await asyncio.sleep(1.0)
        
        # Final flush on shutdown
        if self._queue:
            logger.info("[BATCH_CHECKPOINT] Flushing remaining checkpoints on shutdown")
            await self._flush_batch()
    
    async def _flush_batch(self) -> None:
        """Flush current batch to disk."""
        with self._queue_lock:
            # Get items up to max_batch_size, sorted by priority
            batch = []
            while self._queue and len(batch) < self.max_batch_size:
                # Simple priority: higher priority first
                batch.append(self._queue.popleft())
            
            # Sort by priority (descending) then timestamp (ascending)
            batch.sort(key=lambda r: (-r.priority, r.timestamp))
        
        if not batch:
            return
        
        # Process batch concurrently with bounded concurrency
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def write_with_semaphore(request: CheckpointRequest):
            async with semaphore:
                await self._write_checkpoint(request)
        
        tasks = [write_with_semaphore(req) for req in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Track successes and failures
        successful = []
        failed = []
        
        for req, result in zip(batch, results):
            if isinstance(result, Exception):
                failed.append((req, result))
                # Retry logic
                if req.retry_count < req.max_retries:
                    req.retry_count += 1
                    with self._queue_lock:
                        self._queue.appendleft(req)  # Re-queue for retry
                    self.metrics["retries"] += 1
                    logger.warning(
                        f"[BATCH_CHECKPOINT] Retrying {req.checkpoint_id} "
                        f"(attempt {req.retry_count}/{req.max_retries})"
                    )
            else:
                successful.append(req)
        
        # Update metrics
        with self._metrics_lock:
            self.metrics["processed"] += len(successful)
            self.metrics["failed"] += len(failed)
            self.metrics["batches_flushed"] += 1
        
        # Auto-prune old checkpoints
        if self.auto_prune and successful:
            await self._prune_old_checkpoints()
        
        logger.info(
            f"[BATCH_CHECKPOINT] Flushed batch: {len(successful)} succeeded, "
            f"{len(failed)} failed"
        )
    
    async def _write_checkpoint(self, request: CheckpointRequest) -> bool:
        """Write single checkpoint to disk."""
        start_time = time.time()
        
        try:
            # Serialize data
            data_json = json.dumps(request.data, indent=2, default=str)
            
            # Write atomically (write to temp, then rename)
            temp_path = request.path + ".tmp"
            
            # Run disk I/O in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._atomic_write,
                temp_path,
                request.path,
                data_json,
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Update metrics
            with self._metrics_lock:
                total_time = self.metrics["total_write_time_ms"]
                count = self.metrics["processed"] + 1
                self.metrics["total_write_time_ms"] = total_time + elapsed_ms
                self.metrics["avg_write_time_ms"] = (total_time + elapsed_ms) / count
            
            # Track for pruning
            checkpoint_type = request.data.get("type", "unknown")
            with self._recent_lock:
                if checkpoint_type not in self._recent_checkpoints:
                    self._recent_checkpoints[checkpoint_type] = []
                self._recent_checkpoints[checkpoint_type].append((request.path, time.time()))
            
            logger.debug(
                f"[BATCH_CHECKPOINT] Wrote {request.checkpoint_id} in {elapsed_ms:.1f}ms"
            )
            return True
            
        except Exception as e:
            logger.error(
                f"[BATCH_CHECKPOINT] Failed to write {request.checkpoint_id}: {e}"
            )
            raise
    
    def _atomic_write(self, temp_path: str, final_path: str, data: str) -> None:
        """Atomic write: write to temp file, then rename."""
        try:
            # Write to temp file
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            
            # Atomic rename
            os.rename(temp_path, final_path)
            
        except Exception:
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
    
    async def _prune_old_checkpoints(self) -> None:
        """Prune old checkpoints beyond keep_last_per_type."""
        with self._recent_lock:
            for checkpoint_type, checkpoints in self._recent_checkpoints.items():
                if len(checkpoints) <= self.keep_last_per_type:
                    continue
                
                # Sort by timestamp (newest first)
                checkpoints.sort(key=lambda x: x[1], reverse=True)
                
                # Remove old ones
                to_remove = checkpoints[self.keep_last_per_type:]
                self._recent_checkpoints[checkpoint_type] = checkpoints[:self.keep_last_per_type]
        
        # Delete files outside lock
        for checkpoint_type, checkpoints in list(self._recent_lock):
            pass  # Already handled above
        
        # Actually delete the files
        for checkpoint_type, old_checkpoints in to_remove if (to_remove := checkpoints[self.keep_last_per_type:]) else []:
            try:
                if os.path.exists(old_checkpoints[0]):
                    os.remove(old_checkpoints[0])
                    logger.debug(
                        f"[BATCH_CHECKPOINT] Pruned old checkpoint: {old_checkpoints[0]}"
                    )
            except Exception as e:
                logger.warning(f"[BATCH_CHECKPOINT] Failed to prune {old_checkpoints[0]}: {e}")
    
    def get_metrics(self) -> dict:
        """Get current metrics."""
        with self._metrics_lock:
            metrics_copy = dict(self.metrics)
        
        with self._queue_lock:
            metrics_copy["queue_size"] = len(self._queue)
        
        with self._recent_lock:
            total_tracked = sum(len(v) for v in self._recent_checkpoints.values())
            metrics_copy["tracked_checkpoints"] = total_tracked
        
        # Calculate derived metrics
        processed = metrics_copy["processed"]
        queued = metrics_copy["queued"]
        metrics_copy["processing_rate"] = (processed / queued * 100) if queued > 0 else 0
        
        failed = metrics_copy["failed"]
        metrics_copy["failure_rate"] = (failed / processed * 100) if processed > 0 else 0
        
        return metrics_copy
    
    async def wait_for_queue_empty(self, timeout: float = 30.0) -> bool:
        """Wait for queue to be empty (for graceful shutdown)."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self._queue_lock:
                if not self._queue:
                    return True
            await asyncio.sleep(0.2)
        
        return False
    
    def force_checkpoint(self, checkpoint_type: str, data: dict) -> str:
        """Force immediate checkpoint write (blocking, for critical saves).
        
        Use sparingly - only for critical checkpoints that must be saved immediately.
        """
        checkpoint_id = self.queue_checkpoint(checkpoint_type, data, priority=2)
        
        # Write immediately in blocking mode
        request = CheckpointRequest(
            checkpoint_id=checkpoint_id,
            data=data,
            path=self._get_path_for_id(checkpoint_id),
            priority=2,
            timestamp=time.time(),
        )
        
        try:
            asyncio.get_event_loop().run_until_complete(self._write_checkpoint(request))
            logger.info(f"[BATCH_CHECKPOINT] Force-wrote {checkpoint_id}")
        except Exception as e:
            logger.error(f"[BATCH_CHECKPOINT] Force-write failed: {e}")
            raise
        
        return checkpoint_id
    
    def _get_path_for_id(self, checkpoint_id: str) -> str:
        """Generate path for a checkpoint ID."""
        from services.output_paths import OUTPUT_ROOT
        checkpoint_dir = os.path.join(OUTPUT_ROOT, "checkpoints", "batch")
        return os.path.join(checkpoint_dir, f"checkpoint_{checkpoint_id}.json")


# Global instance (optional)
_global_batch_manager: Optional[BatchCheckpointManager] = None
_global_batch_lock = threading.Lock()


def get_batch_checkpoint_manager() -> BatchCheckpointManager:
    """Get global batch checkpoint manager singleton."""
    global _global_batch_manager
    if _global_batch_manager is None:
        with _global_batch_lock:
            if _global_batch_manager is None:
                _global_batch_manager = BatchCheckpointManager()
    return _global_batch_manager


async def initialize_batch_manager(**kwargs) -> BatchCheckpointManager:
    """Initialize and start global batch manager."""
    manager = get_batch_checkpoint_manager()
    
    # Reinitialize with custom settings if provided
    if kwargs:
        manager.__init__(**kwargs)
    
    await manager.start_processor()
    return manager


async def shutdown_batch_manager() -> None:
    """Shutdown global batch manager gracefully."""
    global _global_batch_manager
    if _global_batch_manager:
        await _global_batch_manager.stop_processor()
        # Optionally clear singleton
        # _global_batch_manager = None
