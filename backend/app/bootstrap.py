import asyncio
import os

from sqlalchemy import select

from app.db.base import ExpenseType, OrganizationRole
from app.core.identity import normalize_phone
from app.db.session import SessionLocal
from app.models import Business, BusinessSettings, ExpenseCategory, User


async def bootstrap() -> None:
    name = os.environ.get("INITIAL_SUPER_ADMIN_NAME", "Nivedha Super Admin").strip()
    email = os.environ.get("INITIAL_SUPER_ADMIN_EMAIL", "").strip().casefold() or None
    phone_value = os.environ.get("INITIAL_SUPER_ADMIN_PHONE", "").strip()
    phone = normalize_phone(phone_value) if phone_value else None
    business_name = os.environ.get("INITIAL_BUSINESS_NAME", "Chamber Bricks").strip()
    business_slug = os.environ.get("INITIAL_BUSINESS_SLUG", "chamber-bricks").strip()
    if email is None and phone is None:
        raise SystemExit("Set INITIAL_SUPER_ADMIN_EMAIL or INITIAL_SUPER_ADMIN_PHONE")

    async with SessionLocal() as db, db.begin():
        business = await db.scalar(select(Business).where(Business.slug == business_slug).with_for_update())
        if business is None:
            business = Business(name=business_name, slug=business_slug, is_active=True)
            db.add(business)
            await db.flush()

        admin = await db.scalar(
            select(User).where(
                (User.email == email) if email else (User.phone == phone),
            ).with_for_update()
        )
        if admin is None:
            admin = User(name=name, email=email, phone=phone, organization_role=OrganizationRole.SUPER_ADMIN, is_active=True)
            db.add(admin)
            await db.flush()
        else:
            admin.organization_role = OrganizationRole.SUPER_ADMIN
            admin.is_active = True

        company = await db.scalar(select(BusinessSettings).where(BusinessSettings.business_id == business.id))
        if company is None:
            db.add(
                BusinessSettings(
                    business_id=business.id,
                    created_by_id=admin.id,
                    legal_name=business_name,
                    display_name=business_name,
                    timezone="Asia/Kolkata",
                    currency="INR",
                )
            )
        defaults = (
            ("Daily expenses", ExpenseType.DAILY),
            ("Vehicle diesel", ExpenseType.DIESEL),
            ("Labour salary", ExpenseType.SALARY),
            ("Labour advance", ExpenseType.SALARY_ADVANCE),
            ("Miscellaneous", ExpenseType.MISCELLANEOUS),
        )
        for category_name, expense_type in defaults:
            exists = await db.scalar(
                select(ExpenseCategory.id).where(
                    ExpenseCategory.business_id == business.id,
                    ExpenseCategory.name == category_name,
                )
            )
            if exists is None:
                db.add(ExpenseCategory(business_id=business.id, created_by_id=admin.id, name=category_name, expense_type=expense_type, is_active=True))
    print(f"Bootstrap complete for {business_name} ({business_slug})")


if __name__ == "__main__":
    asyncio.run(bootstrap())