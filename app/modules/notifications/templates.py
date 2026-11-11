"""HTML + text email templates; response-time promises need SLA approval."""

from html import escape
from string import Template

from app.modules.notifications.constants import TemplateKey

TYPE_LABELS = {
    "general": "general enquiry",
    "project": "project enquiry",
    "partner": "partner application",
    "strategic": "strategic discussion enquiry",
    "meeting": "meeting request",
}
_PHASE1_KEYS = {
    TemplateKey.ACK_GENERAL,
    TemplateKey.ACK_PROJECT,
    TemplateKey.ACK_PARTNER,
    TemplateKey.ACK_STRATEGIC,
    TemplateKey.INTERNAL_NEW_ENQUIRY,
    TemplateKey.ACK_MEETING,
}
_FOOTER = "Coral Swift - Connecting Global Opportunities with Delivery Excellence"


PORTAL_NOTE = (
    "Sign in to the partner portal to view details. We never send message content by email."
)


def _portal_lines(key: TemplateKey, ctx: dict[str, str]) -> tuple[str, list[str]]:
    """Phase 2 emails carry only references, status labels and one-time links, never messages."""
    ref = ctx.get("reference", "")
    greet = f"Dear {ctx.get('name') or 'Sir/Madam'},"
    link = ctx.get("link", "")
    if key is TemplateKey.PARTNER_INVITATION:
        return "Your Coral Swift portal invitation", [
            greet,
            "You have been invited to the Coral Swift portal.",
            f"Activate your account and set a password: {link}",
            "The link is single-use and expires. If you did not expect this, ignore this email.",
        ]
    if key is TemplateKey.PASSWORD_RESET:
        return "Reset your Coral Swift password", [
            greet,
            "A password reset was requested for your account.",
            f"Choose a new password: {link}",
            "The link is single-use and expires. If you did not request it, ignore this email.",
        ]
    if key is TemplateKey.APPLICATION_SUBMITTED:
        return f"Application {ref} submitted", [
            greet,
            f"Your partner application {ref} was submitted for review.",
            "This message confirms receipt only; it is not an approval or commitment.",
        ]
    if key is TemplateKey.INFORMATION_REQUESTED:
        return f"Additional information requested for {ref}", [
            greet,
            f"The reviewer requested additional information for application {ref}.",
            PORTAL_NOTE,
        ]
    if key is TemplateKey.PARTNER_RESPONSE_RECEIVED:
        return f"Partner response received for {ref}", [
            f"A partner responded on application {ref}.",
            PORTAL_NOTE,
        ]
    if key is TemplateKey.APPLICATION_STATUS_CHANGED:
        return f"Application {ref} status updated", [
            greet,
            f"The status of application {ref} is now: {ctx.get('status_label', '')}.",
            PORTAL_NOTE,
        ]
    if key is TemplateKey.MEETING_DECISION:
        return f"Meeting request {ref}: {ctx.get('status_label', '')}", [
            greet,
            f"Your meeting request {ref} is {ctx.get('status_label', '').lower()}.",
            *([f"Time: {ctx['meeting_time']}"] if ctx.get("meeting_time") else []),
            "Times are shown in the time zone you requested.",
        ]
    if key is TemplateKey.SLA_ESCALATION:
        return f"Response target missed for {ref}", [
            f"The first-response target for {ctx.get('enquiry_type', 'enquiry')} {ref} has passed.",
            "Open the admin console to follow up.",
        ]
    if key is TemplateKey.REVIEWER_ASSIGNED:
        return f"Application {ref} assigned to you", [
            f"Application {ref} was assigned to you.",
            PORTAL_NOTE,
        ]
    if key is TemplateKey.PRIVACY_REQUEST_ACK:
        return f"We received your privacy request {ref}", [
            greet,
            f"We received your data request {ref}.",
            "We may contact you to verify your identity before acting on it.",
            *(
                [f"Confirm that this request came from you: {ctx['link']}"]
                if ctx.get("link")
                else []
            ),
        ]
    if key is TemplateKey.EXPIRY_REMINDER:
        return "A document in your partner profile is about to expire", [
            greet,
            f"Your {ctx.get('category', '')} document expires on {ctx.get('expires_on', '')}.",
            "Sign in to the partner portal to upload a replacement.",
        ]
    if key is TemplateKey.STAFF_REPLY:  # staff-authored; the only template that carries free text
        return ctx.get("subject", "A message from Coral Swift"), [
            greet,
            *[line for line in ctx.get("body", "").splitlines() if line.strip()],
            f"Reference: {ref}" if ref else "",
        ]
    if key is TemplateKey.PROFILE_CHANGE_DECISION:
        return "Your profile change request was reviewed", [
            greet,
            f"Your profile change request was {ctx.get('status_label', '').lower()}.",
            PORTAL_NOTE,
        ]
    return f"Decision recorded for application {ref}", [  # APPLICATION_DECISION
        greet,
        f"A decision was recorded on application {ref}: {ctx.get('status_label', '')}.",
        PORTAL_NOTE,
    ]


