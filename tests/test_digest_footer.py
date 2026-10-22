from datetime import datetime, timezone

import digest

JOB = {"job_id": "greenhouse_1", "title": "SRE", "company": "Acme", "location": "", "url": ""}
NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


def test_footer_uses_real_api_url(monkeypatch):
    monkeypatch.setenv("API_URL", "https://abc.execute-api.us-east-1.amazonaws.com/")
    _, body = digest.build_digest([JOB], NOW)
    assert "PATCH https://abc.execute-api.us-east-1.amazonaws.com/jobs/greenhouse_1 " in body


def test_footer_falls_back_to_placeholder(monkeypatch):
    monkeypatch.delenv("API_URL", raising=False)
    _, body = digest.build_digest([JOB], NOW)
    assert "<api>/jobs/greenhouse_1" in body
