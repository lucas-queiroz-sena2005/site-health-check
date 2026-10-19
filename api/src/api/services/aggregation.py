from collections import defaultdict

from api.models import HostState


def aggregate_void_nodes(
    ip_states: list[HostState],
    historical_active_ips: set[str]
) -> list[HostState]:
    """
    Excludes Void IPs from the host states.
    Void IPs are those that have NO open ports in the current job AND are not in historical_active_ips.
    """
    kept_ips: list[HostState] = []

    for ip in ip_states:
        if ip.ip_address.startswith("Void"):
            continue
        has_open = any(p.tcp_status == "open" for p in ip.ports_list)
        if has_open or ip.ip_address in historical_active_ips:
            kept_ips.append(ip)

    return kept_ips

