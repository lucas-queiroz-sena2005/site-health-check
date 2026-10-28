import uuid
import pytest
from sqlmodel import Session, select, create_engine, SQLModel
from sqlmodel.pool import StaticPool
from api.models import HostState, PortState, HttpRoutingCheck, TlsCertificate
from api.services.runner import _upsert_delta_sync
from unittest.mock import patch

@pytest.fixture(name="test_engine")
def test_engine_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine

def test_upsert_delta_sync_inserts_and_updates(test_engine):
    with patch("api.services.runner.db_engine", test_engine):
        # We test that _upsert_delta_sync correctly merges overlapping data (ON CONFLICT DO UPDATE)
        run_id = str(uuid.uuid4())
        ip = "192.168.1.100"
        
        # Delta 1: partial data (just TCP open)
        delta1 = {
            "metadata": {"resolved_from": "test.local", "discovered_from": ["initial"]},
            "ports": {
                "443": {
                    "tcp_status": "open",
                    "tcp_latency_ms": 15
                }
            }
        }
        
        _upsert_delta_sync(run_id, ip, delta1)
        
        with Session(test_engine) as session:
            host = session.exec(select(HostState).where(HostState.scan_run_id == run_id, HostState.ip_address == ip)).first()
            assert host is not None
            assert host.resolved_domains == ["test.local"]
            
            ports = session.exec(select(PortState).where(PortState.host_state_id == host.id)).all()
            assert len(ports) == 1
            assert ports[0].port_number == 443
            assert ports[0].tcp_status == "open"
            assert ports[0].tcp_latency_ms == 15
            
        # Delta 2: overlapping data with new HTTP routing checks and TLS
        delta2 = {
            "metadata": {"resolved_from": "test.local", "discovered_from": ["initial", "second"]},
            "ports": {
                "443": {
                    "tcp_status": "open",
                    "tcp_latency_ms": 16, # updated latency
                    "tls_certificate": {
                        "valid": True,
                        "expires_in_days": 30,
                        "issuer": "Test CA",
                        "protocol_version": "TLSv1.3",
                        "domains_discovered_sans": ["test.local"]
                    },
                    "http_routing_checks": {
                        "test.local": {
                            "status_code": 200,
                            "http_latency_ms": 45,
                            "path_checked": "/",
                            "server_header": "nginx"
                        }
                    }
                }
            }
        }
        
        _upsert_delta_sync(run_id, ip, delta2)
        
        with Session(test_engine) as session:
            host = session.exec(select(HostState).where(HostState.scan_run_id == run_id, HostState.ip_address == ip)).first()
            assert host.discovered_from == ["initial", "second"]
            
            ports = session.exec(select(PortState).where(PortState.host_state_id == host.id)).all()
            assert len(ports) == 1 # still 1 port
            port = ports[0]
            assert port.tcp_latency_ms == 16 # updated
            
            tls = session.exec(select(TlsCertificate).where(TlsCertificate.port_state_id == port.id)).first()
            assert tls is not None
            assert tls.issuer == "Test CA"
            assert tls.valid is True
            
            routes = session.exec(select(HttpRoutingCheck).where(HttpRoutingCheck.port_state_id == port.id)).all()
            assert len(routes) == 1
            assert routes[0].domain == "test.local"
            assert routes[0].status_code == 200


