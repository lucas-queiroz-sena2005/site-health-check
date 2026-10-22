import asyncio
import json
import logging
import signal
import sys
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from fastapi.sse import ServerSentEvent
from sqlmodel import Session

from api.database import engine as db_engine
from api.models import ScanRun, ScanRunStatus
from api.services.alerts import evaluate_and_dispatch_alert as check_and_dispatch_alerts
from api.services.runner import _finalize_run, _ingest_stdout

logger = logging.getLogger(__name__)


class RunManager:
    """Centralized service managing scan run subprocess lifecycles, abort coordination,

    bounded log buffering, SSE distribution, and post-finalization alert triggers.
    """

    def __init__(
        self,
        log_buffer_maxlen: int = 1000,
        subscriber_queue_maxsize: int = 100,
        max_retained_runs: int = 100,
    ):
        self._log_buffer_maxlen = log_buffer_maxlen
        self._subscriber_queue_maxsize = subscriber_queue_maxsize
        self._max_retained_runs = max_retained_runs
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
        """Appends event to the bounded ring-buffer and broadcasts to all active subscriber queues
        using a sliding window (evicting the oldest item if a subscriber queue is full).
        """
        self._log_buffers[run_id].append(event)

        subscribers = list(self._subscribers.get(run_id, []))
        for q in subscribers:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def broadcast_sentinel(self, run_id: str) -> None:
        """Signals stream termination to all active subscribers for run_id,
        guaranteeing delivery of the None EOF sentinel even if the queue is full.
        """
        subscribers = list(self._subscribers.get(run_id, []))
        for q in subscribers:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
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

    async def subscribe_logs(self, run_id: str, is_finished: bool = False) -> AsyncGenerator[ServerSentEvent, None]:
        """Subscribes to log events for run_id: first yields an initial attachment info event,

        replays historical events from buffer, then streams live events if not finished.
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

            if is_finished:
                return

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

    async def dispatch_run(
        self,
        run_id: str,
        snapshot: dict[str, Any],
        scan_id: str | None = None,
    ) -> asyncio.Task:
        """Dispatches background scan execution, returning the created asyncio.Task."""
        task = asyncio.create_task(self._execute_run(run_id, snapshot, scan_id))
        return task

    async def _execute_run(
        self,
        run_id: str,
        snapshot: dict[str, Any],
        scan_id: str | None = None,
    ) -> None:
        """Executes the unified scan run pipeline: Ingest -> Finalize & Evaluate -> Match Alerts."""
        try:
            with Session(db_engine) as session:
                run = session.get(ScanRun, run_id)
                if run:
                    run.status = ScanRunStatus.RUNNING
                    if not run.started_at:
                        run.started_at = datetime.now(UTC)
                    session.add(run)
                    session.commit()

            cmd = [sys.executable, "-u", "-m", "engine.cli", "--config", "-"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            if process.stdin:
                process.stdin.write(json.dumps(snapshot).encode("utf-8") + b"\n")
                await process.stdin.drain()
                process.stdin.close()
                try:
                    await process.stdin.wait_closed()
                except Exception:
                    pass

            self.register_process(run_id, process)

            async def read_stderr():
                if not process.stderr:
                    return
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    self.publish_log(
                        run_id,
                        ServerSentEvent(data={"message": line.decode("utf-8").strip()}, event="log"),
                    )

            await asyncio.gather(
                _ingest_stdout(
                    run_id,
                    process,
                    publish_log=lambda ev: self.publish_log(run_id, ev),
                ),
                read_stderr(),
            )

            await process.wait()

            rc = process.returncode if process.returncode is not None else 1
            if rc in (130, 143):
                self.publish_log(run_id, ServerSentEvent(data={"message": "Run aborted by user"}, event="status"))
            else:
                self.publish_log(run_id, ServerSentEvent(data={"message": f"Run finished with code {rc}"}, event="status"))

            await asyncio.to_thread(_finalize_run, run_id, rc)

            with Session(db_engine) as session:
                finished_run = session.get(ScanRun, run_id)
                summary = (finished_run.metrics_json or {}).get("summary") if finished_run else None
                if summary:
                    self.publish_log(
                        run_id,
                        ServerSentEvent(
                            data={
                                "message": (
                                    f"[+] Evaluation complete: {summary.get('active', 0)} active, "
                                    f"{summary.get('warning', 0)} warning, "
                                    f"{summary.get('failed', 0)} failed, "
                                    f"{summary.get('ghost', 0)} ghost, "
                                    f"{summary.get('void', 0)} void"
                                )
                            },
                            event="log",
                        ),
                    )

            if scan_id:
                try:
                    with Session(db_engine) as session:
                        await check_and_dispatch_alerts(run_id, session)
                except Exception as e:
                    logger.error("Failed to process alerts for run %s: %s", run_id, e)

        except Exception as e:
            logger.exception("Engine error during run %s: %s", run_id, e)
            self.publish_log(run_id, ServerSentEvent(data={"message": f"Engine error: {e!s}"}, event="error"))
            with Session(db_engine) as session:
                run = session.get(ScanRun, run_id)
                if run:
                    run.status = ScanRunStatus.FAILED
                    run.finished_at = datetime.now(UTC)
                    session.add(run)
                    session.commit()
        finally:
            self.unregister_process(run_id)
            self.broadcast_sentinel(run_id)
            self._evict_old_buffers()

    def _evict_old_buffers(self) -> None:
        """Evicts oldest completed run log buffers when count exceeds max_retained_runs."""
        while len(self._log_buffers) > self._max_retained_runs:
            evicted = False
            for old_run_id in list(self._log_buffers.keys()):
                if not self.is_active(old_run_id) and not self._subscribers.get(old_run_id):
                    self._log_buffers.pop(old_run_id, None)
                    evicted = True
                    break
            if not evicted:
                break

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
