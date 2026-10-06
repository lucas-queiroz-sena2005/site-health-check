import asyncio
import time

class AsyncTokenBucket:
    """
    A token bucket rate limiter for pacing outbound network requests.
    """
    def __init__(self, rate: float):
        self.rate = rate
        self.tokens = rate
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()
        
    async def acquire(self):
        """
        Acquire a token. If the bucket is empty, calculates the exact time
        needed to wait for the next token and sleeps without active polling.
        A rate of 0 or lower blocks execution entirely.
        """
        if self.rate <= 0:
            # A rate of 0 means 0 requests/sec, so block indefinitely.
            while True:
                await asyncio.sleep(86400)
                
        while True:
            now = time.monotonic()
            wait_time = 0.0
            
            async with self.lock:
                elapsed = now - self.last_update
                self.tokens += elapsed * self.rate
                if self.tokens > self.rate:
                    self.tokens = self.rate
                self.last_update = now
                
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                
                # Calculate exactly how long to sleep until 1 token is available
                wait_time = (1.0 - self.tokens) / self.rate
            
            # Sleep outside the lock so we don't block other tasks
            if wait_time > 0:
                await asyncio.sleep(wait_time)
