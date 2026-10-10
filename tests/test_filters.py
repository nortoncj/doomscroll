import os

import pytest

from filters import load_filters

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(REPO_ROOT, "config", "filters.json")


@pytest.fixture(scope="module")
def f():
    # Tests run against the REAL config, so a bad edit to filters.json
    # fails CI instead of silently changing your digest.
    return load_filters(CONFIG)


@pytest.mark.parametrize(
    "title, expected",
    [
        ("DevOps Engineer", ["devops"]),
        ("DevOps Engineer II", ["devops"]),
        ("Associate Cloud Engineer", ["cloud"]),
        ("Embedded Software Engineer", ["embedded"]),
        ("IoT Firmware Engineer", ["firmware", "iot"]),
        ("Site Reliability Engineer", ["site reliability"]),
        ("Junior Platform Engineer", ["platform engineer"]),
        ("Electronics Engineer", ["electronics engineer"]),
    ],
)
def test_includes(f, title, expected):
    assert f.match(title, "Tampa, FL") == expected


@pytest.mark.parametrize(
    "title",
    [
        "Patriot Systems Engineer",
        "Software Engineer",
        "Senior DevOps Engineer",
        "Sr. Cloud Engineer",
        "Staff Site Reliability Engineer",
        "Cloud Solutions Architect",
        "Cloud Sales Executive",
        "DevOps Engineer III",
        "Engineering Manager, Infrastructure",
        "Lead Firmware Engineer",
        "Embedded Systems Intern",
        "",
    ],
)
def test_rejects(f, title):
    assert f.match(title, "Remote") == []


@pytest.mark.parametrize(
    "location",
    ["Tampa, FL", "Remote - US", "St. Petersburg, Florida", "Melbourne, FL",
     "Location Negotiable After Selection", ""],
)
def test_locations_kept(f, location):
    assert f.match("DevOps Engineer", location) == ["devops"]


@pytest.mark.parametrize("location", ["Seattle, WA", "Hawthorne, CA", "Austin, TX"])
def test_locations_rejected(f, location):
    assert f.match("DevOps Engineer", location) == []


def test_company_lists_load(f):
    assert "spacex" in f.greenhouse_boards
    assert "palantir" in f.lever_companies
