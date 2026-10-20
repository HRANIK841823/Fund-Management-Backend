from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_member
from app.models import Payment, PaymentStatus, User
from app.schemas import (
    MemberDashboardOut,
    MemberMonthlyStatusOut,
    PaymentCreate,
    PaymentOut,
)
from app.services import payments as payment_service
from app.services import reports
from app.services.payments import utc_today

router = APIRouter(prefix="/api/member", tags=["member"])


@router.get("/dashboard", response_model=MemberDashboardOut)
def dashboard(user: User = Depends(require_member), db: Session = Depends(get_db)):
    year = utc_today().year
    status_view = reports.member_monthly_status(db, user, year)
    paid, pending, unpaid = reports.member_dashboard_counts(status_view.rows)

    total_contributed = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.user_id == user.id, Payment.status == PaymentStatus.APPROVED
        )
    )
    recent = db.scalars(
        select(Payment).where(Payment.user_id == user.id)
        .order_by(Payment.submitted_at.desc(), Payment.id.desc()).limit(5)
    ).all()

    return MemberDashboardOut(
        monthly_contribution_amount=status_view.monthly_contribution_amount,
        total_contributed=int(total_contributed or 0),
        fund_balance=payment_service.fund_balance(db),
        year=year,
        months_paid=paid,
        months_pending=pending,
        months_unpaid=unpaid,
        recent_payments=recent,
    )


@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def submit_payment(
    data: PaymentCreate,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    return payment_service.submit_payment(db, user, data.month, data.year, data.payment_method)


@router.get("/payments", response_model=list[PaymentOut])
def my_payments(user: User = Depends(require_member), db: Session = Depends(get_db)):
    # Always filtered by the authenticated user's id, never by a client-supplied id.
    return db.scalars(
        select(Payment).where(Payment.user_id == user.id)
        .order_by(Payment.year.desc(), Payment.month.desc(), Payment.submitted_at.desc())
    ).all()


@router.get("/monthly-status", response_model=MemberMonthlyStatusOut)
def monthly_status(
    year: int = Query(default_factory=lambda: utc_today().year, ge=2000, le=2100),
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    return reports.member_monthly_status(db, user, year)
