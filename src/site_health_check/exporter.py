"""Export logic for Site Health Check results."""

import json
import os
from datetime import datetime, timezone

from site_health_check.schema import IpState


def export_results(results: dict[str, IpState], output_path: str | None = None) -> str:
    """
    Exports the scan results to a JSON file.
    If output_path is None, dynamically creates a file in the ./results/ directory.
    """
    if not output_path:
        # Smart Default Logic
        target_name = results.get("target", "unknown").replace("://", "_").replace("/", "_")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{target_name}_{timestamp}.json"
        
        # Find the repository root (3 levels up from exporter.py: src/site_health_check/exporter.py -> repo/)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(os.path.dirname(current_dir))
        
        # Ensure the 'results' directory exists in the repo root
        results_dir = os.path.join(repo_root, "results")
        os.makedirs(results_dir, exist_ok=True)
        
        output_path = os.path.join(results_dir, filename)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
        
    return output_path
