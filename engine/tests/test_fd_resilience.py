import asyncio
import errno
import logging
import resource
import socket
from unittest.mock import AsyncMock, patch

import pytest

from engine.engine import tune_nofile_and_workers
from engine.operations.network import resolve_target
from engine.probes.tcp import check_tcp_and_tls


def test_tune_nofile_and_workers_clamping():
    """Verifies that requested workers are clamped safely when OS soft nofile is low."""
    # Low limit (e.g. default container 1024): 10,000 workers clamped to 1024 - 250 = 774
    clamped = tune_nofile_and_workers(requested_workers=10000, current_soft=1024, current_hard=1024)
    assert clamped == 774

    # High limit (e.g. 65535): 10,000 workers should NOT be clamped
    unclamped = tune_nofile_and_workers(requested_workers=10000, current_soft=65535, current_hard=65535)
    assert unclamped == 10000

    # Pathologically low limit: clamps to minimum floor of 50
    floor = tune_nofile_and_workers(requested_workers=500, current_soft=200, current_hard=200)
    assert floor == 50


def test_network_module_eagerly_imports_thread_pool():
    """Verifies concurrent.futures.thread is loaded in sys.modules to prevent lazy-import FD errors."""
    import sys
    assert "concurrent.futures.thread" in sys.modules


@pytest.mark.asyncio
async def test_resolve_target_catches_oserror_errno24():
    """Verifies that resolve_target catches OSError (Errno 24 Too many open files) and returns gracefully."""
    with patch("socket.gethostbyname", side_effect=OSError(errno.EMFILE, "Too many open files")):
        ip, host_header, is_domain = await resolve_target("indica-devel")
        assert ip == ""
        assert host_header == "indica-devel"
        assert is_domain is True


@pytest.mark.asyncio
async def test_check_tcp_and_tls_retries_on_emfile(caplog):
    """Verifies that check_tcp_and_tls logs a warning and retries upon encountering EMFILE/ENFILE."""
    caplog.set_level(logging.WARNING)

    # First attempt raises EMFILE, second attempt succeeds
    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_writer.get_extra_info.return_value = None

    attempts = [
        OSError(errno.EMFILE, "Too many open files"),
        (mock_reader, mock_writer),
    ]

    async def mock_open_connection(*args, **kwargs):
        res = attempts.pop(0)
        if isinstance(res, Exception):
            raise res
        return res

    with patch("asyncio.open_connection", side_effect=mock_open_connection):
        result = await check_tcp_and_tls("192.168.1.1", 80, timeout=1.0)
        assert result.tcp_status == "open"
        assert any("Too many open files" in record.message for record in caplog.records)
