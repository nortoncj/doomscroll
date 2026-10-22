"""TS/SCI clearance filter for job postings.

Goal: drop jobs that need you to ALREADY hold TS/SCI, keep jobs where
you only need to be able to obtain it (or where it's just preferred).

Rules, applied per sentence that mentions TS/SCI:
  1. Has "obtain"/"eligible" language:
       drop only if it ALSO says active/current/existing/cleared
       and isn't framed as preferred. Otherwise keep.
  2. No "obtain" language but framed as preferred/a plus: keep.
  3. Anything else ("Active TS/SCI required", "Clearance: TS/SCI"): drop.
If any sentence says drop, the whole job drops.

Known limitation: Adzuna descriptions are truncated, so a clearance
line past the cutoff never gets seen. Those jobs slip through.
"""

import re

CLEARANCE = re.compile(
    r"\b(?:ts\s*[/\-]?\s*sci|top\s*secret\s*[/\-]\s*sci|top\s*secret\s+sci)\b",
    re.IGNORECASE,
)

# "You can get it" language.
SOFT = re.compile(
    r"\b(?:ability\s+to\s+obtain|able\s+to\s+obtain|capable\s+of\s+obtaining"
    r"|willing(?:ness)?\s+to\s+obtain|eligib(?:le|ility)|obtainable"
    r"|obtain\s+and\s+maintain|must\s+obtain|to\s+be\s+obtained)\b",
    re.IGNORECASE,
)

# "You already have it" language.
STRONG = re.compile(r"\b(?:active|current(?:ly)?|existing|in[\s\-]scope|cleared)\b", re.IGNORECASE)

PREFERRED = re.compile(r"\b(?:preferred|a\s+plus|desired|nice\s+to\s+have|bonus)\b", re.IGNORECASE)

# Sentence ends, line breaks, and bullets.
SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+|•")


def _sentence_verdict(sentence: str) -> str:
    """Return 'keep' or 'drop' for one sentence that mentions TS/SCI."""
    if SOFT.search(sentence):
        if STRONG.search(sentence) and not PREFERRED.search(sentence):
            return "drop"
        return "keep"
    if PREFERRED.search(sentence):
        return "keep"
    return "drop"


def requires_active_clearance(*texts: str) -> bool:
    """True if the posting needs an already held TS/SCI. Pass title, description, etc."""
    blob = "\n".join(t for t in texts if t)
    for sentence in SENTENCE_SPLIT.split(blob):
        if CLEARANCE.search(sentence) and _sentence_verdict(sentence) == "drop":
            return True
    return False


def usajobs_clearance_tag(security_clearance: str | None) -> str | None:
    """USAJobs' SecurityClearance field means the agency adjudicates you,
    not that you must show up cleared. Tag it, never drop on it."""
    if security_clearance and CLEARANCE.search(security_clearance):
        return "clearance_sponsored"
    return None
