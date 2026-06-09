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


class DetectionOut(BaseModel):
    id: int
    farm_id: int
    image_path: str
    predicted_class: str
    confidence: float
    timestamp: datetime

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


class DetectionResult(BaseModel):
    detection: DetectionOut
    prediction: PredictionOut
    alert_created: bool
    message: str


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
    diseased: int
    pest_affected: int
    water_stressed: int
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