def test_finalize_run_prunes_void_hosts_and_inserts_synthetic_void_on_clean_db(test_engine):
    from datetime import datetime, timezone
    from api.models import ScanRun, ScanRunStatus
    from api.services.runner import _finalize_run

    with patch("api.services.runner.db_engine", test_engine):
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with Session(test_engine) as session:
            run = ScanRun(
                id=run_id,
                status=ScanRunStatus.RUNNING,
                started_at=now,
                execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30}
            )
            session.add(run)

            # Add 3 non-responsive hosts under 10.0.0.0/24 with closed port 80
            for i in range(1, 4):
                h = HostState(
                    id=f"{run_id}_10.0.0.{i}",
                    scan_run_id=run_id,
                    ip_address=f"10.0.0.{i}",
                    resolved_domains=["10.0.0.0/24"]
                )
                session.add(h)
                session.flush()
                p = PortState(
                    id=f"{h.id}_80",
                    host_state_id=h.id,
                    port_number=80,
                    tcp_status="closed"
                )
                session.add(p)
            session.commit()

        # Run finalize
        _finalize_run(run_id, 0)

        with Session(test_engine) as session:
            final_run = session.get(ScanRun, run_id)
            assert final_run.status == ScanRunStatus.COMPLETED

            # The 3 individual dead hosts must be deleted and excluded from table
            hosts = session.exec(select(HostState).where(HostState.scan_run_id == run_id)).all()
            assert len(hosts) == 0

            # Also verify summary stats in metrics_json
            summary = final_run.metrics_json["summary"]
            assert summary["void"] == 3
            assert summary["ghost"] == 0
            assert summary["active"] == 0


def test_finalize_run_preserves_active_and_ghost_hosts_while_pruning_void(test_engine):
    from datetime import datetime, timezone, timedelta
    from api.models import ScanRun, ScanRunStatus
    from api.services.runner import _finalize_run

    with patch("api.services.runner.db_engine", test_engine):
        now = datetime.now(timezone.utc)
        prev_run_id = str(uuid.uuid4())
        curr_run_id = str(uuid.uuid4())

        with Session(test_engine) as session:
            # Historical completed run 2 days ago where 10.0.0.2 was active
            prev_run = ScanRun(
                id=prev_run_id,
                status=ScanRunStatus.COMPLETED,
                started_at=now - timedelta(days=2),
                execution_config_snapshot_json={"ghost_window": "7d"}
            )
            session.add(prev_run)
            h_prev = HostState(
                id=f"{prev_run_id}_10.0.0.2",
                scan_run_id=prev_run_id,
                ip_address="10.0.0.2",
                resolved_domains=["10.0.0.0/24"]
            )
            session.add(h_prev)
            session.flush()
            session.add(PortState(
                id=f"{h_prev.id}_80",
                host_state_id=h_prev.id,
                port_number=80,
                tcp_status="open"
            ))

            # Current run
            curr_run = ScanRun(
                id=curr_run_id,
                status=ScanRunStatus.RUNNING,
                started_at=now,
                execution_config_snapshot_json={"ghost_window": "7d", "tls_warning_days": 30}
            )
            session.add(curr_run)

            # Host 1: Active
            h1 = HostState(id=f"{curr_run_id}_10.0.0.1", scan_run_id=curr_run_id, ip_address="10.0.0.1", resolved_domains=["10.0.0.0/24"])
            session.add(h1)
            session.flush()
            session.add(PortState(id=f"{h1.id}_80", host_state_id=h1.id, port_number=80, tcp_status="open"))

            # Host 2: Dead now, but was active 2d ago -> Ghost
            h2 = HostState(id=f"{curr_run_id}_10.0.0.2", scan_run_id=curr_run_id, ip_address="10.0.0.2", resolved_domains=["10.0.0.0/24"])
            session.add(h2)
            session.flush()
            session.add(PortState(id=f"{h2.id}_80", host_state_id=h2.id, port_number=80, tcp_status="closed"))

            # Host 3 & 4: Dead now, never active -> Void
            for i in (3, 4):
                h = HostState(id=f"{curr_run_id}_10.0.0.{i}", scan_run_id=curr_run_id, ip_address=f"10.0.0.{i}", resolved_domains=["10.0.0.0/24"])
                session.add(h)
                session.flush()
                session.add(PortState(id=f"{h.id}_80", host_state_id=h.id, port_number=80, tcp_status="closed"))

            session.commit()

        # Run finalize on current run
        _finalize_run(curr_run_id, 0)

        with Session(test_engine) as session:
            final_run = session.get(ScanRun, curr_run_id)
            hosts = session.exec(select(HostState).where(HostState.scan_run_id == curr_run_id)).all()
            # 1 active + 1 ghost = 2 (void hosts excluded from table)
            assert len(hosts) == 2
            ip_map = {h.ip_address: h for h in hosts}
            assert "10.0.0.1" in ip_map
            assert "10.0.0.2" in ip_map

            summary = final_run.metrics_json["summary"]
            assert summary["active"] == 1
            assert summary["ghost"] == 1
            assert summary["void"] == 2


