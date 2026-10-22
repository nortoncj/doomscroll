"""Build and send the daily digest email through SNS.

Pure formatting lives in build_digest() so it's testable without AWS.
publish_digest() is the thin boto3 part.

Grouping: the same title at the same company shows up once, with a
"(3 listings)" suffix, instead of three near identical entries.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

# SNS caps messages at 256 KB. Stay well under it so a giant first run
# (hello, empty table) still sends instead of blowing up.
MAX_BODY_BYTES = 240_000
SUBJECT_TEMPLATE = "Your daily dose of hopium: {n} new {noun} ({date})"


def _group(jobs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group by title + company, keeping first seen order."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for job in jobs:
        key = (job.get("title", "").strip().lower(), job.get("company", "").strip().lower())
        groups.setdefault(key, []).append(job)
    return list(groups.values())


def _entry(index: int, group: list[dict[str, Any]]) -> str:
    first = group[0]
    title = first.get("title", "").strip() or "(no title)"
    if len(group) > 1:
        title += f" ({len(group)} listings)"
    if any(j.get("clearance_tag") == "clearance_sponsored" for j in group):
        title += " [TS/SCI sponsored]"

    where = " | ".join(p for p in (first.get("company", "").strip(), first.get("location", "").strip()) if p)
    ids = ", ".join(j["job_id"] for j in group)

    lines = [f"{index}. {title}"]
    if where:
        lines.append(f"   {where}")
    if first.get("url"):
        lines.append(f"   {first['url']}")
    lines.append(f"   id: {ids}")
    return "\n".join(lines)


def _footer(example_id: str) -> str:
    """A copy and paste awscurl command. API_URL comes from Terraform."""
    api = os.environ.get("API_URL", "").rstrip("/") or "<api>"
    return (
        "\nUpdate a status (JustDropped, Mid, ShotMyShot, TalkingStage, Curved, Ghosted, BagSecured):\n"
        f"awscurl --service execute-api --region us-east-1 -X PATCH {api}/jobs/{example_id} "
        "-H 'Content-Type: application/json' -d '{\"status\": \"ShotMyShot\"}'\n"
    )


def build_digest(jobs: list[dict[str, Any]], now: datetime) -> tuple[str, str]:
    """Return (subject, body). Call only when jobs is non empty.

    The date comes from `now` as given. The schedule runs at 6 AM Eastern,
    which is the same calendar day in UTC, so UTC is fine here.
    """
    groups = _group(jobs)
    n = len(groups)
    subject = SUBJECT_TEMPLATE.format(
        n=n,
        noun="match" if n == 1 else "matches",
        date=f"{now.strftime('%b')} {now.day}",
    )

    header = f"{n} new {'match' if n == 1 else 'matches'}. Go shoot your shot.\n"
    footer = _footer(groups[0][0]["job_id"])

    parts = [header]
    size = len(header.encode()) + len(footer.encode())
    for i, group in enumerate(groups, start=1):
        entry = "\n" + _entry(i, group) + "\n"
        entry_size = len(entry.encode())
        if size + entry_size > MAX_BODY_BYTES:
            parts.append(f"\n...and {n - i + 1} more. Query DynamoDB for the rest.\n")
            break
        parts.append(entry)
        size += entry_size
    parts.append(footer)
    return subject, "".join(parts)


def publish_digest(sns_client, topic_arn: str, jobs: list[dict[str, Any]], now: datetime) -> str:
    """Publish the digest. Returns the SNS MessageId."""
    subject, body = build_digest(jobs, now)
    resp = sns_client.publish(TopicArn=topic_arn, Subject=subject, Message=body)
    return resp["MessageId"]
