"""Handler tests. Every HTTP fetch and the DynamoDB table are faked,
so these run offline in CI."""

import logging
import os

import pytest

import handler
import sources
import ssm_params

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRETS = {
    "usajobs/api_key": "USA_SECRET_123",
    "adzuna/app_id": "ADZ_ID_456",
    "adzuna/app_key": "ADZ_KEY_789",
}

# One raw response per source, shaped like the real APIs.
# Expected matches: DevOps (greenhouse), Cloud (usajobs), Firmware (adzuna).
GREENHOUSE = {"jobs": [
    {"id": 1, "title": "DevOps Engineer", "company_name": "SpaceX",
     "location": {"name": "Remote"}, "absolute_url": "https://boards.greenhouse.io/spacex/jobs/1"},
    {"id": 2, "title": "Accountant", "company_name": "SpaceX",
     "location": {"name": "Hawthorne, CA"}, "absolute_url": "https://boards.greenhouse.io/spacex/jobs/2"},
]}
LEVER = [
    {"id": "a1", "text": "Senior Cloud Engineer", "hostedUrl": "https://jobs.lever.co/palantir/a1",
     "createdAt": 1786469891368, "categories": {"location": "Remote"}},
]
USAJOBS = {"SearchResult": {"SearchResultItems": [
    {"MatchedObjectId": "800001", "MatchedObjectDescriptor": {
        "PositionTitle": "IT Specialist (Cloud)", "OrganizationName": "Department of the Air Force",
        "PositionLocationDisplay": "Tampa, Florida",
        "PositionURI": "https://www.usajobs.gov:443/job/800001",
        "PublicationStartDate": "2026-10-01T00:00:00.0000"}},
]}}
ADZUNA = {"results": [
    {"id": "9001", "title": "Embedded Firmware Engineer", "company": {"display_name": "Acme Defense"},
     "location": {"display_name": "Orlando, Orange County"}, "created": "2026-10-08T12:00:00Z",
     "redirect_url": "https://www.adzuna.com/land/ad/9001"},
]}


class ConditionalCheckFailed(Exception):
    def __init__(self):
        super().__init__("The conditional request failed")
        self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression):
        assert ConditionExpression == "attribute_not_exists(job_id)"
        if Item["job_id"] in self.items:
            raise ConditionalCheckFailed()
        self.items[Item["job_id"]] = Item


def get_param(name):
    return SECRETS[name]


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setenv("FILTERS_PATH", os.path.join(REPO_ROOT, "config", "filters.json"))
    monkeypatch.setenv("USAJOBS_EMAIL", "test@example.com")
    monkeypatch.setattr(sources, "fetch_greenhouse", lambda board: GREENHOUSE)
    monkeypatch.setattr(sources, "fetch_lever", lambda company: LEVER)
    monkeypatch.setattr(sources, "fetch_usajobs", lambda key, email: USAJOBS)
    monkeypatch.setattr(sources, "fetch_adzuna", lambda app_id, app_key, page=1: ADZUNA)
    return monkeypatch


def test_first_run_inserts_only_matches(fakes):
    table = FakeTable()
    result = handler.lambda_handler({}, None, table=table, get_param=get_param)

    assert result["inserted"] == 3
    assert set(table.items) == {"greenhouse_1", "usajobs_800001", "adzuna_9001"}
    for item in table.items.values():
        assert item["status"] == "JustDropped"
        assert item["matched_keywords"]
        assert item["first_seen_at"] == item["status_updated_at"]


def test_rerun_inserts_nothing(fakes):
    table = FakeTable()
    handler.lambda_handler({}, None, table=table, get_param=get_param)
    second = handler.lambda_handler({}, None, table=table, get_param=get_param)

    assert second["inserted"] == 0
    assert len(table.items) == 3


def test_failed_source_saves_the_rest_then_raises(fakes, caplog):
    def broken_adzuna(app_id, app_key, page=1):
        # Simulate an error message that echoes the request URL with the key in it.
        raise RuntimeError(f"HTTP 500 for ...?app_id={app_id}&app_key={app_key}")

    fakes.setattr(sources, "fetch_adzuna", broken_adzuna)
    caplog.set_level(logging.INFO)
    table = FakeTable()

    with pytest.raises(RuntimeError, match="adzuna"):
        handler.lambda_handler({}, None, table=table, get_param=get_param)

    assert set(table.items) == {"greenhouse_1", "usajobs_800001"}
    assert "ADZ_KEY_789" not in caplog.text
    assert "ADZ_ID_456" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_placeholder_secret_only_breaks_its_own_source(fakes):
    def placeholder_for_usajobs(name):
        if name == ssm_params.USAJOBS_API_KEY:
            raise ssm_params.MissingSecretError("/doomscroll/usajobs/api_key is still CHANGE_ME")
        return SECRETS[name]

    table = FakeTable()
    with pytest.raises(RuntimeError, match="usajobs"):
        handler.lambda_handler({}, None, table=table, get_param=placeholder_for_usajobs)

    assert set(table.items) == {"greenhouse_1", "adzuna_9001"}


def test_duplicate_job_in_one_run_is_written_once(fakes):
    fakes.setattr(sources, "fetch_lever", lambda company: [])
    doubled = {"jobs": GREENHOUSE["jobs"] + GREENHOUSE["jobs"]}
    fakes.setattr(sources, "fetch_greenhouse", lambda board: doubled)
    table = FakeTable()

    result = handler.lambda_handler({}, None, table=table, get_param=get_param)
    assert result["inserted"] == 3