@pytest.mark.asyncio
async def test_run_manager_stdin_dispatch(test_engine):
    import json
    import asyncio
    from unittest.mock import AsyncMock, patch, MagicMock
    from api.services.run_manager import RunManager
    from api.models import ScanRun, ScanRunStatus
    from datetime import datetime, timezone

    run_id = str(uuid.uuid4())
    snapshot = {
        "targets": ["10.0.0.1", "10.0.0.2"],
        "ports": [80, 443],
        "flags": {"check_http": False, "rate": 25.0}
    }

    with patch("api.services.runner.db_engine", test_engine), \
         patch("api.services.run_manager.db_engine", test_engine):
        with Session(test_engine) as session:
            session.add(ScanRun(
                id=run_id,
                status=ScanRunStatus.PENDING,
                started_at=datetime.now(timezone.utc),
                execution_config_snapshot_json=snapshot
            ))
            session.commit()

        mock_process = AsyncMock()
        mock_process.stdin = MagicMock()
        mock_process.stdin.write = MagicMock()
        mock_process.stdin.drain = AsyncMock()
        mock_process.stdin.close = MagicMock()
        mock_process.stdin.wait_closed = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=[
            b'{"status": "completed"}\n',
            b''
        ])
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b'')
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        manager = RunManager()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
            await manager._execute_run(run_id, snapshot)

            mock_exec.assert_called_once()
            cmd_args = mock_exec.call_args[0]
            assert cmd_args[1:] == ("-u", "-m", "engine.cli", "--config", "-")
            assert mock_exec.call_args[1].get("stdin") == asyncio.subprocess.PIPE

            written_payload = b"".join(call.args[0] for call in mock_process.stdin.write.call_args_list).decode("utf-8")
            loaded = json.loads(written_payload)
            assert loaded["targets"] == ["10.0.0.1", "10.0.0.2"]
            assert loaded["ports"] == [80, 443]
            assert loaded["flags"]["check_http"] is False


def test_upsert_delta_sync_preserves_open_tcp_and_merges_discovered_from(test_engine):
    with patch("api.services.runner.db_engine", test_engine):
        run_id = str(uuid.uuid4())
        ip = "192.168.1.50"

        # Delta 1: TCP probe reveals port 443 open with latency 15ms and subrun_id
        delta1 = {
            "metadata": {
                "resolved_from": "host1.local",
                "discovered_from": ["192.168.1.1"],
                "subrun_id": "192.168.1.0/24"
            },
            "ports": {
                "443": {
                    "tcp_status": "open",
                    "tcp_latency_ms": 15
                }
            }
        }
        _upsert_delta_sync(run_id, ip, delta1)

        # Delta 2: VHost probe arrives where TCP check was skipped (tcp_status closed/None, subrun_id None)
        delta2 = {
            "metadata": {
                "resolved_from": "vhost.local",
                "discovered_from": ["192.168.1.2"],
                "subrun_id": None
            },
            "ports": {
                "443": {
                    "tcp_status": "closed",
                    "tcp_latency_ms": None,
                    "http_routing_checks": {
                        "vhost.local": {
                            "status_code": 200,
                            "path_checked": "/"
                        }
                    }
                }
            }
        }
        _upsert_delta_sync(run_id, ip, delta2)

        with Session(test_engine) as session:
            host = session.exec(select(HostState).where(HostState.scan_run_id == run_id, HostState.ip_address == ip)).first()
            assert host is not None
            assert host.subrun_id == "192.168.1.0/24"
            assert "192.168.1.1" in host.discovered_from
            assert "192.168.1.2" in host.discovered_from

            port = session.exec(select(PortState).where(PortState.host_state_id == host.id, PortState.port_number == 443)).first()
            assert port is not None
            assert port.tcp_status == "open"
            assert port.tcp_latency_ms == 15


