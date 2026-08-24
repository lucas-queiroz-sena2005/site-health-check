# Phase 1: Interface & Decoupling

The goal of this phase is to build the user-facing CLI and establish a rigid separation between input parsing and the core execution engine. The CLI must act purely as a translator, converting user arguments into a standardized JSON payload.

## Architectural Concept: The "Dumb" CLI
The CLI does no network operations. It parses arguments (e.g., `--ip 192.168.1.0/24 --ports 80,443`) and builds an event-driven JSON array. This ensures the core engine is decoupled and can eventually accept payloads from a web API, a YAML file, or a remote job queue without modification.

### Standardized JSON Schema Example
```json
[
  {
    "type": "ip_sweep",
    "payload": {
      "target": "192.168.1.50",
      "ports": [80, 443],
      "timeout": 2
    }
  },
  {
    "type": "domain_check",
    "payload": {
      "target": "susy.ic.unicamp.br",
      "ip_hint": "143.106.10.50"
    }
  }
]
```

### CLI Implementation Example (`argparse`)
```python
import argparse
import json

def build_payload(args):
    tasks = []
    # Convert CLI args to standardized JSON structure
    if args.ip:
        tasks.append({
            "type": "ip_sweep",
            "payload": {
                "target": args.ip,
                "ports": [int(p) for p in args.ports.split(",")]
            }
        })
    return tasks

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unicamp Health Check")
    parser.add_argument("--ip", help="Target IP or CIDR")
    parser.add_argument("--ports", default="80,443", help="Comma-separated ports")
    args = parser.parse_args()
    
    # Pass JSON to core engine
    json_payload = build_payload(args)
    # core_engine.run(json_payload)
```

## Tasks

- [ ] **Phase 1: Interface Setup**
  - [ ] Scaffold `src/site_health_check/cli.py` using `argparse`.
  - [ ] Implement CIDR parsing logic (expanding `192.168.1.0/24` into individual IPs).
  - [X] Implement port parsing logic (expanding `8000-8005` into `[8000, 8001, ...]`).
  - [X] Define Pydantic models (or standard Python dataclasses) for the JSON Task Schema to ensure strict validation before passing to the core engine.
