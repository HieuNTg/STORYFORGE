"""MediaJobQueue - Background job queue cho media production (Phase 2).

Mục tiêu:
- Tách media production ra khỏi main pipeline
- Trả kết quả text ngay lập tức (TTFB < 1s)
- Xử lý ảnh/audio/video ở background worker
- Hỗ trợ priority queue và retry logic
- Cung cấp webhook/SSE notification khi hoàn thành
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import uuid

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Trạng thái của media job."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    """Loại media job."""
    CHARACTER_IMAGE = "character_image"
    SCENE_IMAGE = "scene_image"
    AUDIO_NARRATION = "audio_narration"
    VIDEO_TRAILER = "video_trailer"
    COMIC_PANEL = "comic_panel"


@dataclass
class MediaJob:
    """Đại diện cho một media job trong queue."""
    job_id: str
    job_type: JobType
    status: JobStatus = JobStatus.PENDING
    priority: int = 0  # 0 = low, 1 = normal, 2 = high, 3 = critical
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Input data
    input_data: dict = field(default_factory=dict)
    
    # Output
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    
    # Retry logic
    retry_count: int = 0
    max_retries: int = 3
    
    # Callbacks
    webhook_url: Optional[str] = None
    session_id: Optional[str] = None
    story_id: Optional[str] = None
    chapter_number: Optional[int] = None
    
    # Metadata
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "input_data": self.input_data,
            "output_path": self.output_path,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "story_id": self.story_id,
            "chapter_number": self.chapter_number,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MediaJob':
        return cls(
            job_id=data["job_id"],
            job_type=JobType(data["job_type"]),
            status=JobStatus(data["status"]),
            priority=data.get("priority", 0),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            input_data=data.get("input_data", {}),
            output_path=data.get("output_path"),
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
            metadata=data.get("metadata", {}),
            session_id=data.get("session_id"),
            story_id=data.get("story_id"),
            chapter_number=data.get("chapter_number"),
        )


@dataclass
class JobResult:
    """Kết quả xử lý job."""
    job_id: str
    success: bool
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


class MediaJobQueue:
    """Queue quản lý media jobs ở background.
    
    Usage:
        queue = MediaJobQueue(max_workers=4)
        
        # Start background processor
        await queue.start()
        
        # Submit job (non-blocking)
        job_id = queue.submit_job(
            job_type=JobType.CHARACTER_IMAGE,
            input_data={"character_name": "Alice", "description": "..."},
            priority=1,
            session_id="session_123",
        )
        
        # Check status
        status = queue.get_job_status(job_id)
        
        # Wait for completion
        result = await queue.wait_for_job(job_id, timeout=60.0)
        
        # Graceful shutdown
        await queue.shutdown()
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        max_queue_size: int = 1000,
        default_timeout: float = 300.0,  # 5 minutes
        enable_retry: bool = True,
        persistence_dir: Optional[str] = None,
    ):
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.default_timeout = default_timeout
        self.enable_retry = enable_retry
        self.persistence_dir = persistence_dir
        
        # Priority queues (higher priority = processed first)
        self._queues: Dict[int, deque[MediaJob]] = {
            3: deque(),  # Critical
            2: deque(),  # High
            1: deque(),  # Normal
            0: deque(),  # Low
        }
        self._queue_lock = threading.Lock()
        self._job_registry: Dict[str, MediaJob] = {}
        self._registry_lock = threading.Lock()
        
        # Processing state
        self._running = False
        self._worker_tasks: List[asyncio.Task] = []
        self._semaphore: Optional[asyncio.Semaphore] = None
        
        # Completion callbacks
        self._completion_handlers: List[Callable[[JobResult], None]] = []
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # Metrics
        self.metrics = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "retried": 0,
            "total_processing_time_ms": 0.0,
            "avg_processing_time_ms": 0.0,
        }
        self._metrics_lock = threading.Lock()
        
        # Persistence
        if persistence_dir:
            os.makedirs(persistence_dir, exist_ok=True)
            self._load_persistent_jobs()
        
        logger.info(
            f"[MEDIA_QUEUE] Initialized with workers={max_workers}, "
            f"max_queue={max_queue_size}, persistence={persistence_dir}"
        )
    
    def submit_job(
        self,
        job_type: JobType,
        input_data: dict,
        priority: int = 1,
        session_id: Optional[str] = None,
        story_id: Optional[str] = None,
        chapter_number: Optional[int] = None,
        webhook_url: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Submit media job vào queue (non-blocking).
        
        Returns ngay lập tức với job_id để track progress.
        """
        job_id = f"{job_type.value}_{uuid.uuid4().hex[:8]}"
        
        job = MediaJob(
            job_id=job_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            priority=min(priority, 3),  # Cap at 3
            input_data=input_data,
            session_id=session_id,
            story_id=story_id,
            chapter_number=chapter_number,
            webhook_url=webhook_url,
            metadata=metadata or {},
        )
        
        with self._queue_lock:
            # Check queue capacity
            total_queued = sum(len(q) for q in self._queues.values())
            if total_queued >= self.max_queue_size:
                logger.warning(f"[MEDIA_QUEUE] Queue full, rejecting job {job_id}")
                raise RuntimeError("Media job queue is full")
            
            # Add to appropriate priority queue
            self._queues[job.priority].append(job)
            
            # Register job
            with self._registry_lock:
                self._job_registry[job_id] = job
            
            # Update metrics
            with self._metrics_lock:
                self.metrics["submitted"] += 1
        
        logger.debug(
            f"[MEDIA_QUEUE] Submitted job {job_id} (type={job_type.value}, priority={priority})"
        )
        return job_id
    
    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Lấy trạng thái hiện tại của job."""
        with self._registry_lock:
            job = self._job_registry.get(job_id)
            if not job:
                return None
            
            return {
                "job_id": job.job_id,
                "status": job.status.value,
                "job_type": job.job_type.value,
                "priority": job.priority,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "output_path": job.output_path,
                "error_message": job.error_message,
                "retry_count": job.retry_count,
                "estimated_wait_seconds": self._estimate_wait_time(job.priority),
            }
    
    async def wait_for_job(
        self,
        job_id: str,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0,
    ) -> Optional[JobResult]:
        """Wait for job completion (async)."""
        timeout = timeout or self.default_timeout
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_job_status(job_id)
            if not status:
                raise ValueError(f"Job {job_id} not found")
            
            if status["status"] == JobStatus.COMPLETED.value:
                return JobResult(
                    job_id=job_id,
                    success=True,
                    output_path=status.get("output_path"),
                    processing_time_ms=(
                        (status["completed_at"] - status["started_at"]) * 1000
                        if status.get("started_at") and status.get("completed_at")
                        else 0
                    ),
                )
            elif status["status"] == JobStatus.FAILED.value:
                return JobResult(
                    job_id=job_id,
                    success=False,
                    error_message=status.get("error_message"),
                )
            elif status["status"] == JobStatus.CANCELLED.value:
                return JobResult(
                    job_id=job_id,
                    success=False,
                    error_message="Job was cancelled",
                )
            
            await asyncio.sleep(poll_interval)
        
        raise asyncio.TimeoutError(f"Job {job_id} timed out after {timeout}s")
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel pending/queued job."""
        with self._queue_lock:
            for priority, queue in self._queues.items():
                for i, job in enumerate(queue):
                    if job.job_id == job_id:
                        if job.status in [JobStatus.PENDING, JobStatus.QUEUED]:
                            queue.remove(job)
                            job.status = JobStatus.CANCELLED
                            with self._metrics_lock:
                                self.metrics["cancelled"] += 1
                            logger.info(f"[MEDIA_QUEUE] Cancelled job {job_id}")
                            return True
                        else:
                            logger.warning(
                                f"[MEDIA_QUEUE] Cannot cancel job {job_id} "
                                f"(status={job.status.value})"
                            )
                            return False
        
        return False
    
    async def start(self) -> None:
        """Start background workers."""
        if self._running:
            logger.warning("[MEDIA_QUEUE] Already running")
            return
        
        self._running = True
        self._event_loop = asyncio.get_event_loop()
        self._semaphore = asyncio.Semaphore(self.max_workers)
        
        # Start worker tasks
        for i in range(self.max_workers):
            task = asyncio.create_task(self._worker(i))
            self._worker_tasks.append(task)
        
        logger.info(f"[MEDIA_QUEUE] Started {self.max_workers} workers")
    
    async def shutdown(self, wait: bool = True, timeout: float = 10.0) -> None:
        """Shutdown workers gracefully."""
        self._running = False
        
        if wait and self._worker_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._worker_tasks, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("[MEDIA_QUEUE] Shutdown timeout, cancelling workers")
                for task in self._worker_tasks:
                    task.cancel()
        
        logger.info("[MEDIA_QUEUE] Shutdown complete")
    
    async def _worker(self, worker_id: int) -> None:
        """Worker thread xử lý jobs."""
        logger.debug(f"[MEDIA_QUEUE] Worker {worker_id} started")
        
        while self._running:
            try:
                # Get next job from highest priority queue
                job = self._dequeue_job()
                
                if job is None:
                    # No jobs available, wait a bit
                    await asyncio.sleep(0.2)
                    continue
                
                # Process job
                await self._process_job(job, worker_id)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MEDIA_QUEUE] Worker {worker_id} error: {e}")
                await asyncio.sleep(1.0)
        
        logger.debug(f"[MEDIA_QUEUE] Worker {worker_id} stopped")
    
    def _dequeue_job(self) -> Optional[MediaJob]:
        """Dequeue next job (highest priority first)."""
        with self._queue_lock:
            # Check queues in priority order
            for priority in [3, 2, 1, 0]:
                if self._queues[priority]:
                    job = self._queues[priority].popleft()
                    job.status = JobStatus.PROCESSING
                    job.started_at = time.time()
                    return job
        return None
    
    async def _process_job(self, job: MediaJob, worker_id: int) -> None:
        """Process single media job."""
        logger.info(
            f"[MEDIA_QUEUE] Worker {worker_id} processing {job.job_id} "
            f"(type={job.job_type.value})"
        )
        
        start_time = time.time()
        result = None
        
        try:
            # Dispatch to appropriate handler based on job type
            if job.job_type == JobType.CHARACTER_IMAGE:
                result = await self._process_character_image(job)
            elif job.job_type == JobType.SCENE_IMAGE:
                result = await self._process_scene_image(job)
            elif job.job_type == JobType.AUDIO_NARRATION:
                result = await self._process_audio_narration(job)
            elif job.job_type == JobType.VIDEO_TRAILER:
                result = await self._process_video_trailer(job)
            elif job.job_type == JobType.COMIC_PANEL:
                result = await self._process_comic_panel(job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")
            
            # Mark as completed
            job.status = JobStatus.COMPLETED
            job.completed_at = time.time()
            job.output_path = result.output_path if result else None
            
            with self._metrics_lock:
                self.metrics["completed"] += 1
                processing_time = (job.completed_at - job.started_at) * 1000
                self.metrics["total_processing_time_ms"] += processing_time
                self.metrics["avg_processing_time_ms"] = (
                    self.metrics["total_processing_time_ms"] / self.metrics["completed"]
                )
            
            logger.info(
                f"[MEDIA_QUEUE] Completed {job.job_id} in {processing_time:.1f}ms"
            )
            
        except Exception as e:
            logger.error(f"[MEDIA_QUEUE] Failed {job.job_id}: {e}")
            
            # Retry logic
            if self.enable_retry and job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = JobStatus.QUEUED
                
                with self._queue_lock:
                    self._queues[job.priority].appendleft(job)
                
                with self._metrics_lock:
                    self.metrics["retried"] += 1
                
                logger.warning(
                    f"[MEDIA_QUEUE] Retrying {job.job_id} "
                    f"(attempt {job.retry_count + 1}/{job.max_retries})"
                )
            else:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                job.completed_at = time.time()
                
                with self._metrics_lock:
                    self.metrics["failed"] += 1
        
        # Notify completion handlers
        if result:
            job_result = JobResult(
                job_id=job.job_id,
                success=job.status == JobStatus.COMPLETED,
                output_path=job.output_path,
                error_message=job.error_message,
                processing_time_ms=(job.completed_at - job.started_at) * 1000 if job.completed_at and job.started_at else 0,
            )
            await self._notify_completion(job_result)
        
        # Send webhook if configured
        if job.webhook_url:
            await self._send_webhook(job)
    
    async def _process_character_image(self, job: MediaJob) -> Optional[JobResult]:
        """Xử lý character image generation."""
        # Placeholder - integrate with actual image generation service
        # In Phase 2, this will call services.media.image_provider
        await asyncio.sleep(0.5)  # Simulate processing
        
        logger.debug(f"[MEDIA] Generating character image: {job.input_data.get('character_name')}")
        
        # TODO: Integrate with ImageProvider
        return JobResult(
            job_id=job.job_id,
            success=True,
            output_path=f"/output/images/characters/{job.job_id}.png",
            metadata={"character_name": job.input_data.get("character_name")},
        )
    
    async def _process_scene_image(self, job: MediaJob) -> Optional[JobResult]:
        """Xử lý scene image generation."""
        await asyncio.sleep(0.5)  # Simulate
        
        logger.debug(f"[MEDIA] Generating scene image: {job.input_data.get('scene_description')}")
        
        return JobResult(
            job_id=job.job_id,
            success=True,
            output_path=f"/output/images/scenes/{job.job_id}.png",
            metadata={"chapter": job.chapter_number},
        )
    
    async def _process_audio_narration(self, job: MediaJob) -> Optional[JobResult]:
        """Xử lý audio narration generation."""
        await asyncio.sleep(1.0)  # Simulate longer processing
        
        logger.debug(f"[MEDIA] Generating audio for chapter {job.chapter_number}")
        
        return JobResult(
            job_id=job.job_id,
            success=True,
            output_path=f"/output/audio/chapter_{job.chapter_number}.mp3",
            metadata={"duration_seconds": 120},
        )
    
    async def _process_video_trailer(self, job: MediaJob) -> Optional[JobResult]:
        """Xử lý video trailer generation."""
        await asyncio.sleep(2.0)  # Simulate even longer processing
        
        logger.debug(f"[MEDIA] Generating video trailer for {job.story_id}")
        
        return JobResult(
            job_id=job.job_id,
            success=True,
            output_path=f"/output/videos/trailer_{job.story_id}.mp4",
            metadata={"duration_seconds": 30},
        )
    
    async def _process_comic_panel(self, job: MediaJob) -> Optional[JobResult]:
        """Xử lý comic panel generation."""
        await asyncio.sleep(0.8)  # Simulate processing
        
        logger.debug(f"[MEDIA] Generating comic panel for chapter {job.chapter_number}")
        
        return JobResult(
            job_id=job.job_id,
            success=True,
            output_path=f"/output/comics/panel_{job.job_id}.png",
            metadata={"panel_index": job.metadata.get("panel_index", 0)},
        )
    
    def _estimate_wait_time(self, priority: int) -> float:
        """Estimate wait time in seconds based on queue depth."""
        with self._queue_lock:
            # Count jobs with higher or equal priority
            jobs_ahead = sum(
                len(self._queues[p]) for p in range(priority, 4)
            )
        
        # Rough estimate: each job takes ~2 seconds on average
        return jobs_ahead * 2.0 / self.max_workers
    
    async def _notify_completion(self, result: JobResult) -> None:
        """Notify registered completion handlers."""
        for handler in self._completion_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(result)
                else:
                    handler(result)
            except Exception as e:
                logger.warning(f"[MEDIA_QUEUE] Completion handler error: {e}")
    
    async def _send_webhook(self, job: MediaJob) -> None:
        """Send webhook notification when job completes."""
        if not job.webhook_url:
            return
        
        payload = {
            "job_id": job.job_id,
            "status": job.status.value,
            "output_path": job.output_path,
            "error_message": job.error_message,
            "completed_at": job.completed_at,
        }
        
        try:
            # In Phase 2, implement actual HTTP POST
            logger.debug(f"[MEDIA_QUEUE] Would send webhook to {job.webhook_url}")
        except Exception as e:
            logger.warning(f"[MEDIA_QUEUE] Webhook failed: {e}")
    
    def register_completion_handler(self, handler: Callable[[JobResult], None]) -> None:
        """Register callback for job completion."""
        self._completion_handlers.append(handler)
    
    def get_metrics(self) -> dict:
        """Get queue metrics."""
        with self._metrics_lock:
            metrics_copy = dict(self.metrics)
        
        with self._queue_lock:
            metrics_copy["queue_depth_by_priority"] = {
                p: len(q) for p, q in self._queues.items()
            }
            metrics_copy["total_queued"] = sum(len(q) for q in self._queues.values())
        
        with self._registry_lock:
            active_jobs = sum(
                1 for j in self._job_registry.values()
                if j.status == JobStatus.PROCESSING
            )
            metrics_copy["active_jobs"] = active_jobs
        
        return metrics_copy
    
    def _save_persistent_job(self, job: MediaJob) -> None:
        """Save job to disk for persistence."""
        if not self.persistence_dir:
            return
        
        path = os.path.join(self.persistence_dir, f"{job.job_id}.json")
        try:
            with open(path, 'w') as f:
                json.dump(job.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"[MEDIA_QUEUE] Failed to persist job {job.job_id}: {e}")
    
    def _load_persistent_jobs(self) -> None:
        """Reload persistent jobs from disk."""
        if not self.persistence_dir:
            return
        
        try:
            for filename in os.listdir(self.persistence_dir):
                if filename.endswith('.json'):
                    path = os.path.join(self.persistence_dir, filename)
                    with open(path, 'r') as f:
                        data = json.load(f)
                        job = MediaJob.from_dict(data)
                        
                        # Only reload queued/pending jobs
                        if job.status in [JobStatus.QUEUED, JobStatus.PENDING]:
                            with self._queue_lock:
                                self._queues[job.priority].append(job)
                            with self._registry_lock:
                                self._job_registry[job.job_id] = job
        except Exception as e:
            logger.warning(f"[MEDIA_QUEUE] Failed to load persistent jobs: {e}")


# Global instance (optional)
_global_media_queue: Optional[MediaJobQueue] = None
_global_queue_lock = threading.Lock()


def get_media_queue() -> MediaJobQueue:
    """Get global media queue singleton."""
    global _global_media_queue
    if _global_media_queue is None:
        with _global_queue_lock:
            if _global_media_queue is None:
                _global_media_queue = MediaJobQueue()
    return _global_media_queue


async def initialize_media_queue(**kwargs) -> MediaJobQueue:
    """Initialize and start global media queue."""
    queue = get_media_queue()
    
    if kwargs:
        queue.__init__(**kwargs)
    
    await queue.start()
    return queue


async def shutdown_media_queue() -> None:
    """Shutdown global media queue."""
    global _global_media_queue
    if _global_media_queue:
        await _global_media_queue.shutdown()
