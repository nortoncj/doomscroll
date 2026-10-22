import pytest

from clearance import requires_active_clearance, usajobs_clearance_tag

DROP = [
    "Active TS/SCI required.",
    "Must possess a current TS/SCI clearance with polygraph.",
    "Clearance: TS/SCI",
    "Candidates must hold an active Top Secret/SCI.",
    "TS SCI with Full Scope Poly required",
    "Requires TS/SCI.",
    "Active TS/SCI required; candidates eligible for Secret will not be considered.",
    "Must be able to obtain a Secret. Active TS/SCI required.",
    "Existing TS-SCI clearance, eligibility for poly.",
]

KEEP = [
    "Must be able to obtain a TS/SCI clearance.",
    "Ability to obtain TS/SCI is required.",
    "Candidates must be eligible for TS/SCI.",
    "US citizenship and ability to obtain and maintain a Top Secret/SCI.",
    "Active TS/SCI preferred, ability to obtain required.",
    "TS/SCI is a plus.",
    "Secret clearance required.",  # not TS/SCI, out of scope for this filter
    "Build Terraform modules for AWS. No clearance needed.",
    "",
]


@pytest.mark.parametrize("text", DROP)
def test_drops_hard_requirements(text):
    assert requires_active_clearance(text) is True


@pytest.mark.parametrize("text", KEEP)
def test_keeps_obtainable_or_unrelated(text):
    assert requires_active_clearance(text) is False


def test_checks_title_and_description_together():
    assert requires_active_clearance("Cloud Engineer (Active TS/SCI)", "Fun team.") is True


def test_one_bad_sentence_drops_the_job():
    text = "Ability to obtain TS/SCI. Some roles require an active TS/SCI."
    assert requires_active_clearance(text) is True


def test_usajobs_tags_instead_of_dropping():
    assert usajobs_clearance_tag("Top Secret/SCI") == "clearance_sponsored"
    assert usajobs_clearance_tag("Not Required") is None
    assert usajobs_clearance_tag(None) is None