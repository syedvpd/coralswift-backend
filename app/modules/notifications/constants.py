import enum


class DeliveryStatus(enum.StrEnum):
    PENDING = "pending"
    SENT = "sent"  # a real provider accepted the message
    LOGGED = "logged"  # console backend only: nothing was delivered
    FAILED = "failed"


class NotificationType(enum.StrEnum):
    ACKNOWLEDGEMENT = "acknowledgement"
    INTERNAL = "internal"
    ACCOUNT = "account"
    APPLICATION = "application"


class TemplateKey(enum.StrEnum):
    ACK_GENERAL = "ack_general"
    ACK_PROJECT = "ack_project"
    ACK_PARTNER = "ack_partner"
    ACK_STRATEGIC = "ack_strategic"
    INTERNAL_NEW_ENQUIRY = "internal_new_enquiry"
    PARTNER_INVITATION = "partner_invitation"
    PASSWORD_RESET = "password_reset"
    APPLICATION_SUBMITTED = "application_submitted"
    INFORMATION_REQUESTED = "information_requested"
    PARTNER_RESPONSE_RECEIVED = "partner_response_received"
    APPLICATION_STATUS_CHANGED = "application_status_changed"
    APPLICATION_DECISION = "application_decision"
    ACK_MEETING = "ack_meeting"
    MEETING_DECISION = "meeting_decision"
    REVIEWER_ASSIGNED = "reviewer_assigned"
    SLA_ESCALATION = "sla_escalation"
    PRIVACY_REQUEST_ACK = "privacy_request_ack"
    EXPIRY_REMINDER = "expiry_reminder"
    PROFILE_CHANGE_DECISION = "profile_change_decision"