@pytest.mark.asyncio
async def test_run_manager_dispatch_run_pipeline(test_engine):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from api.models import ScanRun, ScanRunStatus
    from api.services.run_manager import RunManager

    run_id = str(uuid.uuid4())
    snapshot = {"targets": ["127.0.0.1"], "ports": [80], "flags": {}}

    with Session(test_engine) as session:
        run = ScanRun(
            id=run_id,
            execution_config_snapshot_json=snapshot,
            status=ScanRunStatus.PENDING,
        )
        session.add(run)
        session.commit()

    manager = RunManager()
    async def real_dispatch_run(r, s, scan_id=None):
        return asyncio.create_task(manager._execute_run(r, s, scan_id))
    manager.dispatch_run = real_dispatch_run

    mock_process = AsyncMock()
    mock_process.stdin = MagicMock()
    mock_process.stdin.write = MagicMock()
    mock_process.stdin.drain = AsyncMock()
    mock_process.stdin.close = MagicMock()
    mock_process.stdin.wait_closed = AsyncMock()
    mock_process.stdout = AsyncMock()
    mock_process.stdout.readline = AsyncMock(side_effect=[
        b'{"status": "completed"}\n',
        b''
    ])
    mock_process.stderr = AsyncMock()
    mock_process.stderr.readline = AsyncMock(return_value=b'')
    mock_process.wait = AsyncMock(return_value=0)
    mock_process.returncode = 0

    # dispatch_run should execute the full unified pipeline:
    # 1. Spawns engine CLI subprocess and streams deltas
    # 2. Finalizes with evaluate_scan_run
    # 3. Dispatches alerts if scan_id provided
    with patch("api.services.run_manager.db_engine", test_engine), \
         patch("api.services.runner.db_engine", test_engine), \
         patch("asyncio.create_subprocess_exec", return_value=mock_process), \
         patch("api.services.evaluator.evaluate_scan_run", wraps=__import__("api.services.evaluator", fromlist=["evaluate_scan_run"]).evaluate_scan_run) as mock_evaluate, \
         patch("api.services.run_manager.check_and_dispatch_alerts", new_callable=AsyncMock) as mock_alerts:
        
        task = await manager.dispatch_run(run_id, snapshot, scan_id="test-scan")
        await task

        assert mock_evaluate.called
        assert mock_alerts.called
        assert not manager.is_active(run_id)

        with Session(test_engine) as session:
            final_run = session.get(ScanRun, run_id)
            assert final_run.status == ScanRunStatus.COMPLETED


