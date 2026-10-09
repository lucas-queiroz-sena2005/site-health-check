import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_round_robin_generator():
    # Test that target generation interleaves IPs from different subnets
    from engine.engine import generate_targets_round_robin
    
    blocks = ["10.0.0.0/24", "10.0.1.0/24"]
    gen = generate_targets_round_robin(blocks)
    
    assert next(gen) == "10.0.0.0"
    assert next(gen) == "10.0.1.0"
    assert next(gen) == "10.0.0.1"
    assert next(gen) == "10.0.1.1"

@pytest.mark.asyncio
async def test_engine_queue_maxsize():
    from engine.engine import async_main
    
    with patch("engine.engine.asyncio.Queue") as mock_queue:
        # Prevent actually doing work
        mock_q_instance = MagicMock()
        mock_q_instance.join = AsyncMock()
        mock_queue.return_value = mock_q_instance
        
        with patch("engine.engine.asyncio.create_task", return_value=AsyncMock()), \
             patch("engine.engine.asyncio.wait", return_value=(set(), set())), \
             patch("engine.engine.asyncio.gather", new_callable=AsyncMock):
            
            await async_main([{"target": "10.0.0.0/24", "ports": [443]}], workers_count=1)
            
        # Assert the queue was created with maxsize=1000
        mock_queue.assert_called_once_with(maxsize=1000)
