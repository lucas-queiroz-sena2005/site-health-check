"""Network operations and helpers."""

import asyncio
import socket
import ipaddress


async def resolve_target(target: str) -> tuple[str, str, bool]:
    """
    Resolves a target to an IP address if it is a domain name.
    
    Returns:
        Tuple containing:
        - ip_address (str): The resolved IP address (or original IP if already an IP). Empty if resolution failed.
        - host_header (Optional[str]): The domain name to use for HTTP Host headers and TLS SNI (None if target was an IP).
        - is_domain (bool): True if the original target was a domain, False if it was an IP.
    """
    ip_address = target
    is_domain = False
    
    try:
        # Check if it's already a valid IPv4 address natively
        ipaddress.IPv4Address(target)
    except ValueError:
        is_domain = True
        try:
            # Resolve domain asynchronously
            loop = asyncio.get_running_loop()
            ip_address = await loop.run_in_executor(None, socket.gethostbyname, target)
        except socket.gaierror:
            # Return empty IP to signal resolution failure
            return "", target, True
            
    host_header = target if is_domain else None
    return ip_address, host_header, is_domain