def test_finalize_run_pruning_toggles(test_engine):
    """Verify that _finalize_run respects prune_void_hosts and prune_closed_ports flags."""
    from datetime import datetime, timezone, timedelta
    from api.models import ScanRun, ScanRunStatus
    from api.services.runner import _finalize_run

    with patch("api.services.runner.db_engine", test_engine):
        now = datetime.now(timezone.utc)
        prev_run_id = str(uuid.uuid4())

        with Session(test_engine) as session:
            # Previous run: 10.0.0.10 had port 80 open (Ghost candidate)
            prev_run = ScanRun(
                id=prev_run_id,
                status=ScanRunStatus.COMPLETED,
                started_at=now - timedelta(days=1),
                execution_config_snapshot_json={"ghost_window": "7d"},
            )
            session.add(prev_run)
            h_prev = HostState(
                id=f"{prev_run_id}_10.0.0.10",
                scan_run_id=prev_run_id,
                ip_address="10.0.0.10",
            )
            session.add(h_prev)
            session.flush()
            session.add(PortState(
                id=f"{h_prev.id}_80",
                host_state_id=h_prev.id,
                port_number=80,
                tcp_status="open",
            ))
            session.commit()

        # Run A: prune_void_hosts=False and prune_closed_ports=False -> Keep all void hosts & all closed ports
        run_a_id = str(uuid.uuid4())
        with Session(test_engine) as session:
            run_a = ScanRun(
                id=run_a_id,
                status=ScanRunStatus.RUNNING,
                started_at=now,
                execution_config_snapshot_json={
                    "prune_void_hosts": False,
                    "prune_closed_ports": False,
                    "ghost_window": "7d",
                },
            )
            session.add(run_a)
            # Active host with port 80 open and port 8080 routine closed
            ha1 = HostState(id=f"{run_a_id}_10.0.0.1", scan_run_id=run_a_id, ip_address="10.0.0.1")
            session.add(ha1)
            session.flush()
            session.add(PortState(id=f"{ha1.id}_80", host_state_id=ha1.id, port_number=80, tcp_status="open"))
            session.add(PortState(id=f"{ha1.id}_8080", host_state_id=ha1.id, port_number=8080, tcp_status="closed"))
            # Void host
            ha2 = HostState(id=f"{run_a_id}_10.0.0.2", scan_run_id=run_a_id, ip_address="10.0.0.2")
            session.add(ha2)
            session.flush()
            session.add(PortState(id=f"{ha2.id}_80", host_state_id=ha2.id, port_number=80, tcp_status="closed"))
            session.commit()

        _finalize_run(run_a_id, 0)

        with Session(test_engine) as session:
            hosts_a = session.exec(select(HostState).where(HostState.scan_run_id == run_a_id)).all()
            assert len(hosts_a) == 2, "prune_void_hosts=False must preserve void host in SQLite"
            ports_a = session.exec(select(PortState).where(PortState.host_state_id == f"{run_a_id}_10.0.0.1")).all()
            assert len(ports_a) == 2, "prune_closed_ports=False must preserve routine closed port in SQLite"

        # Run B: prune_void_hosts=True and prune_closed_ports=True -> Prune void hosts & routine closed ports
        run_b_id = str(uuid.uuid4())
        with Session(test_engine) as session:
            run_b = ScanRun(
                id=run_b_id,
                status=ScanRunStatus.RUNNING,
                started_at=now,
                execution_config_snapshot_json={
                    "prune_void_hosts": True,
                    "prune_closed_ports": True,
                    "ghost_window": "7d",
                },
            )
            session.add(run_b)
            # Active host with port 80 open and port 8080 routine closed (never historically active)
            hb1 = HostState(id=f"{run_b_id}_10.0.0.1", scan_run_id=run_b_id, ip_address="10.0.0.1")
            session.add(hb1)
            session.flush()
            session.add(PortState(id=f"{hb1.id}_80", host_state_id=hb1.id, port_number=80, tcp_status="open"))
            session.add(PortState(id=f"{hb1.id}_8080", host_state_id=hb1.id, port_number=8080, tcp_status="closed"))
            # Ghost host: 10.0.0.10 had port 80 open historically, now closed
            hb_ghost = HostState(id=f"{run_b_id}_10.0.0.10", scan_run_id=run_b_id, ip_address="10.0.0.10")
            session.add(hb_ghost)
            session.flush()
            session.add(PortState(id=f"{hb_ghost.id}_80", host_state_id=hb_ghost.id, port_number=80, tcp_status="closed"))
            # Void host: 10.0.0.99 dead and never historically active
            hb_void = HostState(id=f"{run_b_id}_10.0.0.99", scan_run_id=run_b_id, ip_address="10.0.0.99")
            session.add(hb_void)
            session.flush()
            session.add(PortState(id=f"{hb_void.id}_80", host_state_id=hb_void.id, port_number=80, tcp_status="closed"))
            session.commit()

        _finalize_run(run_b_id, 0)

        with Session(test_engine) as session:
            hosts_b = session.exec(select(HostState).where(HostState.scan_run_id == run_b_id)).all()
            assert len(hosts_b) == 2, "Void host 10.0.0.99 must be pruned; active (10.0.0.1) & ghost (10.0.0.10) must be kept"
            b_ip_map = {h.ip_address: h for h in hosts_b}
            assert "10.0.0.1" in b_ip_map
            assert "10.0.0.10" in b_ip_map

            # On active host hb1 (10.0.0.1), port 8080 (routine closed) must be pruned, leaving only port 80
            ports_b1 = session.exec(select(PortState).where(PortState.host_state_id == f"{run_b_id}_10.0.0.1")).all()
            assert len(ports_b1) == 1, "Routine closed port 8080 must be pruned from SQLite"
            assert ports_b1[0].port_number == 80
            # Host scanned_port_count must still reflect that 2 ports were probed!
            hb1_final = session.get(HostState, f"{run_b_id}_10.0.0.1")
            assert hb1_final.scanned_port_count == 2
            assert hb1_final.open_port_count == 1

            # On ghost host hb_ghost (10.0.0.10), port 80 is closed BUT was historically open -> MUST NOT BE PRUNED
            ports_ghost = session.exec(select(PortState).where(PortState.host_state_id == f"{run_b_id}_10.0.0.10")).all()
            assert len(ports_ghost) == 1
            assert ports_ghost[0].port_number == 80
            assert ports_ghost[0].tcp_status == "closed"


