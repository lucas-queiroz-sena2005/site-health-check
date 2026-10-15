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
    """Constructs a professional Google Chat Cards v2 webhook payload.

    Args:
        schedule_name: Name of the scheduled scan.
        run_id: Unique identifier for the scan run.
        timestamp_str: Formatted UTC timestamp string.
        triggers: List of reasons triggering the notification.
        summary_stats: Counts of active, warning, failed, ghost, void hosts.
        table_url: Deep-link URL to the host results table.
        is_healthy: Whether the run completed with all checks healthy.

    Returns:
        Dictionary representation of the Cards v2 payload.
    """
    title = "Scan: Healthy" if is_healthy else "Scan: Issues Detected"
    status_label = "Healthy" if is_healthy else "Issues Detected"
    status_color = "#137333" if is_healthy else "#c5221f"
    trigger_text = ", ".join(triggers) if triggers else "None"

    active_cnt = summary_stats.get("active", 0)
    warning_cnt = summary_stats.get("warning", 0)
    failed_cnt = summary_stats.get("failed", 0)
    ghost_cnt = summary_stats.get("ghost", 0)

    summary_text = (
        f"Active: {active_cnt} | Warning: {warning_cnt} | "
        f"Failed: {failed_cnt} | Ghost: {ghost_cnt}"
    )

    is_https = table_url.startswith("https://")
    link_html = f"<a href='{table_url}'>View Results Table</a>"

    body_lines = [
        f"<b>Status:</b> <font color='{status_color}'>{status_label}</font>",
        f"<b>Schedule:</b> {schedule_name}",
        f"<b>Run:</b> {run_id[:8]}",
        f"<b>Time:</b> {timestamp_str}",
        f"<b>Triggers:</b> {trigger_text}",
        f"<b>Summary:</b> {summary_text}",
    ]

    widgets: list[dict[str, Any]] = []

    if is_https:
        widgets.append({"textParagraph": {"text": "<br>".join(body_lines)}})
        widgets.append(
            {
                "buttonList": {
                    "buttons": [
                        {
                            "text": "View Results Table",
                            "onClick": {"openLink": {"url": table_url}},
                        }
                    ]
                }
            }
        )
    else:
        # In Google Chat Cards v2, openLink buttons strictly require HTTPS.
        # HTTP URLs are rejected by Google Chat button handlers and do nothing.
        # We render a direct HTML hyperlink instead of a non-functional button.
        body_lines.append("")
        body_lines.append(link_html)
        widgets.append({"textParagraph": {"text": "<br>".join(body_lines)}})

    return {
        "cardsV2": [
            {
                "cardId": f"alert-{run_id}",
                "card": {
                    "header": {
                        "title": title,
                        "subtitle": f"{schedule_name} | Run: {run_id[:8]}",
                    },
                    "sections": [
                        {
                            "widgets": widgets,
                        }
                    ],
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
    """Constructs a clean Slack Block Kit webhook payload.

    Args:
        schedule_name: Name of the scheduled scan.
        run_id: Unique identifier for the scan run.
        timestamp_str: Formatted UTC timestamp string.
        triggers: List of reasons triggering the notification.
        summary_stats: Counts of active, warning, failed, ghost, void hosts.
        table_url: Deep-link URL to the host results table.
        is_healthy: Whether the run completed with all checks healthy.

    Returns:
        Dictionary representation of the Slack Block Kit payload.
    """
    title = "Scan: Healthy" if is_healthy else "Scan: Issues Detected"
    status_label = "Healthy" if is_healthy else "Issues Detected"
    trigger_text = ", ".join(triggers) if triggers else "None"

    active_cnt = summary_stats.get("active", 0)
    warning_cnt = summary_stats.get("warning", 0)
    failed_cnt = summary_stats.get("failed", 0)
    ghost_cnt = summary_stats.get("ghost", 0)

    summary_text = (
        f"Active: {active_cnt} | Warning: {warning_cnt} | "
        f"Failed: {failed_cnt} | Ghost: {ghost_cnt}"
    )

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Status:* {status_label}\n"
                    f"*Schedule:* {schedule_name}\n"
                    f"*Run:* `{run_id[:8]}`\n"
                    f"*Time:* {timestamp_str}\n"
                    f"*Triggers:* {trigger_text}\n"
                    f"*Summary:* {summary_text}"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Results Table",
                    },
                    "url": table_url,
                    "style": "primary" if is_healthy else "danger",
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
    """Builds appropriate alert payload by detecting webhook provider.

    Args:
        webhook_url: Target URL for the incoming webhook.
        schedule_name: Name of the scheduled scan.
        run_id: Unique identifier for the scan run.
        timestamp_str: Formatted UTC timestamp string.
        triggers: List of reasons triggering the notification.
        summary_stats: Counts of active, warning, failed, ghost, void hosts.
        table_url: Deep-link URL to the host results table.
        is_healthy: Whether the run completed with all checks healthy.

    Returns:
        Formatted payload dict for Google Chat, Slack, or generic fallback.
    """
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
        title = "Scan: Healthy" if is_healthy else "Scan: Issues Detected"
        status_label = "Healthy" if is_healthy else "Issues Detected"
        trigger_text = ", ".join(triggers) if triggers else "None"
        summary_text = (
            f"Active: {summary_stats.get('active', 0)} | "
            f"Warning: {summary_stats.get('warning', 0)} | "
            f"Failed: {summary_stats.get('failed', 0)} | "
            f"Ghost: {summary_stats.get('ghost', 0)}"
        )
        msg_lines = [
            title,
            f"Status: {status_label}",
            f"Schedule: {schedule_name}",
            f"Run ID: {run_id[:8]}",
            f"Time: {timestamp_str}",
            f"Triggers: {trigger_text}",
            f"Summary: {summary_text}",
            f"Link: {table_url}",
        ]
        return {
            "text": "\n".join(msg_lines),
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
    """Evaluates whether the run triggers an alert based on alert_config.

    Args:
        alert_config: Notification configuration with enabled trigger flags.
        run_status: Terminal status of the scan run.
        summary_stats: Counts of active, warning, failed, ghost, void hosts.

    Returns:
        Tuple of (should_send, trigger_descriptions, is_healthy).
    """
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

    # Check if healthy notification is enabled
    is_healthy = (
        summary_stats.get("failed", 0) == 0
        and summary_stats.get("ghost", 0) == 0
    )
    if alert_config.notify_on_healthy and is_healthy:
        return (True, [], True)

    return (False, [], True)


async def dispatch_webhook(
    webhook_url: str, payload: dict[str, Any]
) -> tuple[bool, str | None]:
    """Dispatches JSON payload to webhook URL with a 5-second timeout.

    Args:
        webhook_url: Target URL for HTTP POST.
        payload: Body content dict to serialize as JSON.

    Returns:
        Tuple of (success_bool, optional_error_message).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.is_success:
                return (True, None)
            return (False, f"HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(
            f"Failed to dispatch alert webhook to {webhook_url}: {e}"
        )
        return (False, str(e))


def compute_run_summary(
    session: Session,
    run: ScanRun,
    ghost_window_str: str = "7d",
    tls_warning_days: int = 30,
) -> dict[str, int]:
    """Calculates active, warning, failed, ghost, and void counts for a run.

    Args:
        session: Active SQLModel database session.
        run: The ScanRun instance to summarize.
        ghost_window_str: Historical time window string (e.g., '7d', '24h').
        tls_warning_days: Number of days before certificate expiry for warning.

    Returns:
        Dictionary mapping status name to count.
    """
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
                if not valid or (
                    exp_days is not None and exp_days <= tls_warning_days
                ):
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

        current_active_ips = {
            h.ip_address for h in hosts
            if any(p.tcp_status == "open" for p in h.ports)
        }
        target_ips = [h.ip_address for h in hosts]
        if target_ips:
            historical_stmt = (
                select(HostState.ip_address)
                .join(
                    PortState,
                    col(HostState.id) == col(PortState.host_state_id),
                )
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
    """Evaluates scan run results and dispatches webhooks if triggers match.

    Args:
        run_id: ID of the finished ScanRun.
        session: Active SQLModel database session.
    """
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

    # Reuse pre-computed summary stored with run if available
    summary = (run.metrics_json or {}).get("summary")
    if not summary:
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
    table_url = f"{settings.app_base_url}/?run={run.id}"

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
        logger.info(
            f"Alert successfully dispatched for run {run.id} to "
            f"{alert_config.webhook_url}"
        )
    else:
        logger.warning(f"Alert dispatch failed for run {run.id}: {err}")
