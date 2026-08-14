# Site Health Check

A high-performance SRE tool for auditing Network Ports, Deep TLS Certificates, and HTTP Payloads. Originally designed for OpenStack application observability.

## Features
- **Smart Protocol Detection**: Automatically probes raw TCP sockets. If the port supports TLS, it extracts the certificate data. It then dynamically routes the HTTP payload checker to `https://` or `http://` based on the exact capabilities of the port.
- **Port Ranges**: Supports complex port strings (e.g., `-p 80,443,8000-8050`).
- **Deep TLS Inspection**: Extracts exact expiration dates and parses Ciphers without relying on web browsers.
- **Unified State Export**: Dumps all findings into a deeply nested JSON file for downstream GUI consumption.

## Usage

Run the scanner against a target domain or IP:
```bash
poetry run python -m site_health_check cloudflare.com -p 80,443,8443
```

Export the results to a file for observability:
```bash
poetry run python -m site_health_check 192.168.1.50 -p 8000-8050 -o results.json
```