"""Fetch and normalize job postings from each source.

Every source has two halves:
  fetch_<source>()  makes the HTTP call (stdlib only, no requests package)
  parse_<source>()  turns the raw JSON into a list of Job dicts

Tests only ever touch the parse_ half, using saved responses in
tests/fixtures/. CI never calls a live API.

Every parser returns the same shape:
  job_id     "<source>_<id>", safe to use in a URL path (no slashes)
  source     "greenhouse" | "lever" | "usajobs" | "adzuna"
  title, company, location, url
  posted_at  ISO 8601 string, or "" if the source didn't give one

Two optional keys, used during filtering only:
  description   plain text, for the TS/SCI clearance filter. The handler
                strips it before writing to DynamoDB.
  clearance_tag USAJobs only: "clearance_sponsored" when the posting lists
                TS/SCI. Stored, and shown in the digest.
"""

from __future__ import annotations

import html
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, NotRequired, TypedDict

import clearance

TIMEOUT_SECONDS = 20
USER_AGENT = "doomscroll/1.0 (personal job tracker)"


class Job(TypedDict):
    job_id: str
    source: str
    title: str
    company: str
    location: str
    url: str
    posted_at: str
    description: NotRequired[str]
    clearance_tag: NotRequired[str]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

# Retry transient failures: rate limits (429), server errors (5xx), and
# network blips. Waits 2s, then 5s. A 4xx like 401 or 404 is a real problem
# with our request, so it fails immediately instead of retrying.
RETRY_DELAYS_SECONDS = (2, 5)
_sleep = time.sleep  # swapped out in tests so they don't actually wait


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    return isinstance(exc, (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError))


def _get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                return json.load(resp)
        except Exception as exc:
            if attempt == len(RETRY_DELAYS_SECONDS) or not _is_retryable(exc):
                raise
            _sleep(RETRY_DELAYS_SECONDS[attempt])


