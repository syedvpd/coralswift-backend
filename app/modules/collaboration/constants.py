import enum


class ProjectStatus(enum.StrEnum):
    PLANNING = "planning"
    AWAITING_PARTNER = "awaiting_partner"
    ACKNOWLEDGED = "acknowledged"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# Partner-facing wording; internal names are not shown verbatim.
PROJECT_LABELS = {
    ProjectStatus.PLANNING: "Being prepared",
    ProjectStatus.AWAITING_PARTNER: "Awaiting your response",
    ProjectStatus.ACKNOWLEDGED: "Acknowledged",
    ProjectStatus.CONFIRMED: "Confirmed",
    ProjectStatus.IN_PROGRESS: "In progress",
    ProjectStatus.ON_HOLD: "On hold",
    ProjectStatus.COMPLETED: "Completed",
    ProjectStatus.CANCELLED: "Cancelled",
}


class MilestoneStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class ProjectResponseKind(enum.StrEnum):
    ACKNOWLEDGE = "acknowledge"
    CONFIRM = "confirm"
    RESPOND = "respond"
    SUBMIT_INFORMATION = "submit_information"


class CollabKind(enum.StrEnum):
    DISCUSSION = "discussion"
    MEETING = "meeting"
    FOLLOW_UP = "follow_up"


class CollabStatus(enum.StrEnum):
    OPEN = "open"
    AWAITING_PARTNER = "awaiting_partner"
    RESPONDED = "responded"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CollabAction(enum.StrEnum):
    REPLY = "reply"
    ACCEPT = "accept"  # meetings
    DECLINE = "decline"  # meetings
    COMPLETE = "complete"  # follow-ups


# Actions each kind allows from a partner.
KIND_ACTIONS = {
    CollabKind.DISCUSSION: frozenset({CollabAction.REPLY}),
    CollabKind.MEETING: frozenset({CollabAction.REPLY, CollabAction.ACCEPT, CollabAction.DECLINE}),
    CollabKind.FOLLOW_UP: frozenset({CollabAction.REPLY, CollabAction.COMPLETE}),
}


class MessageDirection(enum.StrEnum):
    INBOUND = "inbound"  # partner -> staff
    OUTBOUND = "outbound"  # staff -> partner


STAFF_SENDER_LABEL = "CoralSwift Team"  # approved label list is an open decision (D30)
