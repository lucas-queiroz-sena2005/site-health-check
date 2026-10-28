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
def test_engine_cli_config_stdin_seam():
    # Pass execution config payload over stdin
    payload = {
        "targets": ["127.0.0.1"],
        "ports": [80],
        "flags": {
            "check_http": False,
            "rate": 50.0,
            "timeout": 5,
        }
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "engine.cli", "--config", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = process.communicate(input=json.dumps(payload), timeout=10)

    assert process.returncode == 0, f"Engine failed with stderr: {stderr}"
    lines = [line.strip() for line in stdout.split('\n') if line.strip()]
    assert len(lines) >= 1, "Expected at least 1 line of NDJSON output"
    
    # Verify summary line
    summary = json.loads(lines[-1])
    assert summary.get("status") == "completed"
    
    # Check that HTTP routing checks did not run (flags.check_http == False)
    for line in lines[:-1]:
        delta = json.loads(line)
        for ip, state in delta.items():
            for port, port_state in state.get("ports", {}).items():
                assert not port_state.get("http_routing_checks"), "HTTP checks ran despite check_http: false"


@pytest.mark.integration
def test_engine_cli_config_file_seam(tmp_path):
    # Pass execution config payload via file path with -c
    payload = {
        "targets": ["127.0.0.1"],
        "ports": ["80,443"],
        "flags": {
            "check_http": False,
            "rate": 50.0,
        }
    }
    config_file = tmp_path / "scan_config.json"
    config_file.write_text(json.dumps(payload))

    process = subprocess.Popen(
        [sys.executable, "-m", "engine.cli", "-c", str(config_file)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 0, f"Engine failed with stderr: {stderr}"
    lines = [line.strip() for line in stdout.split('\n') if line.strip()]
    assert len(lines) >= 1
    summary = json.loads(lines[-1])
    assert summary.get("status") == "completed"


@pytest.mark.integration
def test_engine_cli_config_stdin_abort_seam():
    payload = {
        "targets": ["127.0.0.1"],
        "ports": [80],
        "flags": {
            "rate": 0.1,
            "timeout": 10,
        }
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "engine.cli", "--config", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()
    process.stdin.close()
    process.stdin = None

    time.sleep(1.5)
    process.send_signal(signal.SIGTERM)

    try:
        stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        assert False, "Engine did not exit gracefully within timeout"

    assert process.returncode in (130, 143), f"Expected 130 or 143, got {process.returncode}"
    assert "Received signal 15" in stderr or "aborting engine" in stderr
    lines = [line.strip() for line in stdout.split('\n') if line.strip()]
    assert len(lines) > 0
    summary = json.loads(lines[-1])
    assert summary.get("status") == "aborted"


def test_engine_cli_missing_target_and_config_fails():
    process = subprocess.Popen(
        [sys.executable, "-m", "engine.cli"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode != 0
    assert "error" in stderr.lower() or "usage" in stderr.lower()

