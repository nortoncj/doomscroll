"""Keyword and location filtering for job postings.

Matching is whole word and case insensitive. "iot" matches "IoT Engineer"
but not "Patriot Systems Engineer". Terms can contain spaces and
punctuation ("st. petersburg").
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "filters.json")


def _compile(terms: list[str]) -> re.Pattern | None:
    """Build one regex that matches any term as a whole word."""
    cleaned = [t.strip() for t in terms if t and t.strip()]
    if not cleaned:
        return None
    # Longest first, so "platform engineer" wins over shorter overlaps.
    cleaned.sort(key=len, reverse=True)
    alternation = "|".join(re.escape(t) for t in cleaned)
    # Lookarounds work like \b but also handle terms that start or end
    # with punctuation.
    return re.compile(rf"(?<!\w)(?:{alternation})(?!\w)", re.IGNORECASE)


@dataclass(frozen=True)
class Filters:
    include: re.Pattern | None
    exclude: re.Pattern | None
    locations: re.Pattern | None
    greenhouse_boards: tuple[str, ...]
    lever_companies: tuple[str, ...]

    def match(self, title: str, location: str = "") -> list[str]:
        """Return the include keywords found in the title. Empty list = skip.

        1. No title, or no include keywords configured: skip.
        2. Any exclude keyword in the title: skip.
        3. Locations configured and the job's location matches none: skip.
           Jobs with NO location are kept. Silently dropping a good job is
           worse than one extra line in the digest.
        4. Otherwise return every include keyword that matched.
        """
        if not title or self.include is None:
            return []
        if self.exclude is not None and self.exclude.search(title):
            return []
        if self.locations is not None and location and not self.locations.search(location):
            return []
        return sorted({m.group(0).lower() for m in self.include.finditer(title)})


def load_filters(path: str | None = None) -> Filters:
    """Load filters from JSON. FILTERS_PATH env var overrides the default."""
    path = path or os.environ.get("FILTERS_PATH", DEFAULT_PATH)
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return Filters(
        include=_compile(raw.get("include_keywords", [])),
        exclude=_compile(raw.get("exclude_keywords", [])),
        locations=_compile(raw.get("locations", [])),
        greenhouse_boards=tuple(raw.get("greenhouse_boards", [])),
        lever_companies=tuple(raw.get("lever_companies", [])),
    )
