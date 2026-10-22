from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
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
    mute_url: str | None = None,
    finding_codes: list[str] | set[str] | None = None,
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
        mute_url: Optional URL to turn off alerts for this schedule.
        finding_codes: Optional canonical finding codes detected during evaluation.

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
    void_cnt = summary_stats.get("void", 0)

    summary_text = (
        f"Active: {active_cnt} | Warning: {warning_cnt} | "
        f"Failed: {failed_cnt} | Ghost: {ghost_cnt} | Void: {void_cnt}"
    )

    is_https = table_url.startswith("https://")
    link_html = f"<a href='{table_url}'>View Results Table</a>"
    if mute_url:
        link_html += f"<br><a href='{mute_url}'>Turn Off Alerts for this Schedule</a>"

    body_lines = [
        f"<b>Status:</b> <font color='{status_color}'>{status_label}</font>",
        f"<b>Schedule:</b> {schedule_name}",
        f"<b>Run:</b> {run_id[:8]}",
        f"<b>Time:</b> {timestamp_str}",
        f"<b>Triggers:</b> {trigger_text}",
        f"<b>Summary:</b> {summary_text}",
    ]

    if finding_codes:
        distinct_findings = ", ".join(sorted(set(finding_codes)))
        body_lines.append(f"<b>Findings:</b> {distinct_findings}")

    body_lines.extend(["", link_html])

    widgets: list[dict[str, Any]] = [
        {"textParagraph": {"text": "<br>".join(body_lines)}}
    ]

    if is_https:
        buttons = [
            {
                "text": "View Results Table",
                "onClick": {"openLink": {"url": table_url}},
            }
        ]
        if mute_url:
            buttons.append(
                {
                    "text": "Turn Off Alerts",
                    "onClick": {"openLink": {"url": mute_url}},
                }
            )
        widgets.append({"buttonList": {"buttons": buttons}})

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
    mute_url: str | None = None,
    finding_codes: list[str] | set[str] | None = None,
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
        mute_url: Optional URL to turn off alerts for this schedule.
        finding_codes: Optional canonical finding codes detected during evaluation.

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
    void_cnt = summary_stats.get("void", 0)

    summary_text = (
        f"Active: {active_cnt} | Warning: {warning_cnt} | "
        f"Failed: {failed_cnt} | Ghost: {ghost_cnt} | Void: {void_cnt}"
    )

    action_elements = [
        {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": "View Results Table",
            },
            "url": table_url,
            "style": "primary" if is_healthy else "danger",
        }
    ]
    if mute_url:
        action_elements.append(
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Turn Off Alerts",
                },
                "url": mute_url,
            }
        )

    findings_text = ""
    if finding_codes:
        distinct_findings = ", ".join(sorted(set(finding_codes)))
        findings_text = f"\n*Findings:* `{distinct_findings}`"

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
                    f"{findings_text}"
                ),
            },
        },
        {
            "type": "actions",
            "elements": action_elements,
        },
    ]

    return {
        "text": f"{title} - {schedule_name}",
        "blocks": blocks,
    }


def build_mute_status_payload(
    webhook_url: str,
    schedule_name: str,
    is_muted: bool,
    mute_url: str | None = None,
    unmute_url: str | None = None,
) -> dict[str, Any]:
    """Constructs notification payload for mute/unmute status changes.

    Args:
        webhook_url: Target URL for the incoming webhook.
        schedule_name: Name of the scheduled scan.
        is_muted: True if alerts were muted, False if resumed.
        mute_url: Direct URL to mute alerts.
        unmute_url: Direct URL to unmute alerts.

    Returns:
        Formatted payload dict for Google Chat, Slack, or generic fallback.
    """
    if "chat.googleapis.com" in webhook_url:
        title = f"Alerts Muted: {schedule_name}" if is_muted else f"Alerts Active: {schedule_name}"
        desc = (
            f"Automated alerts for schedule <b>{schedule_name}</b> have been turned off."
            if is_muted
            else f"Automated alerts for schedule <b>{schedule_name}</b> have been resumed."
        )
        action_link = (
            f"<a href='{unmute_url}'>Turn Back On Alerts for this Schedule</a>"
            if is_muted and unmute_url
            else (f"<a href='{mute_url}'>Turn Off Alerts for this Schedule</a>" if not is_muted and mute_url else "")
        )
        button_text = "Turn Back On" if is_muted else "Turn Off Alerts"
        button_url = unmute_url if is_muted else mute_url

        body_lines = [desc]
        if action_link:
            body_lines.append("")
            body_lines.append(action_link)

        widgets: list[dict[str, Any]] = [
            {"textParagraph": {"text": "<br>".join(body_lines)}}
        ]

        if button_url and button_url.startswith("https://"):
            widgets.append(
                {
                    "buttonList": {
                        "buttons": [
                            {
                                "text": button_text,
                                "onClick": {"openLink": {"url": button_url}},
                            }
                        ]
                    }
                }
            )

        return {
            "cardsV2": [
                {
                    "cardId": f"mute-status-{schedule_name.lower().replace(' ', '-')}",
                    "card": {
                        "header": {
                            "title": title,
                            "subtitle": f"{schedule_name} | Quick Controls",
                        },
                        "sections": [{"widgets": widgets}],
                    },
                }
            ]
        }
    elif "hooks.slack.com" in webhook_url:
        title = f"Alerts Muted: {schedule_name}" if is_muted else f"Alerts Active: {schedule_name}"
        desc = (
            f"Automated alerts for schedule *{schedule_name}* have been turned off."
            if is_muted
            else f"Automated alerts for schedule *{schedule_name}* have been resumed."
        )
        btn_text = "Turn Back On" if is_muted else "Turn Off Alerts"
        btn_url = unmute_url if is_muted else mute_url

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": desc}},
        ]
        if btn_url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": btn_text},
                            "url": btn_url,
                        }
                    ],
                }
            )
        return {
            "text": f"{title} - {desc}",
            "blocks": blocks,
        }
    else:
        desc = (
            f"Automated alerts for schedule {schedule_name} have been turned off."
            if is_muted
            else f"Automated alerts for schedule {schedule_name} have been resumed."
        )
        url = unmute_url if is_muted else mute_url
        msg = f"{desc}\nAction: {url}" if url else desc
        return {
            "text": msg,
            "schedule_name": schedule_name,
            "is_muted": is_muted,
            "url": url,
        }


async def dispatch_mute_status_notification(scan: Scan, is_muted: bool) -> bool:
    """Dispatches an automated confirmation notification when alerts are muted or unmuted.

    Args:
        scan: The Scan instance whose alert state was toggled.
        is_muted: The new muted state (True if muted, False if active/unmuted).

    Returns:
        True if notification was successfully sent, False otherwise.
    """
    if not scan.alert_config_json:
        return False

    webhook_url = scan.alert_config_json.get("webhook_url")
    if not webhook_url:
        return False

    mute_url = f"{settings.app_base_url}/api/scans/{scan.id}/alerts/mute"
    unmute_url = f"{settings.app_base_url}/api/scans/{scan.id}/alerts/unmute"

    payload = build_mute_status_payload(
        webhook_url=webhook_url,
        schedule_name=scan.name,
        is_muted=is_muted,
        mute_url=mute_url,
        unmute_url=unmute_url,
    )

    success, err = await dispatch_webhook(webhook_url, payload)
    if success:
        logger.info(
            f"Mute status notification ({'muted' if is_muted else 'resumed'}) "
            f"dispatched for scan {scan.id} to {webhook_url}"
        )
    else:
        logger.warning(
            f"Failed to dispatch mute status notification for scan {scan.id}: {err}"
        )
    return success


