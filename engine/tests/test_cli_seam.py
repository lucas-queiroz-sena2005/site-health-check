import subprocess
import time
import json
import signal
import sys

import pytest


@pytest.mark.integration
def test_engine_cli_abort_seam():
    # Start the engine subprocess with a tight rate limit so it doesn't finish immediately
    process = subprocess.Popen(
        [sys.executable, "-m", "engine.cli", "127.0.0.1", "-p", "80", "--rate", "0.1"],
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

@pytest.mark.integration
def test_engine_cli_no_http_seam():
    # Run the engine with --no-check-http
    process = subprocess.Popen(
        [sys.executable, "-m", "engine.cli", "127.0.0.1", "-p", "80", "--no-check-http"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = process.communicate(timeout=10)
    
    assert process.returncode == 0
    lines = [line.strip() for line in stdout.split('\n') if line.strip()]
    
    # Check that none of the delta lines contain HTTP routing checks
    for line in lines[:-1]:
        try:
            delta = json.loads(line)
            for ip, state in delta.items():
                for port, port_state in state.get("ports", {}).items():
                    assert not port_state.get("http_routing_checks"), "HTTP checks ran despite --no-check-http"
        except json.JSONDecodeError:
            pass

@pytest.mark.integration
def test_engine_cli_new_flags_seam():
    # Run the engine with the new flags: -rsv, --whitelist, --blacklist
    process = subprocess.Popen(
        [
            sys.executable, "-m", "engine.cli", "127.0.0.1", 
            "-p", "80", 
            "-rsv",
            "--whitelist", "10.0.0.0/16",
            "--blacklist", "10.0.5.0/24",
            "--dr", "5",
            "--ds", "2",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # We just wait for it to print the "[*] Standardized Payload Built:" and then we can terminate it
    time.sleep(1)
    process.send_signal(signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=5)
    
    # Check that it didn't fail argparse
    assert "error: unrecognized arguments" not in stderr, f"Argparse failed: {stderr}"
    
    # The JSON payload is printed to stderr in logging.info before engine starts
    # Wait, cli.py does: logger.info(json.dumps(json_payload, indent=2))
    assert '"follow_redirects": true' in stderr or '"follow_redirects_out_of_scope": true' in stderr, "Missing redirect flag in payload"
    assert '"force_vhost_origin": true' in stderr, "Missing vhost flag in payload"
    assert '"whitelist": "10.0.0.0/16"' in stderr, "Missing whitelist in payload"
    assert '"blacklist": "10.0.5.0/24"' in stderr, "Missing blacklist in payload"
    assert '"max_depth_redirects": 5' in stderr, "Missing max_depth_redirects in payload"
    assert '"max_depth_sans": 2' in stderr, "Missing max_depth_sans in payload"

