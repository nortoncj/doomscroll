"""Parser tests against real saved API responses in tests/fixtures/."""

import json
import os

import pytest

import sources

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
REQUIRED = ("job_id", "source", "title", "company", "location", "url", "posted_at")
OPTIONAL = ("description", "clearance_tag")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


PARSED = {
    "greenhouse": sources.parse_greenhouse(load("greenhouse_sample.json"), "spacex"),
    "lever": sources.parse_lever(load("lever_sample.json"), "palantir"),
    "usajobs": sources.parse_usajobs(load("usajobs_sample.json")),
    "adzuna": sources.parse_adzuna(load("adzuna_sample.json")),
}


@pytest.mark.parametrize("source", PARSED)
def test_every_job_has_the_shared_shape(source):
    jobs = PARSED[source]
    assert jobs, f"{source} parser returned nothing"
    for job in jobs:
        assert set(REQUIRED) <= set(job) <= set(REQUIRED + OPTIONAL)
        assert job["source"] == source
        assert job["job_id"].startswith(f"{source}_")
        assert "/" not in job["job_id"]
        assert job["title"]
        assert job["url"].startswith("https://")


@pytest.mark.parametrize("source", PARSED)
def test_job_ids_are_unique(source):
    ids = [j["job_id"] for j in PARSED[source]]
    assert len(ids) == len(set(ids))


def test_greenhouse_first_job():
    job = PARSED["greenhouse"][0]
    assert job["job_id"] == "greenhouse_8643277002"
    assert job["title"] == "Accountant"
    assert job["company"] == "SpaceX"
    assert job["location"] == "Hawthorne, CA"
    assert job["posted_at"].startswith("2026-07-21")


def test_lever_first_job():
    job = PARSED["lever"][0]
    assert job["job_id"] == "lever_6ed76ce8-4156-4b60-b120-403538bd66cd"
    assert job["title"] == "Administrative Business Partner"
    assert job["company"] == "Palantir"
    assert "Singapore" in job["location"]
    assert job["posted_at"].startswith("2026-")


def test_usajobs_first_job():
    job = PARSED["usajobs"][0]
    assert job["job_id"] == "usajobs_759326100"
    assert job["title"] == "Data Engineer"
    assert job["company"] == "Central Intelligence Agency"
    assert ":443" not in job["url"]
    assert job["posted_at"].startswith("2026-09-01")


def test_adzuna_first_job():
    job = PARSED["adzuna"][0]
    assert job["job_id"] == "adzuna_5914858061"
    assert job["title"] == "DevOps Engineer"
    assert job["company"] == "Elite Technical"
    assert job["location"] == "Plano, Collin County"


def test_lever_remote_workplace_type_lands_in_location():
    raw = [{"id": "x1", "text": "Cloud Engineer", "hostedUrl": "https://jobs.lever.co/a/x1",
            "createdAt": 1786469891368, "workplaceType": "remote",
            "categories": {"location": "New York, NY"}}]
    assert sources.parse_lever(raw, "acme")[0]["location"] == "Remote; New York, NY"


def test_usajobs_slash_id_falls_back_to_url():
    raw = {"SearchResult": {"SearchResultItems": [{"MatchedObjectDescriptor": {
        "PositionID": "24-1/ABC", "PositionTitle": "IT Specialist",
        "PositionURI": "https://www.usajobs.gov:443/job/123456",
        "PositionLocationDisplay": "Multiple Locations",
        "PositionLocation": [{"LocationName": "Tampa, Florida"}, {"LocationName": "Denver, Colorado"}],
    }}]}}
    job = sources.parse_usajobs(raw)[0]
    assert job["job_id"] == "usajobs_123456"
    assert job["location"] == "Tampa, Florida; Denver, Colorado"


def test_bad_items_are_skipped_not_fatal():
    assert sources.parse_greenhouse({"jobs": [{"title": "no id"}, {"id": 1}]}) == []
    assert sources.parse_adzuna({"results": [{}]}) == []
    assert sources.parse_usajobs({}) == []
    assert sources.parse_lever([]) == []