def build_alert_payload(
    webhook_url: str,
    schedule_name: str,
    run_id: str,
    timestamp_str: str,
    triggers: list[str],
    summary_stats: dict[str, int],
    table_url: str,
    is_healthy: bool = False,
    mute_url: str | None = None,
    finding_codes: list[str] | set[str] | None = None,
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
        mute_url: Optional URL to turn off alerts for this schedule.
        finding_codes: Optional canonical finding codes detected during evaluation.

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
            mute_url=mute_url,
            finding_codes=finding_codes,
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
            mute_url=mute_url,
            finding_codes=finding_codes,
        )
    else:
        title = "Scan: Healthy" if is_healthy else "Scan: Issues Detected"
        status_label = "Healthy" if is_healthy else "Issues Detected"
        trigger_text = ", ".join(triggers) if triggers else "None"
        summary_text = (
            f"Active: {summary_stats.get('active', 0)} | "
            f"Warning: {summary_stats.get('warning', 0)} | "
            f"Failed: {summary_stats.get('failed', 0)} | "
            f"Ghost: {summary_stats.get('ghost', 0)} | "
            f"Void: {summary_stats.get('void', 0)}"
        )
        msg_lines = [
            title,
            f"Status: {status_label}",
            f"Schedule: {schedule_name}",
            f"Run ID: {run_id[:8]}",
            f"Time: {timestamp_str}",
            f"Triggers: {trigger_text}",
            f"Summary: {summary_text}",
        ]
        if finding_codes:
            distinct_findings = ", ".join(sorted(set(finding_codes)))
            msg_lines.append(f"Findings: {distinct_findings}")
        msg_lines.append(f"Link: {table_url}")
        if mute_url:
            msg_lines.append(f"Mute Alerts: {mute_url}")

        payload: dict[str, Any] = {
            "text": "\n".join(msg_lines),
            "schedule_name": schedule_name,
            "run_id": run_id,
            "triggers": triggers,
            "summary": summary_stats,
            "table_url": table_url,
            "is_healthy": is_healthy,
            "mute_url": mute_url,
        }
        if finding_codes:
            payload["findings"] = sorted(set(finding_codes))
        return payload


@dataclass(frozen=True)
class TriggerContext:
    """Evaluation context passed to trigger rule functions."""

    alert_config: AlertConfig
    run_status: ScanRunStatus
    summary_stats: dict[str, int]
    finding_codes: set[str]


TriggerRule = Callable[[TriggerContext], list[str]]


def rule_run_aborted_or_failed(ctx: TriggerContext) -> list[str]:
    """Triggers when a run fails or is aborted if alert_on_abort is active."""
    if ctx.alert_config.alert_on_abort and ctx.run_status in (
        ScanRunStatus.FAILED,
        ScanRunStatus.ABORTED,
    ):
        return ["Scan Run Aborted/Failed"]
    return []


def rule_service_failures(ctx: TriggerContext) -> list[str]:
    """Triggers when failed services exist and alert_on_failure is active."""
    if ctx.alert_config.alert_on_failure and ctx.summary_stats.get("failed", 0) > 0:
        return [f"{ctx.summary_stats['failed']} Service Failures"]
    return []


def rule_ghost_hosts(ctx: TriggerContext) -> list[str]:
    """Triggers when ghost hosts are discovered and alert_on_ghost is active."""
    if ctx.alert_config.alert_on_ghost and ctx.summary_stats.get("ghost", 0) > 0:
        return [f"{ctx.summary_stats['ghost']} Ghost Hosts"]
    return []


def rule_warnings(ctx: TriggerContext) -> list[str]:
    """Triggers when warning hosts exist and alert_on_warning is active."""
    if ctx.alert_config.alert_on_warning and ctx.summary_stats.get("warning", 0) > 0:
        return [f"{ctx.summary_stats['warning']} Warnings (TLS/Redirects)"]
    return []


def rule_void_hosts(ctx: TriggerContext) -> list[str]:
    """Triggers when void hosts exist and alert_on_void is active."""
    if ctx.alert_config.alert_on_void and ctx.summary_stats.get("void", 0) > 0:
        return [f"{ctx.summary_stats['void']} Void Hosts"]
    return []


def rule_finding_codes(ctx: TriggerContext) -> list[str]:
    """Enriches notification triggers with specific canonical finding codes."""
    if (
        ctx.alert_config.alert_on_failure or ctx.alert_config.alert_on_warning
    ) and ctx.finding_codes:
        formatted = ", ".join(sorted(ctx.finding_codes))
        return [f"Findings: {formatted}"]
    return []


