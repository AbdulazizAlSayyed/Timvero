# app/routes/timesheet_routes.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from ..db import get_db
from ..models import Company, Category, TimeEntry, Project

router = APIRouter(prefix="/timesheet", tags=["timesheet"])


# -------------------------
# Helpers
# -------------------------
def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def _get_or_create_company(db: Session, company_name: str) -> Company:
    company_name = (company_name or "").strip()
    if not company_name or company_name == "All":
        raise ValueError("company must be Tempo Glass or ProSteel (not All)")

    c = db.query(Company).filter(Company.name == company_name).first()
    if not c:
        c = Company(name=company_name)
        db.add(c)
        db.commit()
        db.refresh(c)
    return c


def _sheet_rows(db: Session, employee_id: int, hours_map: dict[tuple, float]) -> list[dict]:
    cats = db.query(Category).order_by(Category.id.asc()).all()
    rows = []
    for c in cats:
        # Add regular category entries
        key = (c.id, None)  # (category_id, project_id)
        rows.append(
            {
                "category_id": c.id,
                "project_id": None,
                "kind": c.kind,
                "name": c.name,
                "hours": float(hours_map.get(key, hours_map.get(c.id, 0.0))),  # fallback to old format
            }
        )
    return rows

def _sheet_rows_with_projects(db: Session, hours_map: dict[tuple, float]) -> list[dict]:
    """
    Build rows ONLY from hours_map keys (which already represents the current sheet filter).
    hours_map keys: (category_id, project_id) -> hours
    """
    if not hours_map:
        return []

    cat_ids = {int(cid) for (cid, _pid) in hours_map.keys()}
    proj_ids = {int(pid) for (_cid, pid) in hours_map.keys() if pid is not None}

    categories = db.query(Category).filter(Category.id.in_(cat_ids)).all()
    cat_name = {c.id: c.name for c in categories}
    cat_kind = {c.id: c.kind for c in categories}

    proj_name = {}
    if proj_ids:
        projects = db.query(Project).filter(Project.id.in_(proj_ids)).all()
        proj_name = {p.id: p.name for p in projects}

    rows = []
    for (cid, pid), h in hours_map.items():
        cid = int(cid)
        pid_int = int(pid) if pid is not None else None

        cname = cat_name.get(cid, f"Category {cid}")
        pname = proj_name.get(pid_int, f"Project {pid_int}") if pid_int is not None else None

        name = f"{cname} -> {pname}" if pname else cname

        rows.append(
            {
                "category_id": cid,
                "project_id": pid_int,
                "kind": cat_kind.get(cid, ""),
                "category_name": cname,
                "project_name": pname,     # ✅ مهم
                "name": name,              # خليه إذا بدك للـ backward compatibility
                "hours": float(h or 0.0),
            }
        )
    # optional sort
    rows.sort(key=lambda x: (x["category_id"], x["project_id"] or 0))
    return rows

# -------------------------
# Schemas
# -------------------------
class EntryIn(BaseModel):
    category_id: int
    project_id: Optional[int] = None
    hours: float = Field(ge=0, le=24)


class DailyUpsertIn(BaseModel):
    employee_id: int
    date: str  # YYYY-MM-DD
    company: Optional[str] = None
    company_id: Optional[int] = None
    entries: List[EntryIn]


class MonthlyUpsertIn(BaseModel):
    employee_id: int
    year: int
    month: int
    company: Optional[str] = None
    company_id: Optional[int] = None
    entries: List[EntryIn]


# -------------------------
# GET daily sheet
# -------------------------
from fastapi import Query, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

