"""Invalidate caches after a successful COMMIT of the rows they were built from.

Flushed ORM changes are mapped to namespaces and recorded on the session; after_commit
invalidates them, so a rolled-back transaction invalidates nothing. Covers every ORM code path
(routers, services, maintenance job). Bulk UPDATE/DELETE statements bypass the ORM hook, so those
call `mark_dirty(session, ns)` explicitly (the two Notification bulk updates).

Namespaces are per feature, and per organisation / recipient where the row carries that id, so one
partner's change never drops another partner's entries.
"""

import hashlib
from collections.abc import Callable
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.modules.admin.models import EnquiryFollowUp, SystemSetting
from app.modules.applications.models import PortalApplication
from app.modules.collaboration.models import PartnerProject
from app.modules.content.models import ContentItem
from app.modules.enquiries.models import Contact, Enquiry
from app.modules.notifications.models import Notification
from app.modules.organizations.models import PartnerOrganization
from app.modules.partner_documents.models import PartnerDocumentVersion
from app.modules.performance.models import PerformanceEntry
from app.modules.projects.models import ProjectEnquiry
from app.modules.strategic.models import StrategicEnquiry

NS_PUBLIC_CONTENT = "public-content"
NS_ADMIN_OVERVIEW = "admin-overview"
NS_ADMIN_ENQUIRIES = "admin-enquiries"
NS_ADMIN_ORGS = "admin-orgs"
NS_ADMIN_SETTINGS = "admin-settings"
NS_ADMIN_REPORTS = "admin-reports"


def ns_org(org_id: Any, feature: str) -> str:
    return f"po:{org_id}:{feature}"


def ns_notif(email: str) -> str:
    """Per recipient; hashed so e-mail addresses are not Redis key names."""
    return "notif:" + hashlib.sha256(email.strip().lower().encode()).hexdigest()[:24]


def _fixed(*names: str) -> Callable[[Any], list[str]]:
    return lambda _obj: list(names)


# model -> namespaces its changes invalidate
_WATCHED: dict[type, Callable[[Any], list[str]]] = {
    ContentItem: _fixed(NS_PUBLIC_CONTENT),
    Enquiry: _fixed(NS_ADMIN_OVERVIEW, NS_ADMIN_ENQUIRIES, NS_ADMIN_REPORTS),
    Contact: _fixed(NS_ADMIN_ENQUIRIES),
    ProjectEnquiry: _fixed(NS_ADMIN_ENQUIRIES),
    StrategicEnquiry: _fixed(NS_ADMIN_ENQUIRIES),
    EnquiryFollowUp: _fixed(NS_ADMIN_REPORTS),
    PortalApplication: _fixed(NS_ADMIN_OVERVIEW, NS_ADMIN_ORGS),
    PartnerOrganization: _fixed(NS_ADMIN_ORGS),
    PartnerDocumentVersion: _fixed(NS_ADMIN_REPORTS),
    SystemSetting: _fixed(NS_ADMIN_SETTINGS),
    PartnerProject: lambda o: [ns_org(o.organization_id, "projects")],
    PerformanceEntry: lambda o: [ns_org(o.organization_id, "performance")],
    Notification: lambda o: [ns_notif(o.recipient), NS_ADMIN_REPORTS],
}
_KEY = "cache_dirty"
_registered = False


def mark_dirty(session: Session, *namespaces: str) -> None:
    """Invalidate these namespaces when (and only if) the session's transaction commits."""
    session.info.setdefault(_KEY, set()).update(namespaces)


def _before_flush(session: Session, _: Any, __: Any) -> None:
    for obj in (*session.new, *session.dirty, *session.deleted):
        resolver = _WATCHED.get(type(obj))
        if resolver:
            mark_dirty(session, *resolver(obj))


def _after_commit(session: Session) -> None:
    dirty: set[str] = session.info.pop(_KEY, set())
    cache = get_cache()
    if cache is not None:
        for ns in dirty:
            cache.invalidate(ns)


def _after_rollback(session: Session) -> None:
    session.info.pop(_KEY, None)


def register_cache_hooks() -> None:
    global _registered  # noqa: PLW0603
    if _registered:
        return
    event.listen(Session, "before_flush", _before_flush)
    event.listen(Session, "after_commit", _after_commit)
    event.listen(Session, "after_rollback", _after_rollback)
    _registered = True
