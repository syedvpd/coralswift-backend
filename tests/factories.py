import io
import zipfile
from typing import Any

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<doc/>")
    return buf.getvalue()


def _merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    return {**base, **overrides}


def submitter(**o: Any) -> dict[str, Any]:
    return _merge(
        {
            "full_name": "Asha Rao",
            "designation": "Director",
            "business_email": "Asha.Rao@Example.com",
            "phone": "+91 98765 43210",
            "country": "in",
            "company_name": "Rao Systems Pvt Ltd",
            "privacy_consent": True,
        },
        o,
    )


def contact(**o: Any) -> dict[str, Any]:
    return _merge(
        submitter(),
        {"enquiry_type": "services", "message": "We would like to know more about ERP.", **o},
    )


def project(**o: Any) -> dict[str, Any]:
    return _merge(
        submitter(),
        {
            "project_category": "erp_implementation",
            "requirement_summary": "HRMS and finance ERP rollout",
            "scope": "Phase 1: HRMS. Phase 2: finance.",
            "expected_timeline": "6 months",
            "estimated_volume": "500 users",
            "geography": "United States",
            "security_constraints": "SSO required",
            **o,
        },
    )


def partner(**o: Any) -> dict[str, Any]:
    return _merge(
        submitter(),
        {
            "designation": "Managing Director",
            "website": "https://rao.example.com",
            "year_established": 2015,
            "registered_address": "12 MG Road, Hyderabad",
            "company_country": "IN",
            "preferred_engagement_pathway": "direct_project_engagement",
            "workforce_range": "50_to_100",
            "turnover_range": "inr_2_to_10_crore",
            "service_categories": ["erp", "web_applications"],
            "infrastructure_summary": "Two delivery centres.",
            "client_experience": "Delivered ERP for three mid-size clients.",
            "client_references": [
                {"name": "A Client", "organization": "Client One", "contact": "a@client.example"},
                {"name": "B Client", "organization": "Client Two", "contact": "+14155550123"},
            ],
            **o,
        },
    )


def strategic(**o: Any) -> dict[str, Any]:
    return _merge(
        submitter(),
        {
            "designation": "CEO",
            "discussion_type": "merger",
            "business_overview": "Mid-size delivery company.",
            "confidential_summary": "TOP-SECRET-MARKER we are exploring a merger.",
            "authorized_representative": True,
            **o,
        },
    )
