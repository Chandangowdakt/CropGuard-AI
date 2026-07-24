import sys
from datetime import datetime
from typing import Literal

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (OSError, ValueError):
        pass

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field

RoleType = Literal["farmer", "manager", "admin"]


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: RoleType = "farmer"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: RoleType
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class FarmCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    location: str = ""
    crop_type: str = "chrysanthemum"
    area_acres: float = Field(ge=0, default=0)
    description: str = ""
    manager_id: int | None = None


class FarmUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    crop_type: str | None = None
    area_acres: float | None = Field(default=None, ge=0)
    description: str | None = None


class FarmOut(BaseModel):
    id: int
    user_id: int
    manager_id: int | None = None
    name: str
    location: str
    crop_type: str
    area_acres: float
    description: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class FarmStatsOut(BaseModel):
    farm_id: int
    total_detections: int
    problems_found: int
    last_scan: datetime | None
    health_score: float
    class_counts: dict[str, int]


class FarmWeatherOut(BaseModel):
    farm_id: int
    farm_name: str
    latitude: float
    longitude: float
    temperature: float
    humidity: float
    rainfall: float
    windspeed: float
    disease_risk: Literal["LOW", "MEDIUM", "HIGH"]
    updated_at: datetime
    cached: bool | None = None
    note: str | None = None


class DetectionOut(BaseModel):
    id: int
    farm_id: int
    image_path: str
    predicted_class: str
    confidence: float
    timestamp: datetime
    latitude: float | None = None
    longitude: float | None = None
    plant_zone_id: str | None = None
    session_id: int | None = None

    model_config = {"from_attributes": True}


class PredictionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    predicted_class: str = Field(
        validation_alias=AliasChoices("class", "predicted_class"),
        serialization_alias="class",
    )
    confidence: float
    is_problem: bool
    actual_class: str | None = None
    message: str | None = None


class AnalysisPreviewOut(BaseModel):
    prediction: PredictionOut
    message: str
    analyzed_at: datetime


class BatchImagePredictionOut(BaseModel):
    filename: str
    prediction: PredictionOut


class BatchImageErrorOut(BaseModel):
    filename: str
    error: str


class BatchAnalysisOut(BaseModel):
    total_images: int
    success_count: int
    failed_count: int
    class_counts: dict[str, int]
    class_percentages: dict[str, float]
    results: list[BatchImagePredictionOut]
    errors: list[BatchImageErrorOut] = []
    message: str
    analyzed_at: datetime


class BatchSaveOut(BaseModel):
    farm_id: int
    total_images: int
    saved_count: int
    failed_count: int
    alert_count: int
    class_counts: dict[str, int]
    class_percentages: dict[str, float]
    errors: list[BatchImageErrorOut] = []
    message: str
    saved_at: datetime


class LeafAnalysisOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    predicted_class: str = Field(
        validation_alias=AliasChoices("class", "predicted_class"),
        serialization_alias="class",
    )
    confidence: float = 0.0
    is_problem: bool = False
    description: str | None = None
    recommendation: str | None = None
    message: str | None = None


class DetectionResult(BaseModel):
    detection: DetectionOut
    prediction: PredictionOut
    alert_created: bool
    message: str


class ScanFrameOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    predicted_class: str = Field(
        validation_alias=AliasChoices("class", "predicted_class", "class_name"),
        serialization_alias="class",
    )
    confidence: float
    is_problem: bool
    actual_class: str | None = None
    message: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    analyzed_at: datetime | None = None


class ScanFrameAnalyzeOut(BaseModel):
    """Minimal live-frame inference response (no DB writes)."""

    model_config = ConfigDict(populate_by_name=True)

    predicted_class: str = Field(
        validation_alias=AliasChoices("class", "predicted_class", "class_name"),
        serialization_alias="class",
    )
    confidence: float
    is_problem: bool
    actual_class: str | None = None
    smoothed_class: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    plant_zone_id: str | None = None
    analyzed_at: datetime | None = None


class ScanSessionCreate(BaseModel):
    farm_id: int
    started_at: datetime | None = None


class ScanSessionCreateOut(BaseModel):
    session_id: int


class ScanNextZoneOut(BaseModel):
    session_id: int
    plant_zone_id: str | None = None


class ScanBulkDetectionItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    predicted_class: str = Field(
        validation_alias=AliasChoices("class", "predicted_class"),
        serialization_alias="class",
    )
    confidence: float
    timestamp: datetime
    lat: float | None = None
    lon: float | None = None
    image_base64: str | None = None
    plant_zone_id: str | None = None


class ScanBulkDetectionsIn(BaseModel):
    detections: list[ScanBulkDetectionItem]


class ScanBulkDetectionsOut(BaseModel):
    saved_count: int
    flagged_count: int


class ScanSessionSummaryOut(BaseModel):
    session_id: int
    farm_id: int
    manager_id: int
    status: str
    total_scanned: int
    healthy_count: int
    bacterial_count: int = 0
    septoria_count: int = 0
    diseased_count: int = 0
    pest_count: int = 0
    water_stressed_count: int = 0
    flagged_count: int
    started_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class ScanDetectionIn(BaseModel):
    predicted_class: str
    actual_class: str | None = None
    confidence: float
    latitude: float | None = None
    longitude: float | None = None
    timestamp: datetime
    image_base64: str | None = None