DEFAULT_TRIGGER_RULES: list[TriggerRule] = [
    rule_run_aborted_or_failed,
    rule_service_failures,
    rule_ghost_hosts,
    rule_warnings,
    rule_void_hosts,
    rule_finding_codes,
]


def evaluate_alert_triggers(
    alert_config: AlertConfig,
    run_status: ScanRunStatus,
    summary_stats: dict[str, int],
    finding_codes: list[str] | set[str] | None = None,
    rules: list[TriggerRule] | None = None,
) -> tuple[bool, list[str], bool]:
    """Evaluates whether the run triggers an alert based on alert_config and findings.

    Args:
        alert_config: Notification configuration with enabled trigger flags.
        run_status: Terminal status of the scan run.
        summary_stats: Counts of active, warning, failed, ghost, void hosts.
        finding_codes: Optional canonical finding codes detected during evaluation.
        rules: Optional custom trigger rules to evaluate (defaults to DEFAULT_TRIGGER_RULES).

    Returns:
        Tuple of (should_send, trigger_descriptions, is_healthy).
    """
    ctx = TriggerContext(
        alert_config=alert_config,
        run_status=run_status,
        summary_stats=summary_stats,
        finding_codes=set(finding_codes or []),
    )

    active_rules = rules if rules is not None else DEFAULT_TRIGGER_RULES
    triggers: list[str] = []
    for rule in active_rules:
        triggers.extend(rule(ctx))

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
    void_count: int | None = None,
) -> dict[str, int]:
    """Returns active, warning, failed, ghost, and void counts for a run.

    Reads pre-computed summary metrics stored on the run's metrics_json by evaluator.py.
    If metrics_json summary is not yet populated (e.g. unfinalized test fixtures),
    delegates to evaluator.evaluate_scan_run as the single source of truth.
    """
    if (
        run.metrics_json
        and isinstance(run.metrics_json, dict)
        and "summary" in run.metrics_json
    ):
        summary_data = run.metrics_json["summary"]
        if isinstance(summary_data, dict):
            return {
                "active": int(summary_data.get("active", 0)),
                "warning": int(summary_data.get("warning", 0)),
                "failed": int(summary_data.get("failed", 0)),
                "ghost": int(summary_data.get("ghost", 0)),
                "void": int(
                    void_count
                    if void_count is not None
                    else summary_data.get("void", 0)
                ),
            }

    from api.services.evaluator import evaluate_scan_run

    return evaluate_scan_run(
        run.id,
        session,
        void_count=void_count,
        ghost_window_override=ghost_window_str,
        tls_warning_days_override=tls_warning_days,
    )


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
    if not scan or not scan.alert_config_json or scan.alerts_muted:
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

    # Collect distinct finding codes from HostState for this run
    stmt_findings = select(HostState.finding_codes).where(HostState.scan_run_id == run.id)
    raw_findings = session.exec(stmt_findings).all()
    distinct_finding_codes: set[str] = set()
    for f_list in raw_findings:
        if f_list and isinstance(f_list, list):
            distinct_finding_codes.update(f_list)

    should_send, triggers, is_healthy = evaluate_alert_triggers(
        alert_config=alert_config,
        run_status=run.status,
        summary_stats=summary,
        finding_codes=distinct_finding_codes,
    )

    if not should_send:
        return

    timestamp_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    table_url = f"{settings.app_base_url}/?run={run.id}"

    mute_url = f"{settings.app_base_url}/api/scans/{scan.id}/alerts/mute"

    payload = build_alert_payload(
        webhook_url=alert_config.webhook_url,
        schedule_name=scan.name,
        run_id=run.id,
        timestamp_str=timestamp_str,
        triggers=triggers,
        summary_stats=summary,
        table_url=table_url,
        is_healthy=is_healthy,
        mute_url=mute_url,
        finding_codes=distinct_finding_codes,
    )

    success, err = await dispatch_webhook(alert_config.webhook_url, payload)
    if success:
        logger.info(
            f"Alert successfully dispatched for run {run.id} to "
            f"{alert_config.webhook_url}"
        )
    else:
        logger.warning(f"Alert dispatch failed for run {run.id}: {err}")
