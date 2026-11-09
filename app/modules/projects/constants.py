import enum


class ProjectCategory(enum.StrEnum):
    # IT (PRD s.7/s.9)
    ERP_IMPLEMENTATION = "erp_implementation"
    WEB_APP_DEVELOPMENT = "web_app_development"
    CUSTOM_SOFTWARE = "custom_software"
    CLOUD_INFRASTRUCTURE = "cloud_infrastructure"
    TESTING_MAINTENANCE = "testing_maintenance"
    # Non-IT
    MEDICAL_CODING_BILLING = "medical_coding_billing"
    HEALTHCARE_SUPPORT = "healthcare_support"
    DATA_ENTRY = "data_entry"
    DOCUMENT_PROCESSING = "document_processing"
    BANKING_KYC = "banking_kyc"
    MORTGAGE_PROCESSING = "mortgage_processing"
    MUTUAL_FUND_OPERATIONS = "mutual_fund_operations"
    BACK_OFFICE = "back_office"


IT_CATEGORIES = frozenset(
    {
        ProjectCategory.ERP_IMPLEMENTATION,
        ProjectCategory.WEB_APP_DEVELOPMENT,
        ProjectCategory.CUSTOM_SOFTWARE,
        ProjectCategory.CLOUD_INFRASTRUCTURE,
        ProjectCategory.TESTING_MAINTENANCE,
    }
)


def category_group(category: ProjectCategory) -> str:
    return "it" if category in IT_CATEGORIES else "non_it"
