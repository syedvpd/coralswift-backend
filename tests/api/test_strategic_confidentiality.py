"""Strategic/M&A confidentiality across every staff access path (PRD s.14, s.28).

Super administrators may read strategic enquiries. Every other role must never receive them,
nor a count, reference, name, email or text that reveals one, from any admin endpoint."""

import re
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.constants import StaffRole
from tests import factories
from tests.helpers import make_staff, staff_headers

PUB = "/api/v1/enquiries"
SECRET_EMAIL = "zzstrat.owner@example.org"
SECRET_NAME = "Zed Strategicson"
SECRET_COMPANY = "ZZSTRATCO Holdings Ltd"
MARKER = "TOP-SECRET-MARKER"


def _setup(client: TestClient, db: Session, settings: Settings) -> dict[str, Any]:
    strategic = client.post(
        f"{PUB}/strategic",
        json=factories.strategic(
            full_name=SECRET_NAME, business_email=SECRET_EMAIL, company_name=SECRET_COMPANY
        ),
    )
    general = client.post(
        f"{PUB}/contact",
        json=factories.contact(
            business_email="general.person@example.net", full_name="Gina General"
        ),
    )
    assert strategic.status_code == 201 and general.status_code == 201
    return {
        "strategic_ref": strategic.json()["data"]["reference_number"],
        "general_ref": general.json()["data"]["reference_number"],
        "sa": staff_headers(client, make_staff(db, settings, StaffRole.SUPER_ADMINISTRATOR)),
        "bdm": staff_headers(
            client, make_staff(db, settings, StaffRole.BUSINESS_DEVELOPMENT_MANAGER)
        ),
        "reviewer": staff_headers(client, make_staff(db, settings, StaffRole.PARTNER_REVIEWER)),
        "content": staff_headers(client, make_staff(db, settings, StaffRole.CONTENT_ADMINISTRATOR)),
    }


def _static_get_routes(client: TestClient, prefix: str) -> list[str]:
    """Every GET path under `prefix` (from the OpenAPI document) that needs no path parameter."""
    paths = client.get("/openapi.json").json()["paths"]
    return sorted(
        p for p, ops in paths.items() if p.startswith(prefix) and "get" in ops and "{" not in p
    )


def _leaks(text: str, refs: list[str]) -> list[str]:
    needles = [SECRET_EMAIL, SECRET_NAME, SECRET_COMPANY, MARKER, *refs]
    return [n for n in needles if re.search(re.escape(n), text, re.IGNORECASE)]


def test_non_super_roles_never_receive_strategic_data_from_any_admin_get(
    client: TestClient, db: Session, settings: Settings
) -> None:
    ctx = _setup(client, db, settings)
    paths = _static_get_routes(client, "/api/v1/admin") + _static_get_routes(
        client, "/api/v1/reviewer"
    )
    assert len(paths) > 15  # the sweep is not vacuous
    for role in ("bdm", "reviewer", "content"):
        for path in paths:
            r = client.get(path, headers=ctx[role])
            assert r.status_code in (200, 403), (role, path, r.status_code)
            leaked = _leaks(r.text, [ctx["strategic_ref"]])
            assert not leaked, f"{role} got strategic data from {path}: {leaked}"
    # contrast: the super administrator does see it, and the general enquiry is visible to the BDM
    assert ctx["strategic_ref"] in client.get("/api/v1/admin/enquiries", headers=ctx["sa"]).text
    assert ctx["general_ref"] in client.get("/api/v1/admin/enquiries", headers=ctx["bdm"]).text


def test_strategic_data_not_in_bdm_exports_search_or_detail(
    client: TestClient, db: Session, settings: Settings
) -> None:
    ctx = _setup(client, db, settings)
    for q in (SECRET_COMPANY, SECRET_EMAIL, ctx["strategic_ref"], "zzstrat"):
        r = client.get("/api/v1/admin/enquiries", params={"q": q}, headers=ctx["bdm"])
        assert r.status_code == 200 and r.json()["data"] == [] and r.json()["meta"]["total"] == 0
    csv = client.get("/api/v1/admin/reports/enquiries.csv", headers=ctx["bdm"])
    assert csv.status_code == 200 and not _leaks(csv.text, [ctx["strategic_ref"]])
    sa_list = client.get("/api/v1/admin/enquiries?type=strategic", headers=ctx["sa"]).json()["data"]
    sid = sa_list[0]["id"]
    for role in ("bdm", "reviewer", "content"):
        for suffix in ("", "/documents/00000000-0000-0000-0000-000000000000/download"):
            r = client.get(f"/api/v1/admin/enquiries/{sid}{suffix}", headers=ctx[role])
            assert r.status_code in (403, 404), (role, suffix, r.status_code)
        for action in ("assign", "follow-ups"):
            r = client.post(
                f"/api/v1/admin/enquiries/{sid}/{action}",
                headers=ctx[role],
                json={"assigned_user_id": None, "note": "x"},
            )
            assert r.status_code in (403, 404, 422), (role, action, r.status_code)
        r = client.patch(
            f"/api/v1/admin/enquiries/{sid}", headers=ctx[role], json={"priority": "high"}
        )
        assert r.status_code in (403, 404, 422), (role, r.status_code)


def test_aggregates_for_bdm_exclude_strategic(
    client: TestClient, db: Session, settings: Settings
) -> None:
    ctx = _setup(client, db, settings)
    sa = client.get("/api/v1/admin/overview", headers=ctx["sa"]).json()["data"]
    bdm = client.get("/api/v1/admin/overview", headers=ctx["bdm"]).json()["data"]
    assert "strategic" in str(sa).lower() or sa != bdm  # SA sees more than BDM
    kpi_sa = client.get("/api/v1/admin/reports/kpis", headers=ctx["sa"]).text
    kpi_bdm = client.get("/api/v1/admin/reports/kpis", headers=ctx["bdm"]).text
    assert "strategic" in kpi_sa and "strategic" not in kpi_bdm
