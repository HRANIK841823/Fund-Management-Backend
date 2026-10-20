import re
from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import PaymentMethod, PaymentStatus, Role


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; everything we store is UTC, so say so."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]

USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,50}$")


# ---------- Auth ----------
class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=255, description="Email or username")
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    username: str
    email: str
    role: Role
    is_active: bool
    created_at: UTCDateTime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class MessageOut(BaseModel):
    message: str


# ---------- Members ----------
class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    username: str
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be blank.")
        return v

    @field_validator("username")
    @classmethod
    def _clean_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-50 characters: letters, numbers, dot, dash or underscore."
            )
        return v

    @field_validator("email")
    @classmethod
    def _clean_email(cls, v: str) -> str:
        return v.strip().lower()


class MemberOut(UserOut):
    approved_total: int = 0
    approved_count: int = 0
    pending_count: int = 0


# ---------- Payments ----------
class PaymentCreate(BaseModel):
    # extra="forbid": a request that tries to send `amount` or `status` is rejected outright.
    model_config = ConfigDict(extra="forbid")

    month: int = Field(ge=1, le=12)
    year: int = Field(ge=2000, le=2100)
    payment_method: PaymentMethod


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    month: int
    year: int
    amount: int
    payment_method: PaymentMethod
    status: PaymentStatus
    submitted_at: UTCDateTime
    reviewed_at: UTCDateTime | None = None
    reviewed_by: int | None = None
    rejection_reason: str | None = None


class AdminPaymentOut(PaymentOut):
    member_name: str
    member_username: str
    member_removed: bool = False


class RejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("reason")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


# ---------- Settings ----------
class FundSettingsIn(BaseModel):
    monthly_contribution_amount: int = Field(gt=0, le=10_000_000)


class FundSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    monthly_contribution_amount: int
    updated_at: UTCDateTime
    updated_by: int | None = None


# ---------- Dashboards & reports ----------
class MemberDashboardOut(BaseModel):
    monthly_contribution_amount: int
    total_contributed: int
    fund_balance: int
    year: int
    months_paid: int
    months_pending: int
    months_unpaid: int
    recent_payments: list[PaymentOut]


class MonthStatusRow(BaseModel):
    month: int
    year: int
    status: str  # paid | pending | unpaid
    is_due: bool
    can_submit: bool
    amount: int | None = None
    payment_method: PaymentMethod | None = None
    rejected_count: int = 0
    last_rejection_reason: str | None = None


class MemberMonthlyStatusOut(BaseModel):
    year: int
    monthly_contribution_amount: int
    rows: list[MonthStatusRow]


class MonthlyReportRow(BaseModel):
    user_id: int
    member_name: str
    username: str
    month: int
    year: int
    expected_amount: int
    approved_amount: int
    status: str  # paid | pending | unpaid
    rejected_count: int
    last_rejection_reason: str | None = None


class MonthlyReportSummary(BaseModel):
    paid: int
    pending: int
    unpaid: int
    expected_total: int
    approved_total: int


class MonthlyReportOut(BaseModel):
    month: int
    year: int
    rows: list[MonthlyReportRow]
    summary: MonthlyReportSummary


class AdminDashboardOut(BaseModel):
    month: int
    year: int
    monthly_contribution_amount: int
    total_approved_fund: int
    approved_count: int
    pending_count: int
    rejected_count: int
    total_members: int
    paid_members: int
    pending_members: int
    unpaid_members: int
    expected_total: int
    approved_total_for_month: int
