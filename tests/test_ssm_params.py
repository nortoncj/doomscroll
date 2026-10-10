import pytest

import ssm_params


class FakeSSM:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def get_parameter(self, Name, WithDecryption):
        self.calls.append((Name, WithDecryption))
        return {"Parameter": {"Value": self.values[Name]}}


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setenv("SSM_PREFIX", "/doomscroll")
    ssm_params.clear_cache()
    yield
    ssm_params.clear_cache()


def test_reads_with_decryption():
    client = FakeSSM({"/doomscroll/usajobs/api_key": "real-value"})
    assert ssm_params.get_param(ssm_params.USAJOBS_API_KEY, client) == "real-value"
    assert client.calls == [("/doomscroll/usajobs/api_key", True)]


def test_caches_between_calls():
    client = FakeSSM({"/doomscroll/adzuna/app_id": "abc"})
    ssm_params.get_param(ssm_params.ADZUNA_APP_ID, client)
    ssm_params.get_param(ssm_params.ADZUNA_APP_ID, client)
    assert len(client.calls) == 1


def test_placeholder_fails_loudly():
    client = FakeSSM({"/doomscroll/adzuna/app_key": "CHANGE_ME"})
    with pytest.raises(ssm_params.MissingSecretError, match="put-parameter"):
        ssm_params.get_param(ssm_params.ADZUNA_APP_KEY, client)
