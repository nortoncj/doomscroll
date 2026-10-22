"""Tests for PATCH /jobs/{job_id}. Every response path gets one.

The 403 for unsigned calls comes from API Gateway, not this code, so it's
tested for real with curl after deploy (see README).
"""

import base64
import json

import update_status as us


class ConditionFailed(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class Throttled(Exception):
    response = {"Error": {"Code": "ProvisionedThroughputExceededException"}}


class FakeTable:
    def __init__(self, items=None, error=None):
        self.items = items if items is not None else {"greenhouse_1": {"job_id": "greenhouse_1", "status": "JustDropped", "notes": "old"}}
        self.error = error
        self.calls = []

    def update_item(self, **kw):
        self.calls.append(kw)
        if self.error:
            raise self.error
        job_id = kw["Key"]["job_id"]
        if job_id not in self.items:
            raise ConditionFailed()
        item = self.items[job_id]
        item["status"] = kw["ExpressionAttributeValues"][":s"]
        item["status_updated_at"] = kw["ExpressionAttributeValues"][":t"]
        if ":n" in kw["ExpressionAttributeValues"]:
            item["notes"] = kw["ExpressionAttributeValues"][":n"]
        if "REMOVE notes" in kw["UpdateExpression"]:
            item.pop("notes", None)
        return {"Attributes": dict(item)}


def event(job_id="greenhouse_1", body=None, raw=None, b64=False):
    text = raw if raw is not None else json.dumps(body if body is not None else {"status": "ShotMyShot"})
    if b64:
        text = base64.b64encode(text.encode()).decode()
    return {"pathParameters": {"job_id": job_id}, "body": text, "isBase64Encoded": b64,
            "requestContext": {"authorizer": {"iam": {"userArn": "arn:aws:sts::1:assumed-role/x/chris"}}}}


def call(ev, table=None):
    resp = us.lambda_handler(ev, None, table=table or FakeTable())
    return resp["statusCode"], json.loads(resp["body"])


# ---------------------------------------------------------------- 200

def test_valid_update_returns_200_and_item():
    t = FakeTable()
    code, body = call(event(), t)
    assert code == 200
    assert body["status"] == "ShotMyShot"
    assert body["status_updated_at"]
    assert t.calls[0]["ConditionExpression"] == "attribute_exists(job_id)"


def test_every_status_is_accepted():
    for status in us.VALID_STATUSES:
        code, _ = call(event(body={"status": status}))
        assert code == 200, status


def test_notes_are_saved():
    code, body = call(event(body={"status": "TalkingStage", "notes": "Recruiter call Friday"}))
    assert code == 200 and body["notes"] == "Recruiter call Friday"


def test_omitting_notes_keeps_existing_ones():
    code, body = call(event(body={"status": "Mid"}))
    assert code == 200 and body["notes"] == "old"


def test_empty_notes_clears_them():
    code, body = call(event(body={"status": "Mid", "notes": ""}))
    assert code == 200 and "notes" not in body


def test_base64_body_is_decoded():
    code, _ = call(event(raw=json.dumps({"status": "Curved"}), b64=True))
    assert code == 200


# ---------------------------------------------------------------- 400

def test_unknown_status_is_400():
    code, body = call(event(body={"status": "Applied"}))
    assert code == 400 and "ShotMyShot" in body["error"]


def test_status_is_case_sensitive():
    code, _ = call(event(body={"status": "shotmyshot"}))
    assert code == 400


def test_missing_status_is_400():
    code, _ = call(event(body={"notes": "hi"}))
    assert code == 400


def test_bad_json_is_400():
    code, body = call(event(raw="{not json"))
    assert code == 400 and "JSON" in body["error"]


def test_empty_body_is_400():
    code, _ = call(event(raw=""))
    assert code == 400


def test_json_array_body_is_400():
    code, _ = call(event(raw='["ShotMyShot"]'))
    assert code == 400


def test_non_string_notes_is_400():
    code, _ = call(event(body={"status": "Mid", "notes": 42}))
    assert code == 400


def test_huge_notes_is_400():
    code, _ = call(event(body={"status": "Mid", "notes": "x" * (us.MAX_NOTES_LENGTH + 1)}))
    assert code == 400


def test_bad_job_id_is_400_and_never_touches_dynamodb():
    t = FakeTable()
    for bad in ("", "nounderscore", "Greenhouse_1", "greenhouse_", "a_b c"):
        code, _ = call(event(job_id=bad), t)
        assert code == 400, bad
    assert t.calls == []


# ---------------------------------------------------------------- 404

def test_missing_job_is_404():
    code, body = call(event(job_id="greenhouse_999"))
    assert code == 404 and "greenhouse_999" in body["error"]


# ---------------------------------------------------------------- 500

def test_other_dynamodb_errors_raise():
    try:
        call(event(), FakeTable(error=Throttled()))
    except Throttled:
        return
    raise AssertionError("expected the error to propagate")
