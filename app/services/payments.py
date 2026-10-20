"""Payment business rules: submission, approval/rejection, fund totals."""
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import FundSettings, Payment, PaymentMethod, PaymentStatus, User, utcnow

ACTIVE_STATUSES = (PaymentStatus.PENDING, PaymentStatus.APPROVED)

DUPLICATE_MESSAGE = (
    "You already have a pending or approved payment for this month. "
    "You can submit again only if it is rejected."
)


def get_contribution_amount(db: Session) -> int:
    fund = db.get(FundSettings, 1)
    if fund is None:
        raise HTTPException(500, "Fund settings are missing. Restart the server to re-create them.")
    return fund.monthly_contribution_amount


def fund_balance(db: Session) -> int:
    """Total approved fund = sum of approved payment amounts (never stored manually)."""
    total = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.APPROVED
        )
    )
    return int(total or 0)


def submit_payment(
    db: Session, user: User, month: int, year: int, method: PaymentMethod
) -> Payment:
    """Create a pending payment. The amount always comes from the settings table."""
    existing = db.scalar(
        select(Payment.id).where(
            Payment.user_id == user.id,
            Payment.month == month,
            Payment.year == year,
            Payment.status.in_(ACTIVE_STATUSES),
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_MESSAGE)

    payment = Payment(
        user_id=user.id,
        month=month,
        year=year,
        amount=get_contribution_amount(db),
        payment_method=method,
        status=PaymentStatus.PENDING,
    )
    db.add(payment)
    try:
        db.commit()  # the partial unique index is the final guard against races
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, DUPLICATE_MESSAGE)
    db.refresh(payment)
    return payment


def _review(db: Session, payment_id: int, admin: User, new_status: PaymentStatus,
            reason: str | None = None) -> Payment:
    """Atomically move a payment from pending to approved/rejected.

    The single UPDATE ... WHERE status = 'pending' means two admins clicking at the
    same moment can never both succeed: the second one matches zero rows.
    """
    result = db.execute(
        update(Payment)
        .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING)
        .values(
            status=new_status,
            reviewed_at=utcnow(),
            reviewed_by=admin.id,
            rejection_reason=reason if new_status == PaymentStatus.REJECTED else None,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        db.rollback()
        exists = db.get(Payment, payment_id)
        if exists is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found.")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This payment was already {exists.status.value}. Refresh to see the latest status.",
        )
    db.commit()
    payment = db.get(Payment, payment_id)
    db.refresh(payment)
    return payment


def approve_payment(db: Session, payment_id: int, admin: User) -> Payment:
    return _review(db, payment_id, admin, PaymentStatus.APPROVED)


def reject_payment(db: Session, payment_id: int, admin: User, reason: str | None) -> Payment:
    return _review(db, payment_id, admin, PaymentStatus.REJECTED, reason)


def utc_today() -> datetime:
    return datetime.now(timezone.utc)
