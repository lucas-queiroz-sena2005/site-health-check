import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from engine.probes.http import check_http_routing
from engine.schemas.engine import TaskFlags, HttpRoutingCheck
import engine.engine as engine_module
from engine.engine import worker


import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from engine.probes.http import check_http_routing
from engine.schemas.engine import TaskFlags, HttpRoutingCheck, EngineTask, TaskContext
import engine.engine as engine_module
from engine.engine import worker


def create_mock_aiohttp_session(status_code: int, location: str = None, url: str = None):
    mock_response = AsyncMock()
    mock_response.status = status_code
    mock_response.headers = {"Server": "nginx"}
    if location:
        mock_response.headers["Location"] = location
    if url:
        import yarl
        mock_response.url = yarl.URL(url)
    mock_response.text = AsyncMock(return_value="<html></html>")

    mock_req_ctx = AsyncMock()
    mock_req_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_req_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_req_ctx)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    return mock_session


@pytest.mark.asyncio
async def test_check_http_routing_no_redirect():
    mock_session = create_mock_aiohttp_session(200)
    with patch('aiohttp.ClientSession', return_value=mock_session):
        flags = TaskFlags(timeout_seconds=5)
        result = await check_http_routing("127.0.0.1", 80, None, flags)

        assert result.status_code == 200
        assert result.redirects_to_url is None
        
        # Verify allow_redirects=False was passed
        mock_session.get.assert_called_once()
        _, kwargs = mock_session.get.call_args
        assert kwargs.get("allow_redirects") is False


@pytest.mark.asyncio
async def test_check_http_routing_with_redirect():
    mock_session = create_mock_aiohttp_session(301, location="/login", url="http://127.0.0.1:80/")
    with patch('aiohttp.ClientSession', return_value=mock_session):
        flags = TaskFlags(timeout_seconds=5)
        result = await check_http_routing("127.0.0.1", 80, None, flags)

        assert result.status_code == 301
        assert result.redirects_to_url == "http://127.0.0.1/login"


async def run_worker_with_task(initial_task: EngineTask):
    """Helper to run the worker loop with a given initial task and standard mocks."""
    queue = asyncio.Queue()
    await queue.put(initial_task)

    async def mock_resolve_target(target):
        if target == "login.example.com":
            return "2.2.2.2", target, True
        return "127.0.0.1", None, False

    async def mock_check_tcp_and_tls(ip, port, server_hostname):
        from engine.schemas.engine import PortState
        return PortState(tcp_status="open")

    mock_http = AsyncMock()
    async def mock_check_http_routing(ip, port, host_header, flags):
        if ip == "127.0.0.1":
            return HttpRoutingCheck(
                status_code=302,
                redirects_to_url="https://login.example.com/auth"
            )
        return HttpRoutingCheck(status_code=200)
    mock_http.side_effect = mock_check_http_routing

    engine_module.is_cancelled = False
    engine_module.seen_tcp.clear()
    engine_module.seen_http.clear()

    put_calls = []
    original_put = queue.put
    async def mock_put(item):
        put_calls.append(item)
        await original_put(item)

    with patch.object(engine_module, 'resolve_target', side_effect=mock_resolve_target), \
         patch.object(engine_module, 'check_tcp_and_tls', side_effect=mock_check_tcp_and_tls), \
         patch.object(engine_module, 'check_http_routing', new=mock_http), \
         patch.object(queue, 'put', side_effect=mock_put), \
         patch('sys.stdout.write'), \
         patch('sys.stdout.flush'):
        
        worker_task = asyncio.create_task(worker("test_worker", queue))
        await asyncio.sleep(0.1)
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
            
    return put_calls, mock_http


@pytest.mark.asyncio
async def test_engine_enqueue_redirect():
    initial_task = EngineTask(
        target="127.0.0.1",
        ports=[80],
        context=TaskContext(
            flags=TaskFlags(out_of_scope_depth=1),
            depth=0
        )
    )
    
    put_calls, mock_http = await run_worker_with_task(initial_task)
        
    # Verify a new task was enqueued for login.example.com
    # put_calls should have 1 item (the one put by the redirect)
    assert len(put_calls) == 1
    new_task = put_calls[0]
    
    assert new_task.target == "login.example.com"
    assert new_task.ports == [443]  # derived from https
    assert new_task.context.depth == 0      # depth is passed from original task (0) to worker
    assert new_task.context.parent_ip == "127.0.0.1"


@pytest.mark.asyncio
async def test_engine_redirect_depth_limit():
    """
    Verifies that while the redirect enters the queue with depth=current_depth,
    the worker properly increments the depth upon popping and resolving the new IP,
    and drops it if it exceeds out_of_scope_depth.
    """
    initial_task = EngineTask(
        target="127.0.0.1",
        ports=[80],
        context=TaskContext(
            flags=TaskFlags(out_of_scope_depth=0),
            depth=0
        )
    )
    
    put_calls, mock_http = await run_worker_with_task(initial_task)
        
    # check_http_routing should only be called ONCE (for 127.0.0.1).
    # The worker pops login.example.com, resolves it to 2.2.2.2.
    # 2.2.2.2 != 127.0.0.1, so depth increments to 1.
    # 1 > out_of_scope_depth (0), so it skips scanning 2.2.2.2 entirely!
    assert mock_http.call_count == 1
    # Verify it was indeed called for 127.0.0.1
    assert mock_http.call_args[0][0] == "127.0.0.1"

