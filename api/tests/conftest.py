import asyncio
import pytest


@pytest.fixture(autouse=True)
def no_engine_subprocess(monkeypatch):
    """API unit tests must never spawn a real engine process (it would scan the network
    and write to the real database). Endpoints that launch runs get a no-op instead.
    The real process boundary is covered by engine/tests/test_cli_seam.py."""
    launched: list[str] = []

    async def fake_run_engine_cli(run_id, snapshot, app_state):
        launched.append(run_id)

    async def fake_dispatch_run(self, run_id, snapshot, scan_id=None):
        launched.append(run_id)
        async def dummy():
            pass
        return asyncio.create_task(dummy())

    for target in (
        "api.routers.runs.run_engine_cli",
        "api.routers.scans.run_engine_cli",
        "api.services.scheduler.run_engine_cli",
    ):
        monkeypatch.setattr(target, fake_run_engine_cli)

    monkeypatch.setattr("api.services.run_manager.RunManager.dispatch_run", fake_dispatch_run)
    return launched
