import asyncio
import time
from engine.utils.rate_limit import AsyncTokenBucket

async def main():
    limiter = AsyncTokenBucket(1.0)
    start = time.monotonic()
    for _ in range(5):
        await limiter.acquire()
        print(f"Acquired at {time.monotonic() - start:.2f}")

asyncio.run(main())
