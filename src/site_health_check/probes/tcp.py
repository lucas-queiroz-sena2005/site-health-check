"""TCP and TLS socket probes."""
import asyncio
import logging
import ssl
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from cryptography import x509
from cryptography.x509.oid import ExtensionOID

from site_health_check.schemas.engine import PortState, TlsCertificate


async def check_tcp_and_tls(ip: str, port: int, server_hostname: str | None = None, timeout: float = 2.0) -> PortState:
    """Verifies TCP connection, registers TLS Certificate data and acquires SANs"""
    result = PortState()
    start_time = time.perf_counter()

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                host=ip,
                port=port,
                ssl=ssl_context,
                server_hostname=server_hostname
            ),
            timeout=timeout
        )

        # If we reach here without throwing an error, the port is open AND speaks TLS
        result.tcp_status = "open"
        result.tcp_latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Raw binary certificate
        ssl_obj = writer.get_extra_info('ssl_object')
        if ssl_obj:
            raw_cert = ssl_obj.getpeercert(binary_form=True)
            if raw_cert:
                tls_obj = TlsCertificate(valid=False)

                try:
                    # Parse the binary cert using cryptography
                    cert = x509.load_der_x509_certificate(raw_cert)

                    # SANs extraction
                    ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                    tls_obj.domains_discovered_sans = ext.value.get_values_for_type(x509.DNSName)

                    # Issuer extraction
                    tls_obj.issuer = cert.issuer.rfc4514_string()
                    
                    # Expiration and Date Validation
                    try:
                        not_before = cert.not_valid_before_utc
                        not_after = cert.not_valid_after_utc
                    except AttributeError:
                        # Fallback for older cryptography versions
                        not_before = cert.not_valid_before.replace(tzinfo=timezone.utc)
                        not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
                        
                    now = datetime.now(timezone.utc)
                    is_date_valid = not_before <= now <= not_after
                    tls_obj.expires_in_days = (not_after - now).days
                    
                    # Name Validation (Does the SAN match the hostname?)
                    is_name_valid = True
                    if server_hostname:
                        is_name_valid = False
                        for san in tls_obj.domains_discovered_sans:
                            if san.startswith("*."):
                                base = san[2:]
                                if server_hostname.endswith(base) and server_hostname.count('.') == base.count('.') + 1:
                                    is_name_valid = True
                                    break
                            elif san == server_hostname:
                                is_name_valid = True
                                break
                                
                    tls_obj.valid = is_date_valid and is_name_valid and bool(tls_obj.issuer)
                    

                except Exception as e:  # noqa: BLE001
                    logger.debug(f"Failed to parse cert or extract SANs: {e}")

                result.tls_certificate = tls_obj

        writer.close()
        await writer.wait_closed()

    except ssl.SSLError:
        # Port OPEN, but is just plain TCP (e.g., plain HTTP).
        result.tcp_status = "open"
        result.tcp_latency_ms = int((time.perf_counter() - start_time) * 1000)
    except asyncio.TimeoutError:
        result.tcp_status = "closed"
    except Exception as e:  # noqa: BLE001
        # Network unreachable, connection refused, etc.
        logger.debug(f"TCP connection failed for {ip}:{port} - {e}")
        result.tcp_status = "closed"

    return result
