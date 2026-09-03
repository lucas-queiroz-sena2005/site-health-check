import subprocess
import time
import requests
import json

import time
import requests
import json

print("\n--- 1. Testing Dynamic Schemas (GET /api/schemas/schedule) ---")
resp = requests.get("http://127.0.0.1:8000/api/schemas/schedule")
print(f"Status: {resp.status_code}")
print(json.dumps(resp.json(), indent=2))

print("\n--- 2. Launching a Job (POST /api/jobs/launch) ---")
payload = {
    "targets": ["google.com", "example.com"],
    "ports": [80, 443],
    "flags": {
        "check_http": True,
        "timeout": 30
    }
}
resp = requests.post("http://127.0.0.1:8000/api/jobs/launch", json=payload)
print(f"Status: {resp.status_code}")
job_data = resp.json()
print(json.dumps(job_data, indent=2))

job_id = job_data.get("id")

if job_id:
    print("\n--- 3. Checking List Jobs (GET /api/jobs) ---")
    resp = requests.get("http://127.0.0.1:8000/api/jobs")
    print(f"Status: {resp.status_code}")
    print(f"Total jobs: {len(resp.json())}")
    
    print("\n--- 4. Streaming Job Logs (GET /api/jobs/{job_id}/stream) ---")
    # We use stream=True and iterate lines
    with requests.get(f"http://127.0.0.1:8000/api/jobs/{job_id}/stream", stream=True) as r:
        print(f"Status: {r.status_code}")
        count = 0
        try:
            for line in r.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    print(f"Received SSE: {decoded_line}")
                    count += 1
        except requests.exceptions.ChunkedEncodingError:
            print("Stream ended.")
            
    print("\n--- 5. Creating a Saved View (POST /api/views) ---")
    view_payload = {
        "name": "Failed HTTP",
        "search": "status_code:>=400",
        "statuses": ["completed", "failed"],
        "table_sort_by": "domain",
        "table_sort_dir": "desc"
    }
    resp = requests.post("http://127.0.0.1:8000/api/views", json=view_payload)
    print(f"Status: {resp.status_code}")
    print(json.dumps(resp.json(), indent=2))
