"""Single source of truth for application state changes.

Each rule defines the allowed actor, source states and required inputs. Nothing else in the
code base may assign `PortalApplication.status`; use `applications.service.transition`.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.core.exceptions import AppError
from app.modules.applications.constants import TERMINAL
from app.modules.applications.constants import PortalStatus as S


class Actor(StrEnum):
    PARTNER = "partner"
    REVIEWER = "reviewer"


@dataclass(frozen=True)
class Rule:
    actor: Actor
    sources: frozenset[S]
    target: S
    needs_reason: bool = False
    needs_assignee: bool = False  # an assigned reviewer must exist


_REVIEW_STAGES = frozenset(
    {S.ELIGIBILITY_VERIFICATION, S.CAPABILITY_REVIEW, S.COMMERCIAL_LEGAL_REVIEW}
)
_ACTIVE_FOR_REVIEWER = frozenset({S.SUBMITTED}) | _REVIEW_STAGES

RULES: tuple[Rule, ...] = (
    # partner actions (each is reachable only through its named endpoint)
    Rule(Actor.PARTNER, frozenset({S.DRAFT}), S.SUBMITTED),
    Rule(
        Actor.PARTNER,
        frozenset({S.DRAFT, S.SUBMITTED, S.INFORMATION_REQUESTED}) | _REVIEW_STAGES,
        S.WITHDRAWN,
    ),
    # reviewer forward path
    Rule(Actor.REVIEWER, frozenset({S.SUBMITTED}), S.ELIGIBILITY_VERIFICATION, needs_assignee=True),
    Rule(Actor.REVIEWER, frozenset({S.ELIGIBILITY_VERIFICATION}), S.CAPABILITY_REVIEW),
    Rule(Actor.REVIEWER, frozenset({S.CAPABILITY_REVIEW}), S.COMMERCIAL_LEGAL_REVIEW),
    Rule(
        Actor.REVIEWER,
        frozenset({S.COMMERCIAL_LEGAL_REVIEW}),
        S.PILOT_ONBOARDING,
        needs_reason=True,
    ),
    Rule(Actor.REVIEWER, frozenset({S.PILOT_ONBOARDING}), S.SCALE_UP, needs_reason=True),
    # reviewer outcomes
    Rule(Actor.REVIEWER, _ACTIVE_FOR_REVIEWER, S.INFORMATION_REQUESTED, needs_reason=True),
    Rule(
        Actor.REVIEWER,
        _ACTIVE_FOR_REVIEWER | {S.PILOT_ONBOARDING},
        S.REJECTED,
        needs_reason=True,
    ),
)

# Targets that have a dedicated endpoint and so cannot be requested through the generic one.
DEDICATED_TARGETS = frozenset({S.INFORMATION_REQUESTED, S.WITHDRAWN, S.SUBMITTED, S.DRAFT})


def invalid() -> AppError:
    return AppError("This status change is not allowed", status_code=409, code="INVALID_TRANSITION")


def find_rule(actor: Actor, source: S, target: S) -> Rule:
    if source in TERMINAL:
        raise invalid()
    for rule in RULES:
        if rule.actor is actor and rule.target is target and source in rule.sources:
            return rule
    raise invalid()


def resume_rule(source: S, target: S) -> Rule:
    """Information_requested -> the stage it came from (partner resubmission)."""
    if (
        source is not S.INFORMATION_REQUESTED
        or target in TERMINAL
        or target in (S.DRAFT, S.INFORMATION_REQUESTED)
    ):
        raise invalid()
    return Rule(Actor.PARTNER, frozenset({S.INFORMATION_REQUESTED}), target)


def allowed_targets(actor: Actor, source: S) -> list[S]:
    """Statuses `actor` may move an application to from `source` (information_requested resumes the
    stage it came from, which only the partner can do and which depends on the application)."""
    if source in TERMINAL:
        return []
    out: list[S] = []
    for rule in RULES:
        if rule.actor is actor and source in rule.sources and rule.target not in out:
            out.append(rule.target)
    return out


def transition_table(actor: Actor) -> list[dict[str, object]]:
    """Every rule for `actor`, for clients: from -> to, whether a reason is required."""
    rows: list[dict[str, object]] = []
    for rule in RULES:
        if rule.actor is actor:
            for source in sorted(rule.sources, key=lambda s: s.value):
                rows.append(
                    {
                        "from": source.value,
                        "to": rule.target.value,
                        "needs_reason": rule.needs_reason,
                        "needs_assigned_reviewer": rule.needs_assignee,
                        "dedicated_endpoint": rule.target in DEDICATED_TARGETS,
                    }
                )
    return rows
