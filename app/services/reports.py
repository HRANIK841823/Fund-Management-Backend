"""Read-only summaries: member status by month, admin dashboard, monthly report."""
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Payment, PaymentStatus, Role, User
from app.schemas import (
    AdminDashboardOut,
    MemberMonthlyStatusOut,
    MonthlyReportOut,
    MonthlyReportRow,
    MonthlyReportSummary,
    MonthStatusRow,
)
from app.services.payments import fund_balance, get_contribution_amount, utc_today


def months_due(year: int) -> int:
    """How many months of `year` are due so far (all 12 for past years, 0 for future)."""
    today = utc_today()
    if year < today.year:
        return 12
    if year == today.year:
        return today.month
    return 0


def member_monthly_status(db: Session, user: User, year: int) -> MemberMonthlyStatusOut:
    payments = db.scalars(
        select(Payment).where(Payment.user_id == user.id, Payment.year == year)
        .order_by(Payment.submitted_at)
    ).all()

    by_month: dict[int, list[Payment]] = defaultdict(list)
    for p in payments:
        by_month[p.month].append(p)

    due = months_due(year)
    rows: list[MonthStatusRow] = []
    for month in range(1, 13):
        items = by_month.get(month, [])
        active = next((p for p in items if p.status in (PaymentStatus.APPROVED, PaymentStatus.PENDING)), None)
        rejected = [p for p in items if p.status == PaymentStatus.REJECTED]
        if active is None:
            state = "unpaid"
        else:
            state = "paid" if active.status == PaymentStatus.APPROVED else "pending"
        rows.append(
            MonthStatusRow(
                month=month,
                year=year,
                status=state,
                is_due=month <= due,
                can_submit=active is None,
                amount=active.amount if active else None,
                payment_method=active.payment_method if active else None,
                rejected_count=len(rejected),
                last_rejection_reason=rejected[-1].rejection_reason if rejected else None,
            )
        )
    return MemberMonthlyStatusOut(
        year=year, monthly_contribution_amount=get_contribution_amount(db), rows=rows
    )


def member_dashboard_counts(rows: list[MonthStatusRow]) -> tuple[int, int, int]:
    paid = sum(1 for r in rows if r.status == "paid")
    pending = sum(1 for r in rows if r.status == "pending")
    unpaid_due = sum(1 for r in rows if r.status == "unpaid" and r.is_due)
    return paid, pending, unpaid_due


def monthly_report(db: Session, month: int, year: int) -> MonthlyReportOut:
    contribution = get_contribution_amount(db)

    payments = db.scalars(
        select(Payment).where(Payment.month == month, Payment.year == year)
        .order_by(Payment.submitted_at)
    ).all()
    by_user: dict[int, list[Payment]] = defaultdict(list)
    for p in payments:
        by_user[p.user_id].append(p)

    # Active members, plus any removed member who still has a live payment this month
    # (so the approved total always matches the fund).
    live_user_ids = {
        uid for uid, items in by_user.items()
        if any(p.status in (PaymentStatus.APPROVED, PaymentStatus.PENDING) for p in items)
    }
    members = db.scalars(
        select(User).where(
            User.role == Role.MEMBER,
            (User.deleted_at.is_(None)) | (User.id.in_(live_user_ids)),
        ).order_by(User.name)
    ).all()

    rows: list[MonthlyReportRow] = []
    for m in members:
        items = by_user.get(m.id, [])
        active = next((p for p in items if p.status in (PaymentStatus.APPROVED, PaymentStatus.PENDING)), None)
        rejected = [p for p in items if p.status == PaymentStatus.REJECTED]
        if active is None:
            state, approved_amt, expected = "unpaid", 0, contribution
        elif active.status == PaymentStatus.APPROVED:
            state, approved_amt, expected = "paid", active.amount, active.amount
        else:
            state, approved_amt, expected = "pending", 0, active.amount
        rows.append(
            MonthlyReportRow(
                user_id=m.id,
                member_name=m.name,
                username=m.username,
                month=month,
                year=year,
                expected_amount=expected,
                approved_amount=approved_amt,
                status=state,
                rejected_count=len(rejected),
                last_rejection_reason=rejected[-1].rejection_reason if rejected else None,
            )
        )

    summary = MonthlyReportSummary(
        paid=sum(1 for r in rows if r.status == "paid"),
        pending=sum(1 for r in rows if r.status == "pending"),
        unpaid=sum(1 for r in rows if r.status == "unpaid"),
        expected_total=sum(r.expected_amount for r in rows),
        approved_total=sum(r.approved_amount for r in rows),
    )
    return MonthlyReportOut(month=month, year=year, rows=rows, summary=summary)


def admin_dashboard(db: Session, month: int, year: int) -> AdminDashboardOut:
    def count_status(st: PaymentStatus) -> int:
        return int(db.scalar(select(func.count(Payment.id)).where(Payment.status == st)) or 0)

    report = monthly_report(db, month, year)
    total_members = int(
        db.scalar(
            select(func.count(User.id)).where(User.role == Role.MEMBER, User.deleted_at.is_(None))
        ) or 0
    )
    return AdminDashboardOut(
        month=month,
        year=year,
        monthly_contribution_amount=get_contribution_amount(db),
        total_approved_fund=fund_balance(db),
        approved_count=count_status(PaymentStatus.APPROVED),
        pending_count=count_status(PaymentStatus.PENDING),
        rejected_count=count_status(PaymentStatus.REJECTED),
        total_members=total_members,
        paid_members=report.summary.paid,
        pending_members=report.summary.pending,
        unpaid_members=report.summary.unpaid,
        expected_total=report.summary.expected_total,
        approved_total_for_month=report.summary.approved_total,
    )
