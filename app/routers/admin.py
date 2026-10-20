from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import delete, func, or_, select

from app.database import get_db
from app.dependencies import require_admin
from app.models import FundSettings, Payment, PaymentStatus, Role, User, utcnow
from app.schemas import (
    AdminDashboardOut,
    AdminPaymentOut,
    FundSettingsIn,
    FundSettingsOut,
    MemberCreate,
    MemberOut,
    MessageOut,
    MonthlyReportOut,
    PaymentOut,
    RejectIn,
)
from app.security import hash_password
from app.services import payments as payment_service
from app.services import reports
from app.services.payments import utc_today

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------- Members ----------
def _member_out(user: User, stats: dict[int, tuple[int, int, int]]) -> MemberOut:
    total, approved, pending = stats.get(user.id, (0, 0, 0))
    out = MemberOut.model_validate(user)
    out.approved_total, out.approved_count, out.pending_count = total, approved, pending
    return out


def _member_stats(db: Session) -> dict[int, tuple[int, int, int]]:
    rows = db.execute(
        select(
            Payment.user_id,
            func.coalesce(func.sum(Payment.amount).filter(Payment.status == PaymentStatus.APPROVED), 0),
            func.count(Payment.id).filter(Payment.status == PaymentStatus.APPROVED),
            func.count(Payment.id).filter(Payment.status == PaymentStatus.PENDING),
        ).group_by(Payment.user_id)
    ).all()
    return {uid: (int(t), int(a), int(p)) for uid, t, a, p in rows}


@router.get("/members", response_model=list[MemberOut])
def list_members(db: Session = Depends(get_db)):
    users = db.scalars(
        select(User).where(User.role == Role.MEMBER, User.deleted_at.is_(None)).order_by(User.name)
    ).all()
    stats = _member_stats(db)
    return [_member_out(u, stats) for u in users]


@router.post("/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(data: MemberCreate, db: Session = Depends(get_db)):
    taken = db.scalar(
        select(User).where(or_(User.username == data.username, User.email == data.email))
    )
    if taken is not None:
        field = "username" if taken.username == data.username else "email"
        raise HTTPException(status.HTTP_409_CONFLICT, f"That {field} is already in use.")

    # The role is fixed here. Nothing in the request can make someone an admin.
    user = User(
        name=data.name,
        username=data.username,
        email=data.email,
        password_hash=hash_password(data.password),
        role=Role.MEMBER,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "That username or email is already in use.")
    db.refresh(user)
    return _member_out(user, {})


@router.delete("/members/{user_id}", response_model=MessageOut)
def delete_member(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Permanently delete a member and all of their payments."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found.")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account.")
    if user.role != Role.MEMBER:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only member accounts can be deleted here.")

    name = user.name
    db.execute(delete(Payment).where(Payment.user_id == user_id))
    db.execute(delete(User).where(User.id == user_id))
    db.commit()
    return MessageOut(message=f"{name} and all their payments were permanently deleted.")


# ---------- Payments ----------
@router.get("/payments", response_model=list[AdminPaymentOut])
def list_payments(
    user_id: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    status_filter: PaymentStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    stmt = select(Payment, User).join(User, User.id == Payment.user_id)
    if user_id is not None:
        stmt = stmt.where(Payment.user_id == user_id)
    if month is not None:
        stmt = stmt.where(Payment.month == month)
    if year is not None:
        stmt = stmt.where(Payment.year == year)
    if status_filter is not None:
        stmt = stmt.where(Payment.status == status_filter)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.name).like(like), func.lower(User.username).like(like)))
    stmt = stmt.order_by(Payment.submitted_at.desc(), Payment.id.desc())

    result = []
    for payment, member in db.execute(stmt).all():
        item = AdminPaymentOut.model_validate(
            {
                **PaymentOut.model_validate(payment).model_dump(),
                "member_name": member.name,
                "member_username": member.username,
                "member_removed": member.deleted_at is not None,
            }
        )
        result.append(item)
    return result


@router.post("/payments/{payment_id}/approve", response_model=PaymentOut)
def approve(payment_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return payment_service.approve_payment(db, payment_id, admin)


@router.post("/payments/{payment_id}/reject", response_model=PaymentOut)
def reject(
    payment_id: int,
    data: RejectIn | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    reason = data.reason if data else None
    return payment_service.reject_payment(db, payment_id, admin, reason)


# ---------- Dashboard & reports ----------
@router.get("/dashboard", response_model=AdminDashboardOut)
def dashboard(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: Session = Depends(get_db),
):
    today = utc_today()
    return reports.admin_dashboard(db, month or today.month, year or today.year)


@router.get("/monthly-report", response_model=MonthlyReportOut)
def monthly_report(
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    db: Session = Depends(get_db),
):
    today = utc_today()
    return reports.monthly_report(db, month or today.month, year or today.year)


# ---------- Settings ----------
@router.get("/fund-settings", response_model=FundSettingsOut)
def get_fund_settings(db: Session = Depends(get_db)):
    return db.get(FundSettings, 1)


@router.put("/fund-settings", response_model=FundSettingsOut)
def update_fund_settings(
    data: FundSettingsIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Only the settings row changes. Existing payments keep the amount they were submitted with.
    fund = db.get(FundSettings, 1)
    fund.monthly_contribution_amount = data.monthly_contribution_amount
    fund.updated_by = admin.id
    fund.updated_at = utcnow()
    db.commit()
    db.refresh(fund)
    return fund