def test_bulk_upsert_deltas_sync_coalescing(test_engine):
    """Verify _bulk_upsert_deltas_sync coalesces multiple deltas for the same IP in a single transaction."""
    from api.services.runner import _bulk_upsert_deltas_sync

    with patch("api.services.runner.db_engine", test_engine):
        run_id = str(uuid.uuid4())
        ip = "192.168.1.50"
        delta1 = (
            ip,
            {
                "metadata": {
                    "subrun_id": "sub_1",
                    "resolved_domains": ["vhost1.com"],
                    "discovered_from": ["192.168.1.1"],
                },
                "ports": {
                    "80": {"tcp_status": "open", "tcp_latency_ms": 10},
                    "443": {"tcp_status": "closed", "tcp_latency_ms": None},
                },
            },
        )
        delta2 = (
            ip,
            {
                "metadata": {
                    "resolved_domains": ["vhost2.com"],
                    "discovered_from": ["vhost1.com"],
                },
                "ports": {
                    "80": {"tcp_status": "closed", "tcp_latency_ms": None},  # Should NOT overwrite sticky 'open'
                    "443": {"tcp_status": "open", "tcp_latency_ms": 15},     # Flips to open
                },
            },
        )

        _bulk_upsert_deltas_sync(run_id, [delta1, delta2])

        with Session(test_engine) as session:
            host = session.exec(
                select(HostState).where(
                    HostState.scan_run_id == run_id, HostState.ip_address == ip
                )
            ).first()
            assert host is not None
            assert host.subrun_id == "sub_1"
            assert set(host.resolved_domains) == {"vhost1.com", "vhost2.com"}
            assert set(host.discovered_from) == {"192.168.1.1", "vhost1.com"}

            ports = session.exec(
                select(PortState).where(PortState.host_state_id == host.id)
            ).all()
            p_map = {p.port_number: p for p in ports}
            assert p_map[80].tcp_status == "open", "Sticky open status must be preserved"
            assert p_map[443].tcp_status == "open", "Port 443 opened in second delta must be open"


@pytest.mark.asyncio
async def test_ingest_stdout_micro_batching():
    """Verify _ingest_stdout flushes batches of up to 500 deltas and flushes remaining deltas on EOF."""
    from unittest.mock import AsyncMock, MagicMock
    from api.services.runner import _ingest_stdout

    lines = []
    for i in range(505):
        ip = f"10.0.{(i // 256)}.{(i % 256)}"
        line_data = {
            ip: {
                "metadata": {"subrun_id": "sub_test"},
                "ports": {"80": {"tcp_status": "closed"}},
            }
        }
        import json
        lines.append((json.dumps(line_data) + "\n").encode("utf-8"))

    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(side_effect=lines + [b""])

    mock_process = MagicMock()
    mock_process.stdout = mock_stdout

    calls = []

    def mock_bulk_upsert(run_id, batch):
        calls.append((run_id, len(batch)))

    with patch("api.services.runner._bulk_upsert_deltas_sync", side_effect=mock_bulk_upsert):
        await _ingest_stdout("run_test_batch", mock_process)

    assert len(calls) == 2, f"Expected 2 batch calls (500 + 5), got {len(calls)}"
    assert calls[0] == ("run_test_batch", 500)
    assert calls[1] == ("run_test_batch", 5)