@router.get("/daily-sheet")
def get_daily_sheet(
    employee_id: int = Query(...),
    date: str = Query(...),                 # "YYYY-MM-DD"
    company_id: int = Query(...),
    db: Session = Depends(get_db),
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Company not found")

    rows = (
        db.query(
            TimeEntry.category_id,
            TimeEntry.project_id,
            func.sum(TimeEntry.hours).label("h"),
        )
        .filter(
            TimeEntry.employee_id == employee_id,
            TimeEntry.company_id == c.id,
            TimeEntry.date == date,         # ✅ TEXT compare
            TimeEntry.hours != 0,           # ✅ تجاهل zeros
        )
        .group_by(TimeEntry.category_id, TimeEntry.project_id)
        .all()
    )

    hours_map = {(int(cid), pid): float(h or 0.0) for cid, pid, h in rows}
    entries = _sheet_rows_with_projects(db, hours_map)
    total_hours = float(sum(e["hours"] for e in entries))
    return {"employee_id": employee_id, "company_id": c.id, "date": date, "total_hours": total_hours, "entries": entries}

# -------------------------
# POST daily upsert
# -------------------------
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

@router.post("/daily-bulk-upsert")
def daily_bulk_upsert(payload: DailyUpsertIn, db: Session = Depends(get_db)):
    """
    Daily upsert for one employee + one company + one date.
    Rules:
      - DB date is TEXT => store/compare payload.date (YYYY-MM-DD) as string
      - hours == 0 => delete that row (don't keep zeros)
      - remove row from UI => backend deletes rows not included in payload
      - key = (category_id, project_id)
    """

    # 1) Resolve company
    if payload.company_id is not None:
        c = db.query(Company).filter(Company.id == payload.company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found")
    elif getattr(payload, "company", None):
        c = _get_or_create_company(db, payload.company)
    else:
        raise HTTPException(status_code=400, detail="Either company_id or company must be provided")

    # 2) Parse year/month but KEEP date as TEXT string in DB
    dt = _parse_date(payload.date)
    y, m = dt.year, dt.month
    date_str = payload.date  # ✅ TEXT in sqlite schema

    # 3) Load existing rows for that exact day
    existing = (
        db.query(TimeEntry)
        .filter(
            TimeEntry.employee_id == payload.employee_id,
            TimeEntry.company_id == c.id,
            TimeEntry.date == date_str,
        )
        .all()
    )

    ex_map = {(e.category_id, getattr(e, "project_id", None)): e for e in existing}

    # 4) Upsert incoming entries
    incoming_keys = set()

    for it in payload.entries:
        cat_id = int(it.category_id)
        proj_id = int(it.project_id) if it.project_id is not None else None
        key = (cat_id, proj_id)
        incoming_keys.add(key)

        h = float(it.hours or 0.0)
        old = ex_map.get(key)

        # ✅ If 0 => delete row
        if h == 0.0:
            if old:
                db.delete(old)
            continue

        if old:
            old.hours = h
            old.year = y
            old.month = m
            old.date = date_str
            old.project_id = proj_id
        else:
            db.add(
                TimeEntry(
                    employee_id=payload.employee_id,
                    company_id=c.id,
                    category_id=cat_id,
                    project_id=proj_id,
                    date=date_str,     # ✅ TEXT
                    hours=h,
                    year=y,
                    month=m,
                )
            )

    # 5) Delete rows that exist in DB but not in payload (user removed row)
    for key, old in ex_map.items():
        if key not in incoming_keys:
            db.delete(old)

    db.commit()
    return {"ok": True}

# -------------------------
# GET monthly sheet
# -------------------------
@router.get("/sheet")
def get_monthly_sheet(
    employee_id: int = Query(...),
    year: int = Query(...),
    month: int = Query(...),
    company: str = Query(None),
    company_id: int = Query(None),
    db: Session = Depends(get_db),
):
    # Handle both company name and company_id
    if company_id is not None:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Company not found")
    elif company:
        c = _get_or_create_company(db, company)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Either company or company_id must be provided")

    # robust filter: either stored year/month OR derive from date
    ym = f"{year:04d}-{month:02d}"
    rows = (
        db.query(
            TimeEntry.category_id,
            TimeEntry.project_id,
            func.sum(TimeEntry.hours).label("h")
        )
        .filter(
            TimeEntry.employee_id == employee_id,
            TimeEntry.company_id == c.id,
            or_(
                and_(TimeEntry.year == year, TimeEntry.month == month),
                and_(TimeEntry.date.isnot(None), func.substr(TimeEntry.date, 1, 7) == ym),
            ),
        )
        .group_by(TimeEntry.category_id, TimeEntry.project_id)
        .all()
    )
    hours_map = {(int(cid), pid): float(h or 0.0) for cid, pid, h in rows}

    entries = _sheet_rows_with_projects(db, hours_map)

    total_hours = float(sum(x["hours"] for x in entries))
    return {"employee_id": employee_id, "company": company, "year": year, "month": month, "total_hours": total_hours, "entries": entries}


# -------------------------
# POST monthly upsert
# -------------------------
@router.post("/bulk-upsert")
def monthly_bulk_upsert(payload: MonthlyUpsertIn, db: Session = Depends(get_db)):
    # Handle both company name and company_id
    if payload.company_id is not None:
        c = db.query(Company).filter(Company.id == payload.company_id).first()
        if not c:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Company not found")
    elif payload.company:
        c = _get_or_create_company(db, payload.company)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Either company or company_id must be provided")

    existing = (
        db.query(TimeEntry)
        .filter(
            TimeEntry.employee_id == payload.employee_id,
            TimeEntry.company_id == c.id,
            TimeEntry.year == payload.year,
            TimeEntry.month == payload.month,
        )
        .all()
    )
    ex_map = {(e.category_id, e.project_id): e for e in existing}

    incoming_keys = set()

    for it in payload.entries:
        key = (it.category_id, it.project_id)
        incoming_keys.add(key)

        existing_entry = ex_map.get(key)

        if float(it.hours) == 0.0:
            if existing_entry:
                db.delete(existing_entry)
            continue

        if existing_entry:
            existing_entry.hours = float(it.hours)
        else:
            db.add(
                TimeEntry(
                    employee_id=payload.employee_id,
                    company_id=c.id,
                    category_id=it.category_id,
                    project_id=it.project_id,
                    hours=float(it.hours),
                    year=payload.year,
                    month=payload.month,
                    date=None,
                )
            )

    for key, old in ex_map.items():
        if key not in incoming_keys:
            db.delete(old)

    db.commit()
    return {"ok": True}
