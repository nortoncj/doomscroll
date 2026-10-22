"""Lambda entry point: fetch, filter, dedupe, store.

Flow:
  1. Load filters (filters.json is bundled next to this file).
  2. For each source: fetch, parse, filter (keywords, location, then the
     TS/SCI clearance filter). One source failing never stops the others.
  3. Conditional write each match. A job that already exists is skipped,
     so reruns are safe and only genuinely new jobs count as inserted.
  4. If anything was inserted, publish the digest to SNS. Zero new jobs
     means zero emails.
  5. Log a one-line JSON summary.
  6. If any source (or the digest) failed, raise at the very end so the
     CloudWatch alarm fires. Jobs from the working sources are already
     saved by then.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

import clearance
import digest
import filters as filters_mod
import sources
import ssm_params

log = logging.getLogger()
log.setLevel(logging.INFO)

DEFAULT_STATUS = "JustDropped"
ADZUNA_PAGE_SIZE = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _redact(text: str, secrets: list[str]) -> str:
    """Error messages can echo request URLs. Never let a key reach the logs."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _error_code(exc: Exception) -> str:
    # botocore's ClientError carries the AWS error code in .response.
    return (getattr(exc, "response", None) or {}).get("Error", {}).get("Code", "")


def passes_clearance(job: dict[str, Any]) -> bool:
    """Drop jobs that need an already held TS/SCI.

    USAJobs never gets dropped here. Its parser tags clearance instead,
    because on fed postings TS/SCI usually means they sponsor it.
    """
    if job.get("source") == "usajobs":
        return True
    return not clearance.requires_active_clearance(job.get("title", ""), job.get("description", ""))


def collect(f: filters_mod.Filters, get_param: Callable[[str], str], email: str):
    """Fetch, parse, and filter every source.

    Returns (matches, report, errors). Errors are per source and redacted.
    """
    matches: list[dict[str, Any]] = []
    report: dict[str, dict[str, int]] = {}
    errors: dict[str, str] = {}
    secrets: list[str] = []

    def run(name: str, fetch_and_parse: Callable[[], list]) -> None:
        try:
            jobs = fetch_and_parse()
        except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
            errors[name] = _redact(f"{type(exc).__name__}: {exc}", secrets)
            log.warning(json.dumps({"event": "source_failed", "source": name, "error": errors[name]}))
            return
        kept = []
        dropped_clearance = 0
        for job in jobs:
            keywords = f.match(job["title"], job["location"])
            if not keywords:
                continue
            if not passes_clearance(job):
                dropped_clearance += 1
                continue
            kept.append({**job, "matched_keywords": keywords})
        report[name] = {"fetched": len(jobs), "matched": len(kept)}
        if dropped_clearance:
            report[name]["dropped_clearance"] = dropped_clearance
        matches.extend(kept)

    for board in f.greenhouse_boards:
        run(f"greenhouse:{board}",
            lambda b=board: sources.parse_greenhouse(sources.fetch_greenhouse(b), b))

    for company in f.lever_companies:
        run(f"lever:{company}",
            lambda c=company: sources.parse_lever(sources.fetch_lever(c), c))

    def usajobs() -> list:
        if not email:
            raise RuntimeError("USAJOBS_EMAIL is not set")
        key = get_param(ssm_params.USAJOBS_API_KEY)
        secrets.append(key)
        return sources.parse_usajobs(sources.fetch_usajobs(key, email))

    def adzuna(keywords: str, max_pages: int) -> list:
        app_id = get_param(ssm_params.ADZUNA_APP_ID)
        app_key = get_param(ssm_params.ADZUNA_APP_KEY)
        secrets.extend([app_id, app_key])
        jobs: list = []
        for page in range(1, max_pages + 1):
            raw = sources.fetch_adzuna(app_id, app_key, keywords, page=page)
            jobs.extend(sources.parse_adzuna(raw))
            if len(raw.get("results", [])) < ADZUNA_PAGE_SIZE:
                break
        return jobs

    run("usajobs", usajobs)
    for search, (keywords, max_pages) in sources.ADZUNA_SEARCHES.items():
        run(f"adzuna:{search}", lambda k=keywords, m=max_pages: adzuna(k, m))
    return matches, report, errors


def store(matches: list[dict[str, Any]], table, now: str) -> list[dict[str, Any]]:
    """Insert new jobs only. Returns the items that were actually inserted."""
    inserted = []
    seen: set[str] = set()
    for job in matches:
        if job["job_id"] in seen:
            continue
        seen.add(job["job_id"])
        # description is only for filtering. Don't pay to store it.
        item = {k: v for k, v in job.items() if k != "description"}
        item.update(status=DEFAULT_STATUS, first_seen_at=now, status_updated_at=now)
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(job_id)")
        except Exception as exc:
            if _error_code(exc) == "ConditionalCheckFailedException":
                continue  # already tracked, not new
            raise
        inserted.append(item)
    return inserted


def _default_table():
    import boto3  # bundled in the Lambda runtime; imported lazily for tests

    return boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def _default_sns():
    import boto3  # bundled in the Lambda runtime; imported lazily for tests

    return boto3.client("sns")


def send_digest(inserted: list[dict[str, Any]], errors: dict[str, str], sns=None) -> bool:
    """Publish the digest if there's anything new. Returns True if sent.

    A failed publish is recorded in errors (so the alarm fires) instead of
    raising, because the jobs are already saved and won't count as new on
    the next run.
    """
    topic_arn = os.environ.get("DIGEST_TOPIC_ARN", "")
    if not inserted:
        return False
    if not topic_arn:
        log.warning(json.dumps({"event": "digest_skipped", "reason": "DIGEST_TOPIC_ARN not set"}))
        return False
    try:
        digest.publish_digest(sns or _default_sns(), topic_arn, inserted, datetime.now(timezone.utc))
    except Exception as exc:  # noqa: BLE001 - jobs are saved; alarm on it, don't lose the summary
        errors["digest"] = f"{type(exc).__name__}: {exc}"
        log.error(json.dumps({"event": "digest_failed", "error": errors["digest"]}))
        return False
    return True


def lambda_handler(event, context, table=None, get_param=None, sns=None):
    f = filters_mod.load_filters()
    matches, report, errors = collect(
        f, get_param or ssm_params.get_param, os.environ.get("USAJOBS_EMAIL", "")
    )
    inserted = store(matches, table or _default_table(), _now())
    digest_sent = send_digest(inserted, errors, sns)

    summary = {
        "event": "fetch_complete",
        "sources": report,
        "errors": errors,
        "matched": len(matches),
        "inserted": len(inserted),
        "digest_sent": digest_sent,
        "new_jobs": [
            {"job_id": j["job_id"], "title": j["title"], "company": j["company"]} for j in inserted
        ],
    }
    log.info(json.dumps(summary))

    if errors:
        raise RuntimeError(
            f"{len(errors)} source(s) failed: {', '.join(sorted(errors))}. "
            f"{len(inserted)} new job(s) from the other sources were saved."
        )
    return {"matched": len(matches), "inserted": len(inserted), "sources": report}
