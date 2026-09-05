import httpx

from backend.services import ntfy as ntfy_module


class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)


def test_send_ntfy_success_sets_expected_headers(monkeypatch):
    captured = {}

    def fake_post(url, content=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["content"] = content
        return _FakeResponse(200)

    monkeypatch.setattr(ntfy_module.httpx, "post", fake_post)

    ok = ntfy_module.send_ntfy(
        "OA IN 2 HOURS", "Toshiba\nEmbedded Systems OA", priority=5,
        click_url="https://example.com/oa", tags="rotating_light",
    )

    assert ok is True
    assert captured["headers"]["X-Title"] == "OA IN 2 HOURS"
    assert captured["headers"]["X-Priority"] == "5"
    assert captured["headers"]["X-Click"] == "https://example.com/oa"
    assert captured["headers"]["X-Tags"] == "rotating_light"
    assert captured["content"] == "Toshiba\nEmbedded Systems OA".encode("utf-8")


def test_send_ntfy_failure_returns_false(monkeypatch):
    def fake_post(url, content=None, headers=None, timeout=None):
        return _FakeResponse(500)

    monkeypatch.setattr(ntfy_module.httpx, "post", fake_post)

    ok = ntfy_module.send_ntfy("Title", "Body")
    assert ok is False


def test_send_ntfy_network_error_returns_false(monkeypatch):
    def fake_post(url, content=None, headers=None, timeout=None):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(ntfy_module.httpx, "post", fake_post)

    ok = ntfy_module.send_ntfy("Title", "Body")
    assert ok is False


def test_send_ntfy_strips_non_ascii_title(monkeypatch):
    captured = {}

    def fake_post(url, content=None, headers=None, timeout=None):
        captured["headers"] = headers
        return _FakeResponse(200)

    monkeypatch.setattr(ntfy_module.httpx, "post", fake_post)

    ok = ntfy_module.send_ntfy("OA Reminder — Test", "body")
    assert ok is True
    # Should not raise, and non-ASCII characters are dropped rather than
    # crashing the whole request.
    assert "—" not in captured["headers"]["X-Title"]
