import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentMethod(str, enum.Enum):
    BKASH = "bkash"
    BANK_TRANSFER = "bank_transfer"
    IN_PERSON = "in_person"


def _enum(py_enum: type[enum.Enum], name: str) -> Enum:
    """Store the enum's lowercase *values* as text, guarded by a CHECK constraint."""
    return Enum(
        py_enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=20,
        values_callable=lambda e: [member.value for member in e],
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"), default=Role.MEMBER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    # Soft delete: a removed member keeps their row so payment history is preserved.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="user", foreign_keys="Payment.user_id"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role.value}>"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # whole BDT, frozen at submission
    payment_method: Mapped[PaymentMethod] = mapped_column(
        _enum(PaymentMethod, "payment_method"), nullable=False
    )
    status: Mapped[PaymentStatus] = mapped_column(
        _enum(PaymentStatus, "payment_status"), default=PaymentStatus.PENDING, nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship(back_populates="payments", foreign_keys=[user_id])
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by])

    __table_args__ = (
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_payments_month"),
        CheckConstraint("year BETWEEN 2000 AND 2100", name="ck_payments_year"),
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        # One active (pending or approved) payment per member per month/year.
        # Rejected rows are excluded, so a member can resubmit after a rejection.
        Index(
            "uq_payments_one_active_per_member_month",
            "user_id",
            "month",
            "year",
            unique=True,
            sqlite_where=text("status IN ('pending', 'approved')"),
        ),
        Index("ix_payments_year_month", "year", "month"),
        Index("ix_payments_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} user={self.user_id} "
            f"{self.month}/{self.year} {self.status.value}>"
        )


class FundSettings(Base):
    """Single-row table (id is always 1) holding the monthly contribution amount."""

    __tablename__ = "fund_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    monthly_contribution_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_fund_settings_single_row"),
        CheckConstraint("monthly_contribution_amount > 0", name="ck_fund_settings_amount_positive"),
    )
