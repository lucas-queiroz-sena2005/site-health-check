import asyncio
import logging
import signal
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from typing import Any

from fastapi.sse import ServerSentEvent

logger = logging.getLogger(__name__)


class RunManager:
    """Centralized service managing scan run subprocess lifecycles, abort coordination,

    bounded log buffering, and SSE distribution.
    """

    def __init__(self, log_buffer_maxlen: int = 1000, subscriber_queue_maxsize: int = 100):
        self._log_buffer_maxlen = log_buffer_maxlen
        self._subscriber_queue_maxsize = subscriber_queue_maxsize
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._log_buffers: dict[str, deque[ServerSentEvent]] = defaultdict(
            lambda: deque(maxlen=self._log_buffer_maxlen)
        )
        self._subscribers: dict[str, list[asyncio.Queue[ServerSentEvent | None]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def is_active(self, run_id: str) -> bool:
        """Returns True if the run currently has an active OS subprocess."""
        process = self._processes.get(run_id)
        return process is not None and process.returncode is None

    def register_process(self, run_id: str, process: asyncio.subprocess.Process) -> None:
        """Registers an active subprocess for a scan run."""
        self._processes[run_id] = process

    def unregister_process(self, run_id: str) -> asyncio.subprocess.Process | None:
        """Removes and returns the subprocess handle for a scan run."""
        return self._processes.pop(run_id, None)

    def abort_run(self, run_id: str, grace_seconds: float = 10.0) -> bool:
        """Sends SIGTERM to the active subprocess for run_id and schedules force-kill

        fallback if it fails to terminate within grace_seconds.
        Returns True if a running process was signaled, False otherwise.
        """
        process = self._processes.get(run_id)
        if not process or process.returncode is not None:
            return False

        try:
            process.send_signal(signal.SIGTERM)

            async def force_kill():
                await asyncio.sleep(grace_seconds)
                if process.returncode is None:
                    try:
                        process.kill()
                    except OSError:
                        pass

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(force_kill())
            except RuntimeError:
                pass

            return True
        except ProcessLookupError:
            self._processes.pop(run_id, None)
            return False

    def publish_log(self, run_id: str, event: ServerSentEvent) -> None:
        """Appends event to the bounded ring-buffer and broadcasts to all active subscriber queues."""
        self._log_buffers[run_id].append(event)

        subscribers = list(self._subscribers.get(run_id, []))
        for q in subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full for run %s; dropping event for slow consumer", run_id)

    def broadcast_sentinel(self, run_id: str) -> None:
        """Signals stream termination to all active subscribers for run_id."""
        subscribers = list(self._subscribers.get(run_id, []))
        for q in subscribers:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def get_buffered_logs(self, run_id: str) -> list[ServerSentEvent]:
        """Returns a list of buffered log events for run_id."""
        if run_id not in self._log_buffers:
            return []
        return list(self._log_buffers[run_id])

    def subscriber_count(self, run_id: str) -> int:
        """Returns the number of active SSE subscribers for run_id."""
        return len(self._subscribers.get(run_id, []))

    async def subscribe_logs(self, run_id: str) -> AsyncGenerator[ServerSentEvent, None]:
        """Subscribes to log events for run_id: first yields an initial attachment info event,

        replays historical events from buffer, then streams live events.
        Automatically unsubscribes on generator termination or client disconnect.
        """
        queue: asyncio.Queue[ServerSentEvent | None] = asyncio.Queue(maxsize=self._subscriber_queue_maxsize)
        self._subscribers[run_id].append(queue)

        try:
            yield ServerSentEvent(data={"message": f"Attached to run {run_id} log stream"}, event="info")

            # Replay historical logs
            historical = self.get_buffered_logs(run_id)
            for event in historical:
                yield event

            # Stream live logs
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            subs = self._subscribers.get(run_id, [])
            if queue in subs:
                subs.remove(queue)
            if not subs and run_id in self._subscribers:
                del self._subscribers[run_id]

    def cleanup_run(self, run_id: str) -> None:
        """Evicts subprocess, buffers, and subscriber queues for a completed run."""
        self._processes.pop(run_id, None)
        self._log_buffers.pop(run_id, None)
        self._subscribers.pop(run_id, None)

    async def shutdown(self) -> None:
        """Gracefully terminates all active subprocesses on application shutdown."""
        active_processes = list(self._processes.values())
        for proc in active_processes:
            if proc.returncode is None:
                try:
                    proc.send_signal(signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    pass

        # Give processes up to 2 seconds to exit cleanly
        for _ in range(20):
            if all(p.returncode is not None for p in active_processes):
                break
            await asyncio.sleep(0.1)

        # Force kill any lingering processes
        for proc in active_processes:
            if proc.returncode is None:
                try:
                    proc.kill()
                except (ProcessLookupError, OSError):
                    pass

        self._processes.clear()
        self._log_buffers.clear()
        self._subscribers.clear()
