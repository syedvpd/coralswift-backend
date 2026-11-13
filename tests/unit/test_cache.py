import datetime as dt

from app.core.cache import Cache


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int) -> None:
        self.data[key], self.ttls[key] = value, ex


class BrokenRedis:
    def get(self, key: str) -> None:
        raise ConnectionError("down")

    def set(self, key: str, value: str, ex: int) -> None:
        raise ConnectionError("down")


def test_builds_once_then_serves_cached_json_with_ttl_and_prefix() -> None:
    client, calls = FakeRedis(), []

    def build() -> dict[str, object]:
        calls.append(1)
        return {"at": dt.datetime(2026, 1, 1, tzinfo=dt.UTC), "n": 3}

    cache = Cache(client, "staging")
    first = cache.get_or_set("overview:True", 60, build)
    second = cache.get_or_set("overview:True", 60, build)
    assert first == second == {"at": "2026-01-01T00:00:00+00:00", "n": 3}
    assert len(calls) == 1
    assert client.ttls == {"staging:overview:True": 60}


def test_different_keys_do_not_share_values() -> None:
    cache = Cache(FakeRedis(), "p")
    assert cache.get_or_set("a", 5, lambda: {"v": 1}) == {"v": 1}
    assert cache.get_or_set("b", 5, lambda: {"v": 2}) == {"v": 2}


def test_no_client_just_builds() -> None:
    assert Cache(None, "p").get_or_set("k", 5, lambda: {"v": 1}) == {"v": 1}


def test_redis_outage_falls_back_to_building() -> None:
    assert Cache(BrokenRedis(), "p").get_or_set("k", 5, lambda: {"v": 1}) == {"v": 1}
