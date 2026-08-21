# Site Health Check

A high-performance SRE tool for auditing Network Ports, Deep TLS Certificates, and HTTP Payloads. Originally designed for OpenStack application observability.

## What it is
- **Infrastructure Health Monitor:** Checks basic TCP connectivity and performs deep TLS inspection (extracting expiration dates and Subject Alternative Names).
- **Advanced Target Expansion:** The robust parsing engine natively supports comma-separated targets, hyphenated IP ranges (`192.168.1.1-192.168.1.100`), and full mathematical CIDR block expansion (`10.0.0.0/24`), stripping unusable network bounds out of the box.
- **Port Range Scanner:** Natively supports scanning contiguous port ranges (e.g., `-p 80,443,8000-8050`).
- **SRE-focused Virtual Host Engine:** Split caching ensures TCP connections are only opened once per IP/Port combination, while HTTP checks are executed for every distinct domain (Virtual Host) on that IP.
- **HTTP Payload Validation:** Deep validation of HTTP response codes, expected HTML strings, and routing through reverse proxies using custom DNS interception.
- **Breadth-First Target Discovery:** Capable of recursively discovering and scanning any Subject Alternative Names (SANs) found on a TLS certificate using `--recursive-san`, with `--out-of-scope-depth` constraints to cleanly limit scanning scope and prevent unbounded external CDN sprawling.
- **Observability State Engine:** Dumps all findings into a deeply nested JSON file designed for downstream GUI consumption and observability aggregation.

## What it is NOT
- **NOT an Alerting Engine:** It does not send emails, Slack messages, or SMS. Alerting should be delegated to external observability tools reading the JSON output.
- **NOT a Background Daemon:** It runs as a single execution (CLI-first). Continuous execution scheduling is delegated to standard Linux `cron`.
- **NOT a Visual Dashboard:** The tool generates structured JSON data, not HTML graphs or web interfaces.

## 🚧 In Development (Roadmap)
- **Declarative Orchestration:** Future support for orchestrating multiple complex checks via a hierarchical YAML/JSON configuration file to bypass CLI flags.

## Usage

You can run the scanner against any target domain, IP, or subnet.
```bash
# Basic port scan against a domain
poetry run site-check cloudflare.com -p 80,443,8443

# Scan a full CIDR block and a hyphenated IP range simultaneously
poetry run site-check 10.0.0.0/24,192.168.1.5-192.168.1.15 -p 80,443

# Scan with recursive Subject Alternative Names (SAN) discovery
poetry run site-check 8.8.8.8 -p 443 --recursive-san

# Strict scope check: recursively scan SANs but strictly restrict to the target's physical IP address
poetry run site-check example.com -p 443 --recursive-san --out-of-scope-depth 0

# Test virtual host payload validation
poetry run site-check example.com -p 80,443 --expected-strings "Welcome" --undesired-strings "Error 500"

# Export the results to a file for observability pipelines
poetry run site-check example.com -p 443 -o results.json
```