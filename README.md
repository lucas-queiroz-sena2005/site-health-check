# Site Health Check

A high-performance SRE tool for auditing Network Ports, Deep TLS Certificates, and HTTP Payloads. Originally designed for OpenStack application observability.

## What it is
- **Infrastructure Health Monitor:** Checks basic TCP connectivity and performs deep TLS inspection (extracting expiration dates and Subject Alternative Names).
- **Breadth-First Target Discovery:** Capable of recursively discovering and scanning any Subject Alternative Names (SANs) found on a TLS certificate using `--recursive-san`.
- **SRE-focused Virtual Host Engine:** Split caching ensures TCP connections are only opened once per IP/Port combination, while HTTP checks are executed for every distinct domain (Virtual Host) on that IP.
- **Port Range Scanner:** Natively supports scanning contiguous port ranges (e.g., `-p 80,443,8000-8050`).
- **Observability State Engine:** Dumps all findings into a deeply nested JSON file designed for downstream GUI consumption and observability aggregation.

## What it is NOT
- **NOT an Alerting Engine:** It does not send emails, Slack messages, or SMS. Alerting should be delegated to external observability tools reading the JSON output.
- **NOT a Background Daemon:** It runs as a single execution (CLI-first). Continuous execution scheduling is delegated to standard Linux `cron`.
- **NOT a Visual Dashboard:** The tool generates structured JSON data, not HTML graphs or web interfaces.

## 🚧 In Development (Roadmap)
- **HTTP Payload Validation:** The async HTTP probe is currently under construction. Upcoming versions will natively support validating HTTP response codes, expected HTML strings, and routing through reverse proxies.
- **Declarative Orchestration:** Future support for orchestrating multiple complex checks via a hierarchical YAML configuration file.

## Usage

You can run the scanner against any target domain or IP.
```bash
# Basic port scan
poetry run site-check cloudflare.com -p 80,443,8443

# Scan with recursive Subject Alternative Names (SAN) discovery
poetry run site-check 8.8.8.8 -p 443 --recursive-san

# Disable virtual host HTTP checking for a raw IP sweep
poetry run site-check 192.168.1.50 -p 8000-8050 --no-check-virtual-hosts

# Export the results to a file for observability pipelines
poetry run site-check example.com -p 443 -o results.json
```