class ScanSessionIn(BaseModel):
    farm_id: int
    detections: list[ScanDetectionIn]


class ScanSessionOut(BaseModel):
    message: str
    detections_saved: int
    alerts_created: int
    farm_id: int


class FarmSummaryOut(BaseModel):
    farm_id: int
    total_detections: int
    class_counts: dict[str, int]


class ReportDetectionOut(BaseModel):
    id: int
    farm_id: int
    predicted_class: str
    confidence: float
    timestamp: datetime
    status: Literal["Resolved", "Active"]

    model_config = {"from_attributes": True}


class FarmReportSummary(BaseModel):
    farm_id: int
    farm_name: str
    crop_type: str
    location: str
    period_from: str
    period_to: str
    generated_at: datetime
    total_detections: int
    health_score: float
    class_counts: dict[str, int]
    class_percentages: dict[str, float]


class FarmReportOut(BaseModel):
    summary: FarmReportSummary
    detections: list[ReportDetectionOut]
    recommendations: str


class AlertStatsOut(BaseModel):
    date: str
    total_today: int
    unread: int
    total_week: int
    class_counts: dict[str, int]


class UnreadCountOut(BaseModel):
    count: int


class AlertOut(BaseModel):
    id: int
    farm_id: int
    detection_id: int | None
    class_name: str
    confidence: float
    flagged_image_path: str
    timestamp: datetime
    is_read: bool

    model_config = {"from_attributes": True}


class AlertMarkRead(BaseModel):
    is_read: bool = True


class StatsOut(BaseModel):
    total_farms: int
    total_detections: int
    total_alerts: int
    unread_alerts: int
    class_counts: dict[str, int]


class DailyTrendOut(BaseModel):
    date: str
    healthy: int
    bacterial: int
    septoria: int
    diseased: int = 0
    pest_affected: int = 0
    water_stressed: int = 0
    total: int


class AdminStatsOut(BaseModel):
    total_farms: int
    total_users: int
    total_detections: int
    detections_today: int
    most_common_problem: str | None
    platform_health_score: float
    daily_trends: list[DailyTrendOut]
    most_active_farm: str | None
    most_common_disease_today: str | None


class AdminFarmOut(BaseModel):
    id: int
    name: str
    owner_name: str
    owner_email: str
    crop_type: str
    location: str
    last_scan: datetime | None
    health_score: float
    health_status: Literal["healthy", "warning", "critical"]


class AdminUserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: RoleType
    farms_count: int
    created_at: datetime
    status: str = "Active"


class ActivityFeedItem(BaseModel):
    id: int
    farm_id: int
    farm_name: str
    predicted_class: str
    confidence: float
    timestamp: datetime
    message: str


class RoleChangeRequest(BaseModel):
    role: Literal["farmer", "manager"]


class AdminScanSessionOut(BaseModel):
    session_id: int
    farm_id: int
    farm_name: str
    manager_id: int
    manager_name: str
    started_at: datetime
    completed_at: datetime | None
    total_scanned: int
    issues_found: int
    status: str


class AdminFlaggedDetectionOut(BaseModel):
    id: int
    predicted_class: str
    confidence: float
    timestamp: datetime
    latitude: float | None = None
    longitude: float | None = None


class AdminScanSessionDetailOut(AdminScanSessionOut):
    healthy_count: int
    bacterial_count: int = 0
    septoria_count: int = 0
    diseased_count: int = 0
    pest_count: int = 0
    water_stressed_count: int = 0
    flagged_detections: list[AdminFlaggedDetectionOut]


class AdminManagerOverviewOut(BaseModel):
    manager_id: int
    manager_name: str
    assigned_farms: list[str]
    assigned_farm_count: int
    scans_this_week: int
    issues_this_week: int
    last_scan_at: datetime | None


class AdminFarmHealthComparisonOut(BaseModel):
    farm_id: int
    farm_name: str
    health_score: float
    health_status: Literal["healthy", "warning", "critical"]
    trend: Literal["improving", "worsening", "stable"]
    last_manager_name: str | None
    last_scanned_at: datetime | None


class ManagerAssignRequest(BaseModel):
    manager_id: int
    farm_ids: list[int]


class ManagerAssignOut(BaseModel):
    manager_id: int
    assigned_farm_ids: list[int]
    message: str


class ManagerAssignmentsOut(BaseModel):
    manager_id: int
    farm_ids: list[int]


class DailyDigestFarmBreakdown(BaseModel):
    farm_id: int
    farm_name: str
    sessions_count: int
    plants_scanned: int
    issues_found: int
    problem_rate: float


class AdminDailyDigestOut(BaseModel):
    period_start: datetime
    period_end: datetime
    farms_scanned: int
    managers_active: int
    total_sessions: int
    total_plants_checked: int
    total_issues_found: int
    breakdown_by_farm: list[DailyDigestFarmBreakdown]
    top_concerning_farms: list[DailyDigestFarmBreakdown]
    manager_names: list[str] = []


class DailyDigestSendOut(BaseModel):
    digest: AdminDailyDigestOut
    email_sent: bool
    admin_recipients: int
    message: str
