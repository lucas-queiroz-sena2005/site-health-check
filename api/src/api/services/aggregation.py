from collections import defaultdict
from api.models import IpState

def aggregate_void_nodes(
    ip_states: list[IpState],
    historical_active_ips: set[str]
) -> list[IpState]:
    """
    Groups Void IPs by metadata_resolved_from and replaces them with a single synthetic Void node.
    Void IPs are those that have NO open ports in the current job AND are not in historical_active_ips.
    """
    # Track which IPs are Void per parent
    void_counts: dict[str, int] = defaultdict(int)
    
    # Store the non-void (Active/Ghost) IPs to return as-is
    kept_ips: list[IpState] = []
    
    for ip in ip_states:
        # Determine if IP has any open ports in the current job
        has_open = any(p.tcp_status == "open" for p in ip.ports_list)
        
        if has_open:
            # It's an Active IP
            kept_ips.append(ip)
        elif ip.ip_address in historical_active_ips:
            # It's a Ghost IP (was active recently)
            kept_ips.append(ip)
        else:
            # It's a Void IP (never active or too old)
            parent = ip.metadata_resolved_from or "unknown"
            void_counts[parent] += 1
            
    # Now append the synthetic Void nodes
    for parent, count in void_counts.items():
        if count > 0:
            synthetic_void = IpState(
                id=None,
                job_id=None,
                ip_address=f"Void ({count})",
                metadata_resolved_from=parent if parent != "unknown" else None,
                metadata_discovered_from=["void_aggregated"]
            )
            synthetic_void.ports_list = []
            kept_ips.append(synthetic_void)
            
    return kept_ips
