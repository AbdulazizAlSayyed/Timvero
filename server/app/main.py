# server/app/main.py
from fastapi import FastAPI
from sqlalchemy.orm import Session

from .db import Base, engine, SessionLocal
from .models import AppUser, Category, Company
from .auth import hash_password
from .config import ROLE_HR, ROLE_DATA_ENTRY, ROLE_ADMIN

from .routes.auth_routes import router as auth_router
from .routes.employees_routes import router as employees_router
from .routes.timesheet_routes import router as timesheet_router
from .routes.payments_routes import router as payments_router
from .routes.categories_routes import router as categories_router
from .routes.categories_tree_routes import router as categories_tree_router
from .routes.projects_routes import router as projects_router
from .routes.companies_routes import router as companies_router
from .routes.reports_routes import router as reports_router


app = FastAPI(title="Tempo Tracker API")

app.include_router(auth_router)
app.include_router(employees_router)
app.include_router(timesheet_router)
app.include_router(payments_router)
app.include_router(categories_router)
app.include_router(categories_tree_router)
app.include_router(projects_router)
app.include_router(companies_router)
app.include_router(reports_router)


# ---------------------------
# Seed helpers (RUN ONCE)
# ---------------------------
def seed_users(db: Session):
    """Create default users ONCE."""
    def ensure_user(username: str, password: str, role: str):
        u = db.query(AppUser).filter(AppUser.username == username).first()
        if not u:
            db.add(AppUser(username=username, password_hash=hash_password(password), role=role))

    ensure_user("hr", "1234", ROLE_HR)
    ensure_user("data", "1234", ROLE_DATA_ENTRY)
    ensure_user("admin", "admin123", ROLE_ADMIN)
    db.commit()


def seed_categories(db: Session):
    """
    Create default categories ONCE.
    IMPORTANT: This seeds into the FIRST company only (same behavior as your old code).
    If there is no company yet, it will skip (and will NOT try again later).
    """
    company = db.query(Company).first()
    if not company:
        return

    overheads = ["Management", "HR & Administration", "Finance & Accounting",
                 "Procurement", "Sales & Bidding", "IT"]
    stages = ["MFOC", "General", "Cutting", "Drilling", "Grinding",
              "Furnace", "Double", "Lamination", "Auto Clave"]

    def ensure_cat(name: str, kind: str):
        # keep it per-company to avoid duplicates across companies
        c = (
            db.query(Category)
            .filter(Category.company_id == company.id, Category.name == name, Category.kind == kind)
            .first()
        )
        if c:
            return

        import time
        clean_name = "".join(ch for ch in name if ch.isalnum())[:10].upper()
        code = f"DEFAULT_{int(time.time()) % 10000}_{clean_name}"

        db.add(Category(
            name=name,
            code=code,
            level=1,
            company_id=company.id,
            category_type="department",
            kind=kind,
            budget=0.0,
            sort_order=0
        ))

    for n in overheads:
        ensure_cat(n, "overhead")
    for n in stages:
        ensure_cat(n, "stage")

    db.commit()


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # ✅ Users: seed once
        if db.query(AppUser.id).first() is None:
            seed_users(db)

        # ✅ Categories: seed once (ONLY if Category table is empty)
        if db.query(Category.id).first() is None:
            seed_categories(db)

    finally:
        db.close()


@app.get("/health")
def health():
    return {"ok": True}
