# Phase 2: The Core Engine (BFS & Concurrency)

The Core Engine is responsible for consuming the standardized JSON task list and executing it as fast as possible. Because we are discovering new targets dynamically (like finding SANs in an SSL certificate), we must use a Breadth-First Search (BFS) approach with a central Queue, rather than linear iteration or recursion.

## Architectural Concept: The Worker Pool and Task Queue
Instead of one function calling another (which can lead to infinite recursion if Domain A points to Domain B, and B points to A), we use a central `asyncio.Queue`. 
1. The CLI seeds the initial tasks into the Queue.
2. A pool of asynchronous workers constantly pulls tasks off the front of the queue.
3. If a worker discovers a new domain (a SAN), it pushes a new task to the *back* of the queue.
4. A `seen_targets` set ensures we never process the exact same IP/Port or Domain/IP combination twice.

### Core Engine Implementation Example (`asyncio`)
```python
import asyncio

# Global cache to prevent duplicate scanning (infinite loops)
seen_targets = set()

async def worker(name, queue, results_state):
    while True:
        # Get a task from the queue
        task = await queue.get()
        task_id = f"{task['type']}:{task['payload'].get('target')}"
        
        if task_id in seen_targets:
            queue.task_done()
            continue
            
        seen_targets.add(task_id)
        print(f"Worker {name} processing {task_id}")
        
        # Route to the appropriate probe
        if task["type"] == "ip_sweep":
            # await perform_socket_pass(...)
            # If we find a SAN, push a new task to the queue!
            # await queue.put({"type": "domain_check", "payload": {"target": "new-domain.com"}})
            pass
            
        # Update the central state dictionary
        results_state[task_id] = {"status": "completed"}
        
        queue.task_done()

async def main_engine(json_payload):
    queue = asyncio.Queue()
    results_state = {}
    
    # Seed the queue with initial CLI payload
    for task in json_payload:
        await queue.put(task)
        
    # Spin up 50 concurrent workers
    workers = []
    for i in range(50):
        worker_task = asyncio.create_task(worker(f"W-{i}", queue, results_state))
        workers.append(worker_task)
        
    # Wait until the queue is completely empty
    await queue.join()
    
    # Cancel workers now that the job is done
    for w in workers:
        w.cancel()
        
    # Export state
    print("Scan complete. Writing results.json")

# asyncio.run(main_engine(json_payload))
```

## Tasks

- [ ] **Phase 2: BFS Engine Setup**
  - [ ] Implement the `asyncio.Queue` and the main engine loop in `src/site_health_check/core.py`.
  - [ ] Create the concurrent worker pool configuration (allow configuring the number of workers, e.g., 50-100).
  - [ ] Implement the `seen_targets` caching mechanism (hash set) to prevent duplicate scans and infinite loops.
  - [ ] Implement the central `results_state` dictionary that workers will update concurrently.
  - [ ] Add the JSON disk-writing logic to dump the final `results_state` to `results.json` when the queue is empty.
