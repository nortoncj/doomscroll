"""Read API keys from SSM Parameter Store.

Values are cached for the life of the Lambda container, so warm runs
don't call SSM again. Values are never logged.

Named ssm_params, not secrets, because "secrets" would shadow Python's
built in secrets module.
"""

from __future__ import annotations

import os

PLACEHOLDER = "CHANGE_ME"

USAJOBS_API_KEY = "usajobs/api_key"
ADZUNA_APP_ID = "adzuna/app_id"
ADZUNA_APP_KEY = "adzuna/app_key"

_cache: dict[str, str] = {}


class MissingSecretError(RuntimeError):
    """A parameter still holds the Terraform placeholder value."""


def _prefix() -> str:
    return os.environ.get("SSM_PREFIX", "/doomscroll").rstrip("/")


def get_param(name: str, client=None) -> str:
    """Return the decrypted value of /<prefix>/<name>."""
    full_name = f"{_prefix()}/{name}"
    if full_name in _cache:
        return _cache[full_name]

    if client is None:
        import boto3  # bundled in the Lambda runtime; imported lazily for tests

        client = boto3.client("ssm")

    value = client.get_parameter(Name=full_name, WithDecryption=True)["Parameter"]["Value"]

    if value == PLACEHOLDER:
        raise MissingSecretError(
            f"{full_name} is still {PLACEHOLDER}. Set it with: "
            f"aws ssm put-parameter --name {full_name} --type SecureString --overwrite --value <value>"
        )

    _cache[full_name] = value
    return value


def clear_cache() -> None:
    """For tests."""
    _cache.clear()
