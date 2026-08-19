# Data Schemas (Input & Output)

The `site-health-check` engine relies on a strict separation between **Input** (Commands/Tasks) and **Output** (State/Results). This guarantees the engine remains lightweight, deduplicated, and easy to integrate with external tools.

---

## 1. The Input Schema (Job Queue)

The input schema utilizes a **Flag-Based** and **Unified Target** approach. 

Whether a user types a command into the CLI, or an external web server sends a payload via API, it is always translated into this array of Task Objects before execution.

### Key Concepts
- **Unified Target:** There are no `types` of tasks (like `ip_sweep` or `url_check`). The `target` property accepts a raw IP, a Domain, or a full URL. The engine is smart enough to figure out how to process it.
- **Strict Ports:** The `ports` property is strictly an array of integers. Any translation from CLI ranges (e.g., `80-85`) happens *before* the JSON is generated.
- **Extensible Flags:** All behavior modifications (timeouts, recursive SAN checking, expected strings) are handled in the `flags` dictionary.

---

## 2. The Output Schema (State)

The output JSON (`results.json`) uses a strict **IP-First** hierarchy (`IP -> Port -> Domain`). This normalizes all data, completely bridging the gap between Application Monitoring (URLs) and Infrastructure Discovery (CIDR Sweeps).

### The "Resolve & Place" Logic
Even if the initial input was a single Application URL (e.g., `https://susy.ic.unicamp.br/login`), the engine resolves the IP first, performs the checks, and places the result inside the unified IP hierarchy. 

This ensures that if you check 10 different URLs that all share the same OpenStack NGINX proxy, the output JSON automatically groups them together under that single physical/virtual server IP, creating a perfect infrastructure map.
