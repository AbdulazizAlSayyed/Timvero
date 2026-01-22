from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..db import get_db
from ..models import Employee, Company
from ..deps import require_roles
from ..config import ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY

router = APIRouter(prefix="/employees", tags=["employees"])


class EmployeeIn(BaseModel):
    staff_id: str
    name: str
    company: str | None = None  # keep optional for old clients


@router.get("/")
def list_employees(
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    rows = db.query(Employee).order_by(Employee.name.asc()).all()
    return [
        {
            "id": r.id,
            "staff_id": r.staff_id,
            "name": r.name,
            "company": {"id": r.company.id, "name": r.company.name} if r.company else None,
        }
        for r in rows
    ]


@router.post("/")
def add_employee(
    data: EmployeeIn,
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    staff_id = (data.staff_id or "").strip()
    name = (data.name or "").strip()

    if not staff_id:
        raise HTTPException(status_code=400, detail="Staff ID required")
    if not name:
        raise HTTPException(status_code=400, detail="Employee name required")

    existing_employee = db.query(Employee).filter(Employee.staff_id == staff_id).first()
    if existing_employee:
        raise HTTPException(status_code=400, detail="Staff ID already exists")

    company_name = (data.company or "").strip()

    company_id = None
    if company_name:
        company = db.query(Company).filter(Company.name == company_name).first()
        if not company:
            company = Company(name=company_name)
            db.add(company)
            db.flush()
        company_id = company.id

    e = Employee(staff_id=staff_id, name=name, company_id=company_id)
    db.add(e)
    db.commit()
    db.refresh(e)
    return {"ok": True, "id": e.id}


@router.put("/{id}")
def update_employee(
    id: int,
    data: EmployeeIn,
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    employee = db.query(Employee).filter(Employee.id == id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    staff_id = (data.staff_id or "").strip()
    name = (data.name or "").strip()

    if not staff_id:
        raise HTTPException(status_code=400, detail="Staff ID required")
    if not name:
        raise HTTPException(status_code=400, detail="Employee name required")

    existing_employee = (
        db.query(Employee)
        .filter(Employee.staff_id == staff_id, Employee.id != id)
        .first()
    )
    if existing_employee:
        raise HTTPException(status_code=400, detail="Staff ID already exists")

    employee.staff_id = staff_id
    employee.name = name

    company_name = (data.company or "").strip()
    company_id = None
    if company_name:
        company = db.query(Company).filter(Company.name == company_name).first()
        if not company:
            company = Company(name=company_name)
            db.add(company)
            db.flush()
        company_id = company.id

    employee.company_id = company_id

    db.commit()
    db.refresh(employee)
    return {"ok": True, "id": employee.id}


@router.delete("/{id}")
def delete_employee(
    id: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    employee = db.query(Employee).filter(Employee.id == id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    from ..models import TimeEntry

    time_entries = db.query(TimeEntry).filter(TimeEntry.employee_id == id).all()
    for entry in time_entries:
        db.delete(entry)

    db.delete(employee)
    db.commit()
    return {"ok": True, "message": "Employee deleted successfully"}
