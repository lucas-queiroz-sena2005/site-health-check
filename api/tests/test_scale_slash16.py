import time
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from api.models import (
    EntityStatus,
    HostState,
    HttpRoutingCheck,
    PortState,
    Scan,
    ScanRun,
    ScanRunStatus,
    TlsCertificate,
)
from api.services.evaluator import evaluate_scan_run
from api.services.runner import _bulk_upsert_deltas_sync, _finalize_run


@pytest.fixture(name="scale_engine")
def scale_engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_slash16_end_to_end_scale_and_pruning(scale_engine):
    """Benchmark full /16 (65,536 IPs) batched ingestion, evaluation, pruning, and ghost diffing."""
    with patch("api.services.runner.db_engine", scale_engine):
        start_time = time.perf_counter()

        run_id = str(uuid.uuid4())
        TOTAL_TARGETS = 65536
        ACTIVE_TARGETS = 36  # First 36 IPs are active web services
        BATCH_SIZE = 500

        with Session(scale_engine) as session:
            scan = Scan(
                id="slash16-test-scan",
                name="Slash16 Scan",
                targets=["10.0.0.0/16"],
                ports_json=[80, 443],
                flags_json={},
            )
            session.add(scan)
            run = ScanRun(
                id=run_id,
                scan_id=scan.id,
                status=ScanRunStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
                execution_config_snapshot_json={
                    "prune_void_hosts": True,
                    "prune_closed_ports": True,
                    "ghost_window": "7d",
                    "tls_warning_days": 30,
                },
            )
            session.add(run)
            session.commit()

        # Generate 65,536 deltas in micro-batches
        current_batch = []
        for i in range(TOTAL_TARGETS):
            b_octet = i // 256
            c_octet = i % 256
            ip = f"10.0.{b_octet}.{c_octet}"

            if i < ACTIVE_TARGETS:
                # Responsive web host
                delta_data = {
                    "metadata": {
                        "resolved_domains": [f"app-{i}.internal"],
                        "discovered_from": ["10.0.0.1"],
                        "subrun_id": "10.0.0.0/16",
                    },
                    "ports": {
                        "80": {"tcp_status": "open", "tcp_latency_ms": 12},
                        "443": {
                            "tcp_status": "open",
                            "tcp_latency_ms": 15,
                            "tls_certificate": {
                                "valid": True,
                                "expires_in_days": 45,
                                "issuer": "Corp CA",
                                "protocol_version": "TLSv1.3",
                                "domains_discovered_sans": [f"app-{i}.internal"],
                            },
                            "http_routing_checks": {
                                f"app-{i}.internal": {
                                    "status_code": 200,
                                    "http_latency_ms": 35,
                                    "path_checked": "/",
                                    "server_header": "envoy",
                                }
                            },
                        },
                        "8080": {"tcp_status": "closed", "tcp_latency_ms": None},
                    },
                }
            else:
                # Routine closed / non-responsive host
                delta_data = {
                    "metadata": {
                        "subrun_id": "10.0.0.0/16",
                    },
                    "ports": {
                        "80": {"tcp_status": "closed", "tcp_latency_ms": None},
                        "443": {"tcp_status": "closed", "tcp_latency_ms": None},
                    },
                }

            current_batch.append((ip, delta_data))
            if len(current_batch) >= BATCH_SIZE:
                _bulk_upsert_deltas_sync(run_id, current_batch)
                current_batch = []

        if current_batch:
            _bulk_upsert_deltas_sync(run_id, current_batch)
            current_batch = []

        ingestion_elapsed = time.perf_counter() - start_time

        # Finalize and evaluate run
        eval_start = time.perf_counter()
        _finalize_run(run_id, 0)
        eval_elapsed = time.perf_counter() - eval_start
        total_elapsed = time.perf_counter() - start_time

        print(f"\n[/16 Benchmark] Ingestion: {ingestion_elapsed:.2f}s | Evaluation & Pruning: {eval_elapsed:.2f}s | Total: {total_elapsed:.2f}s")

        with Session(scale_engine) as session:
            final_run = session.get(ScanRun, run_id)
            assert final_run.status == ScanRunStatus.COMPLETED

            summary = final_run.metrics_json["summary"]
            assert summary["active"] == ACTIVE_TARGETS
            assert summary["void"] == (TOTAL_TARGETS - ACTIVE_TARGETS)
            assert summary["ghost"] == 0
            assert summary["warning"] == 0
            assert summary["failed"] == 0
            # 36 active hosts * 2 open ports (80 and 443) = 72 services
            assert summary["service_count"] == ACTIVE_TARGETS * 2
            assert summary["http_check_count"] == ACTIVE_TARGETS

            # Verify that all 65,500 void hosts were pruned from SQLite
            remaining_hosts = session.exec(
                select(HostState).where(HostState.scan_run_id == run_id)
            ).all()
            assert len(remaining_hosts) == ACTIVE_TARGETS

            # Verify routine closed port 8080 was pruned from each active host, but ports 80 & 443 kept
            for h in remaining_hosts:
                ports = session.exec(
                    select(PortState).where(PortState.host_state_id == h.id)
                ).all()
                assert len(ports) == 2
                port_nums = {p.port_number for p in ports}
                assert port_nums == {80, 443}
                # Scanned port count must still reflect that 3 ports were probed
                assert h.scanned_port_count == 3
                assert h.open_port_count == 2

        # Step 2: Run a subsequent scan run where 5 previously active hosts are now offline (Ghost detection test)
        run2_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with Session(scale_engine) as session:
            run2 = ScanRun(
                id=run2_id,
                scan_id="slash16-test-scan",
                status=ScanRunStatus.RUNNING,
                started_at=now,
                execution_config_snapshot_json={
                    "prune_void_hosts": True,
                    "prune_closed_ports": True,
                    "ghost_window": "7d",
                },
            )
            session.add(run2)
            session.commit()

        # In run 2, only test the 36 IPs from run 1: first 31 are active, last 5 are closed (ghosts)
        run2_deltas = []
        for i in range(ACTIVE_TARGETS):
            b_octet = i // 256
            c_octet = i % 256
            ip = f"10.0.{b_octet}.{c_octet}"
            if i < 31:
                # Still active
                d = {
                    "metadata": {"subrun_id": "test"},
                    "ports": {"80": {"tcp_status": "open"}},
                }
            else:
                # Went offline (historical ghost)
                d = {
                    "metadata": {"subrun_id": "test"},
                    "ports": {
                        "80": {"tcp_status": "closed"},
                        "443": {"tcp_status": "closed"},
                    },
                }
            run2_deltas.append((ip, d))

        _bulk_upsert_deltas_sync(run2_id, run2_deltas)
        _finalize_run(run2_id, 0)

        with Session(scale_engine) as session:
            final_run2 = session.get(ScanRun, run2_id)
            summary2 = final_run2.metrics_json["summary"]
            assert summary2["active"] == 31
            assert summary2["ghost"] == 5, "5 hosts that went offline must be classified as ghosts"
            assert summary2["void"] == 0

            # Verify ghost hosts are NOT pruned
            run2_hosts = session.exec(
                select(HostState).where(HostState.scan_run_id == run2_id)
            ).all()
            assert len(run2_hosts) == 36
            ghost_hosts = [h for h in run2_hosts if h.status == EntityStatus.GHOST]
            assert len(ghost_hosts) == 5

        # Assert performance constraint: ingestion + eval of /16 completes within budget
        assert total_elapsed < 10.0, f"Expected total run under 10s, took {total_elapsed:.2f}s"
