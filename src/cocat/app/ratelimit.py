import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, status

TRUSTED_PROXIES_ENV = "COCAT_TRUSTED_PROXIES"


@dataclass
class RateLimiter:
    max_calls: int
    period: float
    clock: Callable[[], float] = time.monotonic
    max_keys: int = 10_000
    # simplify: in-memory, per process; resets on restart. Move to a shared store if
    # the server ever runs several replicas.
    _windows: dict[str, tuple[float, int]] = field(default_factory=dict)

    def hit(self, key: str) -> bool:
        now = self.clock()
        if len(self._windows) > self.max_keys:
            self._windows = {
                client: window
                for client, window in self._windows.items()
                if now - window[0] < self.period
            }
        start, calls = self._windows.get(key, (now, 0))
        if now - start >= self.period:
            start, calls = now, 0
        if calls >= self.max_calls:
            return False
        self._windows[key] = (start, calls + 1)
        return True


def client_key(request: Request) -> str:
    trusted = int(os.environ.get(TRUSTED_PROXIES_ENV, "0"))
    hops = [
        hop.strip() for hop in request.headers.get("x-forwarded-for", "").split(",")
    ]
    hops = [hop for hop in hops if hop]
    if trusted > 0 and len(hops) >= trusted:
        return hops[-trusted]
    return request.client.host if request.client else "unknown"


def limit(limiter: RateLimiter) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        if not limiter.hit(client_key(request)):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)

    return dependency