def _iso(value: Any) -> str:
    """Normalize whatever date format a source uses into ISO 8601."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        # Lever sends milliseconds since epoch.
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        # USAJobs sends 4 digit fractions ("2026-09-01T00:00:00.0000"),
        # which older Pythons reject. Fall back to the date and time part.
        try:
            return datetime.fromisoformat(text[:19]).isoformat()
        except ValueError:
            return text


_TAG = re.compile(r"<[^>]+>")


def _plain(text: Any) -> str:
    """HTML (even double escaped, like Greenhouse) to plain text.

    Tags become newlines so the clearance filter still sees separate
    sentences instead of one giant run on line.
    """
    if not text:
        return ""
    text = html.unescape(html.unescape(str(text)))
    return html.unescape(_TAG.sub("\n", text)).strip()


def _job_id(source: str, raw_id: Any) -> str:
    # Slashes would break PATCH /jobs/{job_id}, so swap them out.
    return f"{source}_{str(raw_id).strip().replace('/', '-')}"


# --------------------------------------------------------------------------
# Greenhouse (public, no auth)
# --------------------------------------------------------------------------

def fetch_greenhouse(board: str) -> dict:
    # content=true adds the job description, which the clearance filter needs.
    return _get_json(
        f"https://boards-api.greenhouse.io/v1/boards/{urllib.parse.quote(board)}/jobs?content=true"
    )


def parse_greenhouse(raw: dict, board: str = "") -> list[Job]:
    jobs: list[Job] = []
    for item in raw.get("jobs", []):
        if not item.get("id") or not item.get("title"):
            continue
        jobs.append(Job(
            job_id=_job_id("greenhouse", item["id"]),
            source="greenhouse",
            title=item["title"].strip(),
            company=(item.get("company_name") or board).strip(),
            location=((item.get("location") or {}).get("name") or "").strip(),
            url=item.get("absolute_url", ""),
            posted_at=_iso(item.get("first_published") or item.get("updated_at")),
            description=_plain(item.get("content")),
        ))
    return jobs


# --------------------------------------------------------------------------
# Lever (public, no auth)
# --------------------------------------------------------------------------

def fetch_lever(company: str) -> list:
    return _get_json(f"https://api.lever.co/v0/postings/{urllib.parse.quote(company)}?mode=json")


def parse_lever(raw: list, company: str = "") -> list[Job]:
    jobs: list[Job] = []
    for item in raw or []:
        if not item.get("id") or not item.get("text"):
            continue
        cats = item.get("categories") or {}
        locations = cats.get("allLocations") or [cats.get("location") or ""]
        location = "; ".join(loc for loc in locations if loc)
        # Lever puts remote in workplaceType, not the location string.
        if item.get("workplaceType") == "remote" and "remote" not in location.lower():
            location = f"Remote; {location}" if location else "Remote"
        jobs.append(Job(
            job_id=_job_id("lever", item["id"]),
            source="lever",
            title=item["text"].strip(),
            company=company.title() if company else "",
            location=location,
            url=item.get("hostedUrl", ""),
            posted_at=_iso(item.get("createdAt")),
            # Clearance lines usually live in the requirements lists.
            description="\n".join(filter(None, [
                item.get("descriptionPlain") or "",
                *(f"{lst.get('text', '')}\n{_plain(lst.get('content'))}" for lst in item.get("lists") or []),
                item.get("additionalPlain") or "",
            ])).strip(),
        ))
    return jobs


# --------------------------------------------------------------------------
# USAJobs (API key + registered email in User-Agent)
# --------------------------------------------------------------------------

# 2210 IT Management, 0854 Computer Engineering, 0855 Electronics Engineering
USAJOBS_SERIES = "2210;0854;0855"


def fetch_usajobs(api_key: str, email: str, days_posted: int = 7) -> dict:
    params = urllib.parse.urlencode({
        "JobCategoryCode": USAJOBS_SERIES,
        "DatePosted": days_posted,
        "ResultsPerPage": 500,
    })
    return _get_json(
        f"https://data.usajobs.gov/api/search?{params}",
        headers={
            "Host": "data.usajobs.gov",
            "User-Agent": email,  # USAJobs requires the registered email here
            "Authorization-Key": api_key,
        },
    )


def parse_usajobs(raw: dict) -> list[Job]:
    jobs: list[Job] = []
    items = (raw.get("SearchResult") or {}).get("SearchResultItems") or []
    for item in items:
        d = item.get("MatchedObjectDescriptor") or {}
        url = (d.get("PositionURI") or "").replace(":443", "")
        # PositionID has slashes ("24-12198900-6898/DIHD"), so prefer the
        # numeric announcement ID, falling back to the end of the URL.
        raw_id = item.get("MatchedObjectId") or url.rstrip("/").rsplit("/", 1)[-1]
        title = (d.get("PositionTitle") or "").strip()
        if not raw_id or not title:
            continue

        location = (d.get("PositionLocationDisplay") or "").strip()
        if location.lower() in ("", "multiple locations"):
            names = [loc.get("LocationName", "") for loc in d.get("PositionLocation") or []]
            location = "; ".join(n for n in names if n) or location

        details = ((d.get("UserArea") or {}).get("Details") or {})
        if details.get("RemoteIndicator") and "remote" not in location.lower():
            location = f"Remote; {location}" if location else "Remote"

        job = Job(
            job_id=_job_id("usajobs", raw_id),
            source="usajobs",
            title=title,
            company=(d.get("OrganizationName") or d.get("DepartmentName") or "").strip(),
            location=location,
            url=url,
            posted_at=_iso(d.get("PublicationStartDate")),
        )
        # Never drop USAJobs on clearance: on fed postings TS/SCI means the
        # agency adjudicates you after the offer. Tag it instead.
        tag = clearance.usajobs_clearance_tag(details.get("SecurityClearance"))
        if tag:
            job["clearance_tag"] = tag
        jobs.append(job)
    return jobs


# --------------------------------------------------------------------------
# Adzuna (app_id + app_key)
# --------------------------------------------------------------------------

# Separate searches so broad marketing terms can't crowd tech results out
# of the page limit. Name -> (what_or keywords, max pages).
ADZUNA_SEARCHES = {
    "tech": ("devops devsecops cloud sre infrastructure embedded firmware iot", 3),
    "marketing": ("marketing applications content", 2),
}


def fetch_adzuna(app_id: str, app_key: str, keywords: str, page: int = 1, days_old: int = 7) -> dict:
    params = urllib.parse.urlencode({
        "app_id": app_id,
        "app_key": app_key,
        "what_or": keywords,
        "max_days_old": days_old,
        "results_per_page": 50,
    })
    return _get_json(f"https://api.adzuna.com/v1/api/jobs/us/search/{page}?{params}")


def parse_adzuna(raw: dict) -> list[Job]:
    jobs: list[Job] = []
    for item in raw.get("results", []):
        if not item.get("id") or not item.get("title"):
            continue
        jobs.append(Job(
            job_id=_job_id("adzuna", item["id"]),
            source="adzuna",
            title=item["title"].strip(),
            company=((item.get("company") or {}).get("display_name") or "").strip(),
            location=((item.get("location") or {}).get("display_name") or "").strip(),
            url=item.get("redirect_url", ""),
            posted_at=_iso(item.get("created")),
            # Truncated by Adzuna. A clearance line past the cutoff is missed.
            description=_plain(item.get("description")),
        ))
    return jobs
