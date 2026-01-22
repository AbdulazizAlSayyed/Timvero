from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..db import get_db
from ..models import Payment, Employee, EmployeeSalary
from ..deps import require_roles
from ..config import ROLE_HR, ROLE_ADMIN

router = APIRouter(prefix="/payments", tags=["payments"])


# =========================================================
# Monthly Payments (existing)
# =========================================================
class UpsertPaymentIn(BaseModel):
    employee_id: int
    year: int
    month: int
    amount: float


def _validate(year: int, month: int):
    if year < 2026:
        raise HTTPException(400, "year must be >= 2026")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month must be 1..12")


@router.get("")
def get_payment(
    employee_id: int,
    year: int,
    month: int,
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN)),
):
    _validate(year, month)
    row = (
        db.query(Payment)
        .filter(
            Payment.employee_id == employee_id,
            Payment.year == year,
            Payment.month == month,
        )
        .first()
    )
    return {"amount": float(row.amount) if row else 0.0}


@router.post("/upsert")
def upsert_payment(
    data: UpsertPaymentIn,
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN)),
):
    _validate(data.year, data.month)
    if data.amount < 0:
        raise HTTPException(400, "amount must be >= 0")

    row = (
        db.query(Payment)
        .filter(
            Payment.employee_id == data.employee_id,
            Payment.year == data.year,
            Payment.month == data.month,
        )
        .first()
    )

    if row:
        row.amount = float(data.amount)
    else:
        db.add(
            Payment(
                employee_id=data.employee_id,
                year=data.year,
                month=data.month,
                amount=float(data.amount),
            )
        )

    db.commit()
    return {"ok": True}


# =========================================================
# NEW: Default Salaries (GET + BULK UPSERT)
# =========================================================
@router.get("/salaries")
def list_salaries(
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN)),
):
    res = (
        db.query(
            Employee.id.label("employee_id"),
            Employee.name.label("employee_name"),
            EmployeeSalary.base_salary.label("salary"),
        )
        .outerjoin(EmployeeSalary, Employee.id == EmployeeSalary.employee_id)
        .all()
    )
    return [
        {
            "employee_id": r.employee_id,
            "employee_name": r.employee_name,
            "salary": r.salary or 0.0,
        }
        for r in res
    ]


@router.post("/salaries/bulk-upsert")
def upsert_salaries(
    payload: list[dict],
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN)),
):
    for item in payload:
        emp_id = item["employee_id"]
        salary = float(item["salary"])
        ex = db.query(EmployeeSalary).filter_by(employee_id=emp_id).first()
        if ex:
            ex.base_salary = salary
        else:
            db.add(EmployeeSalary(employee_id=emp_id, base_salary=salary))
    db.commit()
    return {"ok": True, "message": "Salaries updated"}
