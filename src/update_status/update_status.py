"""Lambda behind PATCH /jobs/{job_id}: update a job's status.

API Gateway checks the SigV4 signature before this code ever runs, so an
unsigned request gets a 403 there and never reaches us.

Responses:
  200  updated item
  400  bad job_id, bad JSON, missing or unknown status, bad notes
  404  job doesn't exist (conditional update, so we never create one)

Named update_status.py, not handler.py, so it can't collide with the
fetch_jobs handler when pytest puts both folders on the import path.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger()
log.setLevel(logging.INFO)

# Fun names in the data, plain English in the README.
VALID_STATUSES = (
    "JustDropped",   # new
    "Mid",           # reviewed, passed
    "ShotMyShot",    # applied
    "TalkingStage",  # interviewing
    "Curved",        # rejected
    "Ghosted",       # no response
    "BagSecured",    # offer
)
MAX_NOTES_LENGTH = 2000
# Matches what fetch_jobs writes: "<source>_<id>", never a slash.
JOB_ID_PATTERN = re.compile(r"^[a-z]+_[^/\s]{1,200}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        # default=str handles the Decimals boto3 returns for numbers.
        "body": json.dumps(body, default=str),
    }


def _error_code(exc: Exception) -> str:
    return (getattr(exc, "response", None) or {}).get("Error", {}).get("Code", "")


def parse_request(event: dict[str, Any]) -> tuple[str, str, str | None]:
    """Return (job_id, status, notes) or raise ValueError with a 400 message."""
    job_id = (event.get("pathParameters") or {}).get("job_id", "")
    if not JOB_ID_PATTERN.match(job_id):
        raise ValueError("job_id must look like <source>_<id>, for example greenhouse_8737416002")

    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        raise ValueError("Body must be valid JSON") from None
    if not isinstance(body, dict):
        raise ValueError("Body must be a JSON object")

    status = body.get("status")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(VALID_STATUSES)}")

    notes = body.get("notes")
    if notes is not None:
        if not isinstance(notes, str):
            raise ValueError("notes must be a string")
        if len(notes) > MAX_NOTES_LENGTH:
            raise ValueError(f"notes must be {MAX_NOTES_LENGTH} characters or fewer")
    return job_id, status, notes


def update_job(table, job_id: str, status: str, notes: str | None, now: str) -> dict[str, Any]:
    """Conditional update. Raises if the job doesn't exist.

    notes omitted: leave existing notes alone.
    notes "":      clear them.
    """
    expression = "SET #s = :s, status_updated_at = :t"
    values: dict[str, Any] = {":s": status, ":t": now}
    if notes:
        expression += ", notes = :n"
        values[":n"] = notes
    elif notes == "":
        expression += " REMOVE notes"

    resp = table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=expression,
        ConditionExpression="attribute_exists(job_id)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return resp["Attributes"]


def _default_table():
    import boto3  # bundled in the Lambda runtime; imported lazily for tests

    return boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def lambda_handler(event, context, table=None):
    try:
        job_id, status, notes = parse_request(event)
    except ValueError as exc:
        return _response(400, {"error": str(exc)})

    try:
        item = update_job(table or _default_table(), job_id, status, notes, _now())
    except Exception as exc:
        if _error_code(exc) == "ConditionalCheckFailedException":
            return _response(404, {"error": f"No job with id {job_id}"})
        raise  # a real failure: let it 500 and show up in the logs

    caller = (((event.get("requestContext") or {}).get("authorizer") or {}).get("iam") or {}).get("userArn", "")
    log.info(json.dumps({"event": "status_updated", "job_id": job_id, "status": status, "caller": caller}))
    return _response(200, item)
