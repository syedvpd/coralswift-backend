import pytest

from app.core.exceptions import AppError
from app.modules.applications.constants import TERMINAL
from app.modules.applications.constants import PortalStatus as S
from app.modules.applications.transitions import DEDICATED_TARGETS, Actor, find_rule, resume_rule


def allowed(actor: Actor, source: S, target: S) -> bool:
    try:
        find_rule(actor, source, target)
    except AppError:
        return False
    return True


def test_reviewer_forward_path() -> None:
    path = [
        S.SUBMITTED,
        S.ELIGIBILITY_VERIFICATION,
        S.CAPABILITY_REVIEW,
        S.COMMERCIAL_LEGAL_REVIEW,
        S.PILOT_ONBOARDING,
        S.SCALE_UP,
    ]
    for a, b in zip(path, path[1:], strict=False):
        assert allowed(Actor.REVIEWER, a, b), (a, b)


def test_no_skipping_or_going_back() -> None:
    assert not allowed(Actor.REVIEWER, S.SUBMITTED, S.CAPABILITY_REVIEW)
    assert not allowed(Actor.REVIEWER, S.ELIGIBILITY_VERIFICATION, S.PILOT_ONBOARDING)
    assert not allowed(Actor.REVIEWER, S.CAPABILITY_REVIEW, S.ELIGIBILITY_VERIFICATION)
    assert not allowed(Actor.REVIEWER, S.SCALE_UP, S.PILOT_ONBOARDING)


@pytest.mark.parametrize("terminal", sorted(TERMINAL))
def test_terminal_states_are_final(terminal: S) -> None:
    for actor in Actor:
        for target in S:
            assert not allowed(actor, terminal, target)


def test_partner_cannot_use_reviewer_transitions() -> None:
    for target in (S.ELIGIBILITY_VERIFICATION, S.CAPABILITY_REVIEW, S.PILOT_ONBOARDING, S.REJECTED):
        assert not allowed(Actor.PARTNER, S.SUBMITTED, target)
    assert not allowed(Actor.PARTNER, S.SUBMITTED, S.SCALE_UP)


def test_reviewer_cannot_submit_or_withdraw_for_partner() -> None:
    assert not allowed(Actor.REVIEWER, S.DRAFT, S.SUBMITTED)
    assert not allowed(Actor.REVIEWER, S.SUBMITTED, S.WITHDRAWN)
    assert {S.INFORMATION_REQUESTED, S.WITHDRAWN, S.SUBMITTED, S.DRAFT} == set(DEDICATED_TARGETS)


def test_decisions_require_reason_and_assignment_rules() -> None:
    assert find_rule(Actor.REVIEWER, S.CAPABILITY_REVIEW, S.REJECTED).needs_reason
    assert find_rule(Actor.REVIEWER, S.COMMERCIAL_LEGAL_REVIEW, S.PILOT_ONBOARDING).needs_reason
    assert find_rule(Actor.REVIEWER, S.SUBMITTED, S.ELIGIBILITY_VERIFICATION).needs_assignee
    assert not find_rule(
        Actor.REVIEWER, S.ELIGIBILITY_VERIFICATION, S.CAPABILITY_REVIEW
    ).needs_reason


def test_partner_withdraw_allowed_before_pilot_only() -> None:
    for source in (S.DRAFT, S.SUBMITTED, S.INFORMATION_REQUESTED, S.CAPABILITY_REVIEW):
        assert allowed(Actor.PARTNER, source, S.WITHDRAWN)
    assert not allowed(Actor.PARTNER, S.PILOT_ONBOARDING, S.WITHDRAWN)


def test_resume_rule() -> None:
    assert resume_rule(S.INFORMATION_REQUESTED, S.CAPABILITY_REVIEW).actor is Actor.PARTNER
    for bad_source in (S.SUBMITTED, S.DRAFT):
        with pytest.raises(AppError):
            resume_rule(bad_source, S.SUBMITTED)
    for bad_target in (S.REJECTED, S.WITHDRAWN, S.DRAFT, S.INFORMATION_REQUESTED):
        with pytest.raises(AppError):
            resume_rule(S.INFORMATION_REQUESTED, bad_target)
