import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from engine.probes.http import check_http_routing
from engine.schemas.engine import TaskFlags, HttpRoutingCheck
import engine.engine as engine_module
from engine.engine import scanner_routine


import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from engine.probes.http import check_http_routing
from engine.schemas.engine import TaskFlags, HttpRoutingCheck, EngineTask, TaskContext
import engine.engine as engine_module
from engine.engine import scanner_routine


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
        limiter = engine_module.AsyncTokenBucket(50.0)
        
        from engine.parsing import ScopeValidator
        validator = None
        if initial_task.context.flags.whitelist or initial_task.context.flags.blacklist:
            validator = ScopeValidator(
                whitelist=initial_task.context.flags.whitelist,
                blacklist=initial_task.context.flags.blacklist
            )
            
        worker_task = asyncio.create_task(scanner_routine("test_routine", queue, limiter, validator))
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
            flags=TaskFlags(follow_redirects=True, follow_redirects_out_of_scope=True, max_depth_redirects=5),
            redirect_depth=0,
            san_depth=0
        )
    )
    
    put_calls, mock_http = await run_worker_with_task(initial_task)
        
    # Verify a new task was enqueued for login.example.com
    assert len(put_calls) == 1
    new_task = put_calls[0]
    
    assert new_task.target == "login.example.com"
    assert new_task.ports == [443]
    assert new_task.context.redirect_depth == 0      # depth is passed from original task (0) to worker and increments on pop
    assert new_task.context.parent_ip == "127.0.0.1"


@pytest.mark.asyncio
async def test_engine_redirect_depth_limit():
    """
    Verifies that while the redirect enters the queue with depth=current_depth,
    the worker properly increments the depth upon popping and resolving the new IP,
    and drops it if it exceeds max_depth_redirects.
    """
    initial_task = EngineTask(
        target="127.0.0.1",
        ports=[80],
        context=TaskContext(
            flags=TaskFlags(follow_redirects=True, follow_redirects_out_of_scope=True, max_depth_redirects=0),
            redirect_depth=0,
            san_depth=0
        )
    )
    
    put_calls, mock_http = await run_worker_with_task(initial_task)
        
    # The worker pops login.example.com, resolves it to 2.2.2.2.
    # 2.2.2.2 != 127.0.0.1, so depth increments to 1.
    # 1 > max_depth_redirects (0), so it skips scanning 2.2.2.2 entirely!
    assert mock_http.call_count == 1
    assert mock_http.call_args[0][0] == "127.0.0.1"

@pytest.mark.asyncio
async def test_engine_redirect_dropped_when_out_of_scope():
    """
    Verifies that if a target resolves to an IP outside the whitelist,
    and follow_redirects_out_of_scope is False, it is dropped immediately.
    """
    initial_task = EngineTask(
        target="127.0.0.1",
        ports=[80],
        context=TaskContext(
            # Whitelist strict to 127.0.0.1. login.example.com resolves to 2.2.2.2!
            flags=TaskFlags(whitelist="127.0.0.1", follow_redirects=True, follow_redirects_out_of_scope=False, max_depth_redirects=5),
            redirect_depth=0,
            san_depth=0
        )
    )
    
    put_calls, mock_http = await run_worker_with_task(initial_task)
    
    # HTTP probe should only happen for 127.0.0.1.
    # The new target 2.2.2.2 should be dropped by the ScopeValidator.
    assert mock_http.call_count == 1
    assert mock_http.call_args[0][0] == "127.0.0.1"

@pytest.mark.asyncio
async def test_engine_vhost_origin_probing():
    """
    Verifies that when force_vhost_origin is true, the engine bypasses DNS resolution,
    keeps the parent IP, and sends the target as the Host header.
    """
    initial_task = EngineTask(
        target="hidden-vhost.local",
        ports=[80],
        context=TaskContext(
            flags=TaskFlags(force_vhost_origin=True),
            parent_ip="192.168.1.100",  # The IP we discovered the vhost on
            source_type="seed"
        )
    )
    
    with patch('engine.engine.resolve_target') as mock_resolve:
        put_calls, mock_http = await run_worker_with_task(initial_task)
        
        # DNS resolution should NEVER be called!
        assert mock_resolve.call_count == 0
        
        # HTTP probe MUST be called against 192.168.1.100, but with host_header="hidden-vhost.local"
        assert mock_http.call_count == 1
        args, kwargs = mock_http.call_args
        assert args[0] == "192.168.1.100"  # Probing the IP
        assert kwargs["host_header"] == "hidden-vhost.local"  # using the SNI target
