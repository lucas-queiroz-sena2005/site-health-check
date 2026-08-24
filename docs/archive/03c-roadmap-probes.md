# Phase 3: The Network Probes (Two-Pass System)

This phase implements the actual network operations. Because we are optimizing for sweeping large CIDR blocks (IP-First discovery), we must use a "Two-Pass" system to avoid the massive timeout overhead of high-level HTTP libraries.

## Architectural Concept: Sockets vs. Requests

### Pass 1: The Socket Layer (Discovery & Speed)
We use Python's raw `asyncio` streams (or non-blocking sockets) to perform TCP handshakes. This answers the question: *"Is anything listening on IP `192.168.1.50` port 443?"* in milliseconds.
If it is, we wrap the socket in an SSL context to pull the certificate and extract the Subject Alternative Names (SANs), discovering domains we didn't know existed.

### Pass 2: The HTTP Layer (Deep Inspection)
We ONLY trigger an HTTP request (using `aiohttp` or `requests`) if the Socket Pass confirmed the port is open AND we need to verify HTTP-level routing (like NGINX Host Headers) or HTML content.

### Implementation Example (`asyncio` Sockets + SSL)
```python
import asyncio
import ssl

async def perform_socket_pass(ip, port):
    """
    Attempts a TCP connection and fetches SSL SANs in milliseconds.
    """
    try:
        # 1. Raw TCP Handshake
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), 
            timeout=2.0
        )
        
        discovered_sans = []
        
        # 2. SSL Upgrade (if port is 443)
        if port == 443:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # We just want the cert data
            
            # Wrap socket
            transport = writer.transport
            sock = transport.get_extra_info('socket')
            ssl_sock = ctx.wrap_socket(sock, do_handshake_on_connect=True)
            
            cert = ssl_sock.getpeercert(binary_form=False)
            
            # Extract SANs
            for item in cert.get('subjectAltName', []):
                if item[0] == 'DNS':
                    discovered_sans.append(item[1])
                    
        writer.close()
        await writer.wait_closed()
        
        return {"status": "open", "sans": discovered_sans}
        
    except (asyncio.TimeoutError, ConnectionRefusedError):
        return {"status": "closed", "sans": []}
```

## Tasks

- [ ] **Phase 3: The Probes**
  - [ ] Implement `src/site_health_check/probes/tcp_probe.py` using `asyncio.open_connection` with strict, low timeouts (e.g., 2 seconds).
  - [ ] Implement the SSL wrapping logic to extract `subjectAltName` (SANs) directly from the raw socket connection.
  - [ ] Implement `src/site_health_check/probes/http_probe.py` using `aiohttp` (or `httpx`) to perform the deep HTTP checks only when instructed by the core engine.
  - [ ] Ensure the HTTP probe correctly injects the `Host` header to bypass reverse proxies when targeting a raw IP address directly.
