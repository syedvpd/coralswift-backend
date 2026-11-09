import enum


class EngagementPathway(enum.StrEnum):
    STRATEGIC_MERGER_INTEGRATION = "strategic_merger_integration"
    DIRECT_PROJECT_ENGAGEMENT = "direct_project_engagement"
    VENDOR_SUBCONTRACTING = "vendor_subcontracting"


# Bands are an ASSUMPTION: the PRD fixes only the 50-person and INR 2 crore thresholds.
# Recorded for human review; never used to approve or reject automatically.
class WorkforceRange(enum.StrEnum):
    UNDER_50 = "under_50"
    FROM_50_TO_100 = "50_to_100"
    FROM_101_TO_250 = "101_to_250"
    OVER_250 = "over_250"


class TurnoverRange(enum.StrEnum):
    UNDER_2_CRORE = "under_inr_2_crore"
    FROM_2_TO_10_CRORE = "inr_2_to_10_crore"
    OVER_10_CRORE = "over_inr_10_crore"


class ServiceCategory(enum.StrEnum):
    ERP = "erp"
    WEB_APPLICATIONS = "web_applications"
    CUSTOM_SOFTWARE = "custom_software"
    CLOUD_INFRASTRUCTURE = "cloud_infrastructure"
    TESTING_MAINTENANCE = "testing_maintenance"
    DIGITAL_TRANSFORMATION = "digital_transformation"
    MEDICAL_CODING_BILLING = "medical_coding_billing"
    HEALTHCARE_SUPPORT = "healthcare_support"
    DATA_ENTRY_DOCUMENT_PROCESSING = "data_entry_document_processing"
    BANKING_KYC_MORTGAGE = "banking_kyc_mortgage"
    MUTUAL_FUND_OPERATIONS = "mutual_fund_operations"
    BACK_OFFICE = "back_office"


class ApplicationStatus(enum.StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"  # reserved for Phase 2 reviewer workflow
