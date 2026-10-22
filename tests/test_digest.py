"""Tests for the M3 digest, clearance wiring, and parser descriptions."""

from datetime import datetime, timezone

import digest
import handler
import sources

NOW = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)


def job(job_id, title="Cloud Engineer", company="Vantor", **extra):
    return {
        "job_id": job_id, "source": "adzuna", "title": title, "company": company,
        "location": "Tampa, FL", "url": f"https://example.com/{job_id}", "posted_at": "",
        **extra,
    }


class FakeSNS:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def publish(self, **kwargs):
        if self.fail:
            raise RuntimeError("SNS is down")
        self.calls.append(kwargs)
        return {"MessageId": "m-1"}


# ---------------------------------------------------------------- digest

def test_subject_format():
    subject, _ = digest.build_digest([job("a"), job("b", title="SRE")], NOW)
    assert subject == "Your daily dose of hopium: 2 new matches (Oct 13)"


def test_subject_singular_and_no_zero_padding():
    subject, _ = digest.build_digest([job("a")], datetime(2026, 11, 2, tzinfo=timezone.utc))
    assert subject == "Your daily dose of hopium: 1 new match (Nov 2)"


def test_subject_fits_sns_limit():
    subject, _ = digest.build_digest([job(str(i), title=f"T{i}") for i in range(99999)][:5], NOW)
    assert len(subject) < 100 and "\n" not in subject


def test_duplicates_grouped_by_title_and_company():
    jobs = [job("a1"), job("a2", title=" cloud engineer "), job("a3", company="VANTOR"),
            job("b1", company="Other Co")]
    subject, body = digest.build_digest(jobs, NOW)
    assert "2 new matches" in subject
    assert body.count("Vantor") == 1
    assert "Cloud Engineer (3 listings)" in body
    assert "id: a1, a2, a3" in body
    assert "Other Co" in body


def test_clearance_sponsored_flag_shows():
    _, body = digest.build_digest([job("u1", clearance_tag="clearance_sponsored")], NOW)
    assert "[TS/SCI sponsored]" in body


def test_huge_digest_is_truncated_under_sns_limit():
    jobs = [job(f"id{i}", title=f"Cloud Engineer {i}" + "x" * 500) for i in range(2000)]
    _, body = digest.build_digest(jobs, NOW)
    assert len(body.encode()) < 256 * 1024
    assert "more. Query DynamoDB for the rest." in body


# ---------------------------------------------------------------- send_digest

def test_no_new_jobs_means_no_email(monkeypatch):
    monkeypatch.setenv("DIGEST_TOPIC_ARN", "arn:aws:sns:us-east-1:1:t")
    sns = FakeSNS()
    assert handler.send_digest([], {}, sns) is False
    assert sns.calls == []


def test_sends_when_jobs_inserted(monkeypatch):
    monkeypatch.setenv("DIGEST_TOPIC_ARN", "arn:aws:sns:us-east-1:1:t")
    sns = FakeSNS()
    assert handler.send_digest([job("a")], {}, sns) is True
    assert sns.calls[0]["TopicArn"] == "arn:aws:sns:us-east-1:1:t"
    assert sns.calls[0]["Subject"].startswith("Your daily dose of hopium: 1 new match")


def test_missing_topic_skips_without_error(monkeypatch):
    monkeypatch.delenv("DIGEST_TOPIC_ARN", raising=False)
    errors = {}
    assert handler.send_digest([job("a")], errors, FakeSNS()) is False
    assert errors == {}


def test_publish_failure_is_recorded_for_the_alarm(monkeypatch):
    monkeypatch.setenv("DIGEST_TOPIC_ARN", "arn:aws:sns:us-east-1:1:t")
    errors = {}
    assert handler.send_digest([job("a")], errors, FakeSNS(fail=True)) is False
    assert "digest" in errors


# ---------------------------------------------------------------- clearance wiring

def test_active_tssci_in_description_is_dropped():
    assert handler.passes_clearance(job("a", description="Active TS/SCI required.")) is False


def test_obtainable_tssci_is_kept():
    assert handler.passes_clearance(job("a", description="Must be able to obtain a TS/SCI.")) is True


def test_usajobs_never_dropped_for_clearance():
    fed = job("u", source="usajobs", description="Active TS/SCI required.")
    assert handler.passes_clearance(fed) is True


def test_store_does_not_write_description():
    class Table:
        items = []

        def put_item(self, Item, ConditionExpression):
            self.items.append(Item)

    t = Table()
    handler.store([job("a", description="long text")], t, "2026-10-13T10:00:00+00:00")
    assert "description" not in t.items[0]
    assert t.items[0]["status"] == "JustDropped"


# ---------------------------------------------------------------- parsers

def test_greenhouse_description_unescaped_and_split():
    raw = {"jobs": [{"id": 1, "title": "SRE", "content": "&lt;p&gt;Active TS/SCI required.&lt;/p&gt;&lt;p&gt;Fun team&amp;more&lt;/p&gt;"}]}
    desc = sources.parse_greenhouse(raw, "acme")[0]["description"]
    assert "Active TS/SCI required." in desc and "Fun team&more" in desc
    assert "<" not in desc


def test_lever_description_includes_requirement_lists():
    raw = [{"id": "x", "text": "SRE", "descriptionPlain": "About us",
            "lists": [{"text": "Requirements", "content": "<li>Active TS/SCI</li>"}]}]
    desc = sources.parse_lever(raw, "acme")[0]["description"]
    assert "About us" in desc and "Active TS/SCI" in desc


def test_usajobs_tags_clearance_from_structured_field():
    raw = {"SearchResult": {"SearchResultItems": [{
        "MatchedObjectId": "123",
        "MatchedObjectDescriptor": {
            "PositionTitle": "IT Specialist", "PositionURI": "https://www.usajobs.gov/job/123",
            "UserArea": {"Details": {"SecurityClearance": "Top Secret/SCI"}},
        },
    }]}}
    assert sources.parse_usajobs(raw)[0]["clearance_tag"] == "clearance_sponsored"


def test_usajobs_no_tag_when_not_required():
    raw = {"SearchResult": {"SearchResultItems": [{
        "MatchedObjectId": "124",
        "MatchedObjectDescriptor": {
            "PositionTitle": "IT Specialist", "PositionURI": "https://www.usajobs.gov/job/124",
            "UserArea": {"Details": {"SecurityClearance": "Not Required"}},
        },
    }]}}
    assert "clearance_tag" not in sources.parse_usajobs(raw)[0]
