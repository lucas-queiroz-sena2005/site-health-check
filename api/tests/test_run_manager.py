import asyncio
import signal
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.sse import ServerSentEvent

from api.services.run_manager import RunManager


@pytest.mark.asyncio
async def test_run_manager_process_registration_and_status():
    manager = RunManager()
    run_id = "test-run-1"

    assert not manager.is_active(run_id)

    mock_process = MagicMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = None

    manager.register_process(run_id, mock_process)
    assert manager.is_active(run_id)

    manager.unregister_process(run_id)
    assert not manager.is_active(run_id)


@pytest.mark.asyncio
async def test_run_manager_abort_active_process():
    manager = RunManager()
    run_id = "test-run-abort"

    mock_process = MagicMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = None

    manager.register_process(run_id, mock_process)

    aborted = manager.abort_run(run_id)
    assert aborted is True
    mock_process.send_signal.assert_called_once_with(signal.SIGTERM)


@pytest.mark.asyncio
async def test_run_manager_abort_inactive_process():
    manager = RunManager()
    run_id = "test-run-inactive"

    aborted = manager.abort_run(run_id)
    assert aborted is False


@pytest.mark.asyncio
async def test_run_manager_abort_process_lookup_error():
    manager = RunManager()
    run_id = "test-run-lookup-err"

    mock_process = MagicMock(spec=asyncio.subprocess.Process)
    mock_process.returncode = None
    mock_process.send_signal.side_effect = ProcessLookupError()

    manager.register_process(run_id, mock_process)

    aborted = manager.abort_run(run_id)
    assert aborted is False
    assert not manager.is_active(run_id)


@pytest.mark.asyncio
async def test_run_manager_log_buffering_ring_buffer_bounds():
    manager = RunManager()
    run_id = "test-run-logs"

    # Publish 1050 events into a buffer with maxlen=1000
    for i in range(1050):
        manager.publish_log(run_id, ServerSentEvent(data={"index": i}, event="log"))

    buffer = manager.get_buffered_logs(run_id)
    assert len(buffer) == 1000
    # The oldest 50 should have been evicted; first element should be index 50
    assert buffer[0].data == {"index": 50}
    assert buffer[-1].data == {"index": 1049}


@pytest.mark.asyncio
async def test_run_manager_sse_streaming_replay_and_live():
    manager = RunManager()
    run_id = "test-run-stream"

    # Publish historical events before client subscribes
    manager.publish_log(run_id, ServerSentEvent(data={"msg": "hist_1"}, event="log"))
    manager.publish_log(run_id, ServerSentEvent(data={"msg": "hist_2"}, event="log"))

    received = []

    async def client():
        async for event in manager.subscribe_logs(run_id):
            received.append(event)
            if len(received) == 3:  # 2 historical + 1 live
                break

    client_task = asyncio.create_task(client())
    await asyncio.sleep(0.05)

    # Publish live event while subscriber is connected
    manager.publish_log(run_id, ServerSentEvent(data={"msg": "live_3"}, event="log"))

    await asyncio.wait_for(client_task, timeout=2.0)

    assert len(received) == 3
    assert received[0].data == {"msg": "hist_1"}
    assert received[1].data == {"msg": "hist_2"}
    assert received[2].data == {"msg": "live_3"}


@pytest.mark.asyncio
async def test_run_manager_subscriber_cleanup_on_disconnect():
    manager = RunManager()
    run_id = "test-run-cleanup"

    # Start generator and immediately break out (simulating client disconnect)
    async for _ in manager.subscribe_logs(run_id):
        break

    # Verify subscriber queue count is 0
    assert manager.subscriber_count(run_id) == 0


@pytest.mark.asyncio
async def test_run_manager_cleanup_run():
    manager = RunManager()
    run_id = "test-run-full-cleanup"

    mock_process = MagicMock(spec=asyncio.subprocess.Process)
    manager.register_process(run_id, mock_process)
    manager.publish_log(run_id, ServerSentEvent(data={"msg": "hello"}, event="log"))

    assert manager.is_active(run_id)
    assert len(manager.get_buffered_logs(run_id)) == 1

    manager.cleanup_run(run_id)

    assert not manager.is_active(run_id)
    assert len(manager.get_buffered_logs(run_id)) == 0
    assert manager.subscriber_count(run_id) == 0
