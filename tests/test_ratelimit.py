import pytest
from conftest import login, make_user, ws_headers
from fastapi import APIRouter, Request
from fastapi.routing import APIRoute

from cocat.app.app import with_route_dependency
from cocat.app.ratelimit import RateLimiter, client_key, limit


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_limiter_blocks_after_max_then_recovers():
    clock = FakeClock()
    limiter = RateLimiter(3, 60.0, clock)

    assert [limiter.hit("key") for _ in range(3)] == [True, True, True]
    assert limiter.hit("key") is False

    clock.now = 59.9
    assert limiter.hit("key") is False

    clock.now = 60.0
    assert limiter.hit("key") is True


def test_limiter_keys_are_independent():
    limiter = RateLimiter(1, 60.0, FakeClock())

    assert limiter.hit("a") is True
    assert limiter.hit("b") is True
    assert limiter.hit("a") is False


def test_limiter_drops_expired_windows():
    clock = FakeClock()
    limiter = RateLimiter(1, 10.0, clock, max_keys=2)

    limiter.hit("a")
    clock.now = 20.0
    limiter.hit("b")
    limiter.hit("c")
    limiter.hit("d")

    assert set(limiter._windows) == {"b", "c", "d"}


def test_with_route_dependency_adds_and_raises_on_unknown_path():
    router = APIRouter()

    @router.post("/known")
    def known() -> None:
        return None

    dependency = limit(RateLimiter(1, 60.0))

    assert with_route_dependency(router, "/known", dependency) is router
    assert known() is None
    route = router.routes[0]
    assert isinstance(route, APIRoute)
    assert len(route.dependencies) == 1

    with pytest.raises(ValueError, match="No route /missing"):
        with_route_dependency(router, "/missing", dependency)


def test_login_is_rate_limited(app_client):
    data = {"username": "nobody@example.com", "password": "wrong"}
    client = app_client.client

    assert [
        client.post("/auth/jwt/login", data=data).status_code for _ in range(10)
    ] == [400] * 10
    assert client.post("/auth/jwt/login", data=data).status_code == 429


def test_logout_is_not_rate_limited(app_client):
    make_user(app_client.db_path, "a@b.c")
    login(app_client.client, "a@b.c")

    for _ in range(15):
        assert app_client.client.post("/auth/jwt/logout").status_code != 429


def test_ws_headers_carry_the_login_cookie(app_client):
    make_user(app_client.db_path, "a@b.c")
    login(app_client.client, "a@b.c")

    response = app_client.client.get("/users/me", headers=ws_headers(app_client.client))

    assert response.json()["email"] == "a@b.c"


def make_request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [
                (key.lower().encode(), value.encode()) for key, value in headers.items()
            ],
            "client": ("1.2.3.4", 1234),
        }
    )


def test_client_key_trusts_only_proxy_hops(monkeypatch):
    forwarded = make_request({"x-forwarded-for": "spoofed, 9.9.9.9"})

    monkeypatch.setenv("COCAT_TRUSTED_PROXIES", "1")
    assert client_key(forwarded) == "9.9.9.9"

    monkeypatch.setenv("COCAT_TRUSTED_PROXIES", "2")
    assert client_key(make_request({"x-forwarded-for": "1.1.1.1"})) == "1.2.3.4"

    monkeypatch.setenv("COCAT_TRUSTED_PROXIES", "0")
    assert client_key(forwarded) == "1.2.3.4"

    assert client_key(Request({"type": "http", "headers": []})) == "unknown"
