from datetime import date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select

from app.api.deps import BusinessContext, Db, business_context
from app.models import Expense, Invoice


router = APIRouter(prefix="/dashboard", tags=["dashboard"])
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


async def total_sales(db, business_id, start: date, end: date) -> str:
    value = await db.scalar(select(func.coalesce(func.sum(Invoice.total_amount), 0)).where(
        Invoice.business_id == business_id,
        Invoice.invoice_date >= start,
        Invoice.invoice_date <= end,
        Invoice.deleted_at.is_(None),
        Invoice.status == "issued",
    ))
    return str(value or 0)


async def total_expenses(db, business_id, start: date, end: date) -> str:
    value = await db.scalar(select(func.coalesce(func.sum(Expense.amount), 0)).where(
        Expense.business_id == business_id,
        Expense.expense_date >= start,
        Expense.expense_date <= end,
        Expense.deleted_at.is_(None),
    ))
    return str(value or 0)


@router.get("/summary")
async def summary(
    request: Request,
    db: Db,
    context: Annotated[BusinessContext, Depends(business_context)],
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
) -> dict:
    today = datetime.now(LOCAL_TZ).date()
    if (from_date is None) != (to_date is None):
        raise HTTPException(422, "Provide both from and to dates")
    if from_date and to_date:
        if from_date > to_date:
            raise HTTPException(422, "from must be on or before to")
        windows = {"selected": (from_date, to_date)}
    else:
        month_start = today.replace(day=1)
        week_start = today - timedelta(days=today.weekday())
        year_start = today.replace(month=1, day=1)
        windows = {
            "annual": (year_start, today),
            "monthly": (month_start, today),
            "weekly": (week_start, today),
            "daily": (today, today),
        }
    sales: dict[str, dict[str, str]] = {}
    expenses: dict[str, dict[str, str]] = {}
    for label, (start, end) in windows.items():
        sales[label] = {"from": start.isoformat(), "to": end.isoformat(), "amount": await total_sales(db, context.business.id, start, end)}
        expenses[label] = {"from": start.isoformat(), "to": end.isoformat(), "amount": await total_expenses(db, context.business.id, start, end)}
    return {"data": {"timezone": "Asia/Kolkata", "currency": "INR", "sales": sales, "expenses": expenses}, "request_id": getattr(request.state, "request_id", None)}


@router.get("/trends")
async def trends(
    request: Request,
    db: Db,
    context: Annotated[BusinessContext, Depends(business_context)],
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    interval: str = Query("day", pattern="^(day|week|month)$"),
) -> dict:
    if from_date > to_date:
        raise HTTPException(422, "from must be on or before to")
    sales_bucket = func.date_trunc(interval, Invoice.invoice_date).label("period")
    sales_rows = await db.execute(select(sales_bucket, func.sum(Invoice.total_amount)).where(
        Invoice.business_id == context.business.id,
        Invoice.invoice_date.between(from_date, to_date),
        Invoice.deleted_at.is_(None),
        Invoice.status == "issued",
    ).group_by(sales_bucket).order_by(sales_bucket))
    expense_bucket = func.date_trunc(interval, Expense.expense_date).label("period")
    expense_rows = await db.execute(select(expense_bucket, func.sum(Expense.amount)).where(
        Expense.business_id == context.business.id,
        Expense.expense_date.between(from_date, to_date),
        Expense.deleted_at.is_(None),
    ).group_by(expense_bucket).order_by(expense_bucket))
    return {
        "data": {
            "sales": [{"period": period.date().isoformat(), "amount": str(amount)} for period, amount in sales_rows],
            "expenses": [{"period": period.date().isoformat(), "amount": str(amount)} for period, amount in expense_rows],
        },
        "request_id": getattr(request.state, "request_id", None),
    }