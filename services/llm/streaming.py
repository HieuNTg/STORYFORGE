"""Streaming mixin — per-chunk timeout and retry-aware streaming utilities."""

import logging
import threading

from services.llm.retry import MAX_RETRIES, BASE_DELAY, _is_transient, _redact

logger = logging.getLogger(__name__)


class StreamingMixin:
    """Mixin that adds streaming retry + chunk-timeout capabilities to LLMClient."""

    def _stream_with_retry(self, gen_factory, label: str = "stream"):
        """Retry wrapper for streaming generators.

        Only retries if no chunks were yielded yet (prevents duplicate output
        when failure occurs mid-stream).
        """
        import random
        import time

        last_exc = None
        chunks_yielded = 0
        for attempt in range(MAX_RETRIES):
            try:
                for chunk in gen_factory():
                    chunks_yielded += 1
                    yield chunk
                return
            except Exception as e:
                last_exc = e
                if chunks_yielded > 0:
                    # Mid-stream failure — cannot safely retry without duplication
                    logger.error(f"{label} failed after {chunks_yielded} chunks: {_redact(e)}")
                    raise
                if attempt < MAX_RETRIES - 1 and _is_transient(e):
                    delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(f"{label} attempt {attempt+1} failed: {_redact(e)}. Retry in {delay:.1f}s")
                    time.sleep(delay)
                    continue
                break
        logger.error(f"{label} failed after {MAX_RETRIES} attempts: {_redact(last_exc)}")
        raise last_exc

    def _stream_with_chunk_timeout(
        self,
        source_gen,
        chunk_timeout: int = 30,
        first_chunk_timeout: int = 60,
    ):
        """Wrap a streaming generator with per-chunk timeouts.

        Uses a longer timeout for the first chunk (TTFT includes model load)
        and a shorter timeout for subsequent chunks (stall detection).
        """
        import queue as _queue

        _SENTINEL = object()
        chunk_queue: _queue.Queue = _queue.Queue()

        def _producer():
            try:
                for chunk in source_gen:
                    chunk_queue.put(chunk)
            except Exception as exc:
                chunk_queue.put(exc)
            finally:
                chunk_queue.put(_SENTINEL)

        producer_thread = threading.Thread(target=_producer, daemon=True)
        producer_thread.start()

        got_first = False
        while True:
            timeout = first_chunk_timeout if not got_first else chunk_timeout
            try:
                item = chunk_queue.get(timeout=timeout)
            except _queue.Empty:
                phase = "first chunk" if not got_first else "inter-chunk"
                logger.error(
                    f"Stream {phase} timeout: no data received in {timeout}s"
                )
                raise TimeoutError(
                    f"Streaming response stalled — no {phase} data within {timeout}s"
                )
            if item is _SENTINEL:
                return
            if isinstance(item, Exception):
                raise item
            got_first = True
            yield item
