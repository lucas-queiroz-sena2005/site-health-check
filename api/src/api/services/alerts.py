import logging
from datetime import UTC, datetime, timedelta
import re
from typing import Any

import httpx
from sqlmodel import Session, col, func, select

from api.config import settings
from api.models import (
    AlertConfig,
    HostState,
    HttpRoutingCheck,
    PortState,
    Scan,
    ScanRun,
    ScanRunStatus,
)

logger = logging.getLogger(__name__)


def build_google_chat_card(
    schedule_name: str,
    run_id: str,
    timestamp_str: str,
    triggers: list[str],
    summary_stats: dict[str, int],
    table_url: str,
    is_healthy: bool = False,
) -> dict[str, Any]:
    title = "🟢 Scan Complete: All Healthy" if is_healthy else "🔴 Alert: Scan Issues Detected"
    trigger_text = ", ".join(triggers) if triggers else "None"
    summary_text = (
        f"Active: {summary_stats.get('active', 0)} | "
        f"Warning: {summary_stats.get('warning', 0)} | "
        f"Failed: {summary_stats.get('failed', 0)} | "
        f"Ghost: {summary_stats.get('ghost', 0)} | "
        f"Void: {summary_stats.get('void', 0)}"
    )

    widgets = [
        {"decoratedText": {"topLabel": "Schedule", "text": schedule_name}},
        {"decoratedText": {"topLabel": "Run ID", "text": run_id}},
        {"decoratedText": {"topLabel": "Time", "text": timestamp_str}},
        {"decoratedText": {"topLabel": "Trigger", "text": trigger_text}},
        {"decoratedText": {"topLabel": "Summary", "text": summary_text}},
        {
            "buttonList": {
                "buttons": [
                    {
                        "text": "View Results Table",
                        "onClick": {"openLink": {"url": table_url}},
                    }
                ]
            }
        },
    ]

    return {
        "cardsV2": [
            {
                "cardId": f"alert-{run_id}",
                "card": {
                    "header": {
                        "title": title,
                        "subtitle": f"Schedule: {schedule_name}",
                    },
                    "sections": [{"widgets": widgets}],
                },
            }
        ]
    }


def build_slack_blocks(
    schedule_name: str,
    run_id: str,
    timestamp_str: str,
    triggers: list[str],
    summary_stats: dict[str, int],
    table_url: str,
    is_healthy: bool = False,
) -> dict[str, Any]:
    title = "🟢 Scan Complete: All Healthy" if is_healthy else "🔴 Alert: Scan Issues Detected"
    trigger_text = ", ".join(triggers) if triggers else "None"
    summary_text = (
        f"Active: {summary_stats.get('active', 0)} | "
        f"Warning: {summary_stats.get('warning', 0)} | "
        f"Failed: {summary_stats.get('failed', 0)} | "
        f"Ghost: {summary_stats.get('ghost', 0)} | "
        f"Void: {summary_stats.get('void', 0)}"
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Schedule:*\n{schedule_name}"},
                {"type": "mrkdwn", "text": f"*Run ID:*\n`{run_id}`"},
                {"type": "mrkdwn", "text": f"*Time:*\n{timestamp_str}"},
                {"type": "mrkdwn", "text": f"*Trigger:*\n{trigger_text}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary:*\n{summary_text}"},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Results Table"},
                    "url": table_url,
                    "style": "primary",
                }
            ],
        },
    ]

    return {
        "text": f"{title} - {schedule_name}",
        "blocks": blocks,
    }


def build_alert_payload(
    webhook_url: str,
    schedule_name: str,
    run_id: str,
    timestamp_str: str,
    triggers: list[str],
    summary_stats: dict[str, int],
    table_url: str,
    is_healthy: bool = False,
) -> dict[str, Any]:
    if "chat.googleapis.com" in webhook_url:
        return build_google_chat_card(
            schedule_name=schedule_name,
            run_id=run_id,
            timestamp_str=timestamp_str,
            triggers=triggers,
            summary_stats=summary_stats,
            table_url=table_url,
            is_healthy=is_healthy,
        )
    elif "hooks.slack.com" in webhook_url:
        return build_slack_blocks(
            schedule_name=schedule_name,
            run_id=run_id,
            timestamp_str=timestamp_str,
            triggers=triggers,
            summary_stats=summary_stats,
            table_url=table_url,
            is_healthy=is_healthy,
        )
    else:
        title = "🟢 Scan Complete: All Healthy" if is_healthy else "🔴 Alert: Scan Issues Detected"
        return {
            "text": f"{title}\nSchedule: {schedule_name}\nRun ID: {run_id}\nTriggers: {', '.join(triggers)}\nLink: {table_url}",
            "schedule_name": schedule_name,
            "run_id": run_id,
            "triggers": triggers,
            "summary": summary_stats,
            "table_url": table_url,
            "is_healthy": is_healthy,
        }