def render(key: TemplateKey, ctx: dict[str, str]) -> tuple[str, str, str]:
    """Return (subject, text, html). Context values are HTML-escaped for the HTML body."""
    if key not in _PHASE1_KEYS:
        subject, lines = _portal_lines(key, ctx)
        text = "\n".join([*lines, "", _FOOTER])
        body = "".join(f"<p>{escape(line)}</p>" for line in lines)
        return (
            subject,
            text,
            f"<html><body>{body}<p><small>{escape(_FOOTER)}</small></p></body></html>",
        )
    ref = ctx.get("reference", "")
    label = TYPE_LABELS.get(ctx.get("enquiry_type", ""), "enquiry")
    if key is TemplateKey.INTERNAL_NEW_ENQUIRY:
        lines = [f"New {label} received.", f"Reference: {ref}"]
        if ctx.get("name"):  # omitted for strategic: keep confidential records out of email
            lines.append(
                f"From: {ctx['name']}" + (f" ({ctx['company']})" if ctx.get("company") else "")
            )
        subject = f"[Coral Swift] New {label} {ref}"
    else:
        lines = [
            f"Dear {ctx.get('name') or 'Sir/Madam'},",
            f"Thank you. We have received your {label}.",
            f"Your reference number is {ref}. Please quote it in any correspondence.",
            "This message confirms receipt only; it is not an offer, approval or commitment.",
        ]
        if ctx.get("enquiry_type") == "meeting":
            lines[3] = "The meeting is not confirmed until a time has been agreed with you."
        if ctx.get("response_hours"):
            lines.insert(3, f"We aim to respond within {ctx['response_hours']} hours.")
        subject = f"We received your {label} ({ref})"
    text = "\n".join([*lines, "", _FOOTER])
    body = "".join(f"<p>{escape(line)}</p>" for line in lines)
    html = f"<html><body>{body}<p><small>{escape(_FOOTER)}</small></p></body></html>"
    return subject, text, html


NL, CR = chr(10), chr(13)
ALLOWED_PLACEHOLDERS = frozenset(
    {
        "name",
        "reference",
        "status_label",
        "link",
        "enquiry_type",
        "company",
        "category",
        "expires_on",
        "meeting_time",
    }
)
_ONE_TIME_LINK_KEYS = {"partner_invitation", "password_reset"}


def placeholders_in(*texts: str | None) -> set[str]:
    found: set[str] = set()
    for text in texts:
        if text:
            for match in Template.pattern.finditer(text):
                name = match.group("named") or match.group("braced")
                if name:
                    found.add(name)
                elif match.group("invalid") is not None:
                    found.add("$")
    return found


def validate_template(key: str, subject: str, text: str, html: str | None) -> None:
    """Admin-edited templates may use only known placeholders; the subject is one line."""
    if NL in subject or CR in subject:
        raise ValueError("subject must be a single line")
    bad = placeholders_in(subject, text, html) - ALLOWED_PLACEHOLDERS
    if bad:
        raise ValueError(f"unknown placeholders: {sorted(bad)}")
    if key in _ONE_TIME_LINK_KEYS and "link" not in placeholders_in(text):
        raise ValueError("this template must contain the $link placeholder")


def render_override(
    subject: str, text: str, html: str | None, ctx: dict[str, str]
) -> tuple[str, str, str]:
    safe = {k: str(v) for k, v in ctx.items() if k in ALLOWED_PLACEHOLDERS}
    escaped = {k: escape(v) for k, v in safe.items()}
    out_text = Template(text).safe_substitute(safe)
    if html:
        out_html = Template(html).safe_substitute(escaped)
    else:
        out_html = "".join(f"<p>{escape(line)}</p>" for line in out_text.split(NL))
        out_html = f"<html><body>{out_html}</body></html>"
    return Template(subject).safe_substitute(safe).replace(NL, " "), out_text, out_html
