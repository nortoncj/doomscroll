"""Retry behavior for the shared HTTP helper. No real network, no real waiting."""

import io
import json
import urllib.error

import pytest

import sources


def http_error(code):
    return urllib.error.HTTPError("https://example.com", code, "error", {}, None)


@pytest.fixture
def fake_net(monkeypatch):
    """Feed urlopen a scripted list of outcomes. Records every sleep."""
    state = {"script": [], "calls": 0, "sleeps": []}

    def fake_urlopen(req, timeout):
        outcome = state["script"][state["calls"]]
        state["calls"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(json.dumps(outcome).encode())

    monkeypatch.setattr(sources.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(sources, "_sleep", lambda s: state["sleeps"].append(s))
    return state


def test_503_then_success_retries_once(fake_net):
    fake_net["script"] = [http_error(503), {"ok": True}]
    assert sources._get_json("https://example.com") == {"ok": True}
    assert fake_net["calls"] == 2
    assert fake_net["sleeps"] == [2]


def test_429_is_retried(fake_net):
    fake_net["script"] = [http_error(429), http_error(429), {"ok": True}]
    assert sources._get_json("https://example.com") == {"ok": True}
    assert fake_net["sleeps"] == [2, 5]


def test_network_blip_is_retried(fake_net):
    fake_net["script"] = [urllib.error.URLError("connection reset"), {"ok": True}]
    assert sources._get_json("https://example.com") == {"ok": True}


def test_gives_up_after_two_retries(fake_net):
    fake_net["script"] = [http_error(503), http_error(503), http_error(503)]
    with pytest.raises(urllib.error.HTTPError):
        sources._get_json("https://example.com")
    assert fake_net["calls"] == 3


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_client_errors_fail_fast(fake_net, code):
    fake_net["script"] = [http_error(code)]
    with pytest.raises(urllib.error.HTTPError):
        sources._get_json("https://example.com")
    assert fake_net["calls"] == 1
    assert fake_net["sleeps"] == []