def evaluate_alert_triggers(
    alert_config: AlertConfig,
    run_status: ScanRunStatus,
    summary_stats: dict[str, int],
) -> tuple[bool, list[str], bool]:
    triggers: list[str] = []

    if alert_config.alert_on_abort and run_status in (
        ScanRunStatus.FAILED,
        ScanRunStatus.ABORTED,
    ):
        triggers.append("Scan Run Aborted/Failed")

    if alert_config.alert_on_failure and summary_stats.get("failed", 0) > 0:
        triggers.append(f"{summary_stats['failed']} Service Failures")

    if alert_config.alert_on_ghost and summary_stats.get("ghost", 0) > 0:
        triggers.append(f"{summary_stats['ghost']} Ghost Hosts")

    if alert_config.alert_on_warning and summary_stats.get("warning", 0) > 0:
        triggers.append(f"{summary_stats['warning']} Warnings (TLS/Redirects)")

    if triggers:
        return (True, triggers, False)

    # If no failure/warning triggers activated, check if healthy notification is enabled
    is_healthy = summary_stats.get("failed", 0) == 0 and summary_stats.get("ghost", 0) == 0
    if alert_config.notify_on_healthy and is_healthy:
        return (True, ["All checks passed successfully"], True)

    return (False, [], True)


async def dispatch_webhook(
    webhook_url: str, payload: dict[str, Any]
) -> tuple[bool, str | None]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.is_success:
                return (True, None)
            return (False, f"HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"Failed to dispatch alert webhook to {webhook_url}: {e}")
        return (False, str(e))


def compute_run_summary(
    session: Session,
    run: ScanRun,
    ghost_window_str: str = "7d",
    tls_warning_days: int = 30,
) -> dict[str, int]:
    statement = select(HostState).where(HostState.scan_run_id == run.id)
    hosts = session.exec(statement).all()

    active_count = 0
    warning_count = 0
    failed_count = 0

    for h in hosts:
        host_has_open = False
        host_has_failed = False
        host_has_warning = False

        for port in h.ports:
            if port.tcp_status == "open":
                host_has_open = True
            elif port.tcp_status in ("closed", "filtered", "error"):
                host_has_failed = True

            # Check TLS
            if port.tls_certificate:
                valid = port.tls_certificate.valid
                exp_days = port.tls_certificate.expires_in_days
                if not valid or (exp_days is not None and exp_days <= tls_warning_days):
                    host_has_warning = True

            # Check HTTP
            for http in port.http_routing_checks:
                if http.status_code and http.status_code >= 400:
                    host_has_failed = True

        if host_has_failed:
            failed_count += 1
        elif host_has_warning:
            warning_count += 1
        elif host_has_open:
            active_count += 1

    # Ghost count calculation
    ghost_count = 0
    match = re.fullmatch(r"^(\d+)([smhd])$", ghost_window_str.strip().lower())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        units = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}
        delta = timedelta(**{units[unit]: amount})
        cutoff = datetime.now(UTC) - delta

        current_active_ips = {h.ip_address for h in hosts if any(p.tcp_status == "open" for p in h.ports)}
        target_ips = [h.ip_address for h in hosts]
        if target_ips:
            historical_stmt = (
                select(HostState.ip_address)
                .join(PortState, col(HostState.id) == col(PortState.host_state_id))
                .join(ScanRun, col(HostState.scan_run_id) == col(ScanRun.id))
                .where(PortState.tcp_status == "open")
                .where(col(ScanRun.started_at) >= cutoff)
                .where(ScanRun.status == ScanRunStatus.COMPLETED)
                .where(col(HostState.ip_address).in_(target_ips))
                .distinct()
            )
            historical_active = set(session.exec(historical_stmt).all())
            ghost_ips = historical_active - current_active_ips
            ghost_count = len(ghost_ips)

    return {
        "active": active_count,
        "warning": warning_count,
        "failed": failed_count,
        "ghost": ghost_count,
        "void": 0,
    }


async def evaluate_and_dispatch_alert(run_id: str, session: Session) -> None:
    run = session.get(ScanRun, run_id)
    if not run or not run.scan_id:
        return

    scan = session.get(Scan, run.scan_id)
    if not scan or not scan.alert_config_json:
        return

    try:
        alert_config = AlertConfig.model_validate(scan.alert_config_json)
    except Exception as e:
        logger.error(f"Invalid alert config on scan {scan.id}: {e}")
        return

    if not alert_config.webhook_url:
        return

    summary = compute_run_summary(
        session=session,
        run=run,
        ghost_window_str=scan.ghost_window or "7d",
        tls_warning_days=scan.tls_warning_days or 30,
    )

    should_send, triggers, is_healthy = evaluate_alert_triggers(
        alert_config=alert_config,
        run_status=run.status,
        summary_stats=summary,
    )

    if not should_send:
        return

    timestamp_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    table_url = f"{settings.app_base_url}/#/?run_id={run.id}"

    payload = build_alert_payload(
        webhook_url=alert_config.webhook_url,
        schedule_name=scan.name,
        run_id=run.id,
        timestamp_str=timestamp_str,
        triggers=triggers,
        summary_stats=summary,
        table_url=table_url,
        is_healthy=is_healthy,
    )

    success, err = await dispatch_webhook(alert_config.webhook_url, payload)
    if success:
        logger.info(f"Alert successfully dispatched for run {run.id} to {alert_config.webhook_url}")
    else:
        logger.warning(f"Alert dispatch failed for run {run.id}: {err}")
