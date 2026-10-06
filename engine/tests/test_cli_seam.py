import subprocess
import time
import json
import signal
import sys

import pytest


@pytest.mark.integration
def test_engine_cli_abort_seam():
    # Start the engine subprocess with a long worker delay so it doesn't finish immediately
    process = subprocess.Popen(
        [sys.executable, "-m", "engine.cli", "127.0.0.1", "-p", "80", "--delay", "10.0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Give it a second to start up and initialize workers
    time.sleep(1.5)
    
    # Send SIGTERM to simulate API aborting the run
    process.send_signal(signal.SIGTERM)
    
    # Wait for process to exit gracefully
    try:
        stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        assert False, "Engine did not exit gracefully within timeout"
        
    # Check exit code (130 for SIGINT, 143 for SIGTERM depending on platform/Python handling)
    assert process.returncode in (130, 143), f"Expected 130 or 143, got {process.returncode}"
    
    # Verify stderr logs contain abort signal
    assert "Received signal 15" in stderr or "aborting engine" in stderr
    
    # Verify stdout contains final NDJSON summary
    lines = [line.strip() for line in stdout.split('\n') if line.strip()]
    assert len(lines) > 0, "No output on stdout"
    
    last_line = lines[-1]
    try:
        summary = json.loads(last_line)
        assert summary.get("status") == "aborted", "Summary line should indicate aborted status"
    except json.JSONDecodeError:
        assert False, "Last line of stdout is not valid JSON"
