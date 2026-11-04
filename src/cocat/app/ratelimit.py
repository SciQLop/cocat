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
        if key not in self._windows and len(self._windows) >= self.max_keys:
            self._make_room(now)
        start, calls = self._windows.get(key, (now, 0))
        if now - start >= self.period:
            start, calls = now, 0
        if calls >= self.max_calls:
            return False
        self._windows[key] = (start, calls + 1)
        return True

    def _make_room(self, now: float) -> None:
        self._windows = {
            client: window
            for client, window in self._windows.items()
            if now - window[0] < self.period
        }
        overflow = len(self._windows) - self.max_keys + 1
        oldest = sorted(self._windows, key=lambda client: self._windows[client][0])
        for client in oldest[: max(0, overflow)]:
            del self._windows[client]


def load_trusted_proxies() -> int:
    value = os.environ.get(TRUSTED_PROXIES_ENV, "").strip()
    if not value:
        return 0
    if not value.isdigit():
        raise RuntimeError(
            f"{TRUSTED_PROXIES_ENV} must be a non-negative integer, got {value!r}"
        )
    return int(value)


def client_key(request: Request, trusted_proxies: int) -> str:
    hops = [
        hop.strip() for hop in request.headers.get("x-forwarded-for", "").split(",")
    ]
    hops = [hop for hop in hops if hop]
    if trusted_proxies > 0 and len(hops) >= trusted_proxies:
        return hops[-trusted_proxies]
    return request.client.host if request.client else "unknown"


def limit(limiter: RateLimiter, trusted_proxies: int) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        if not limiter.hit(client_key(request, trusted_proxies)):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)

    return dependency
