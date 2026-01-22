from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..db import get_db
from ..models import Category
from ..deps import require_roles, get_current_user
from ..config import ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY

router = APIRouter(prefix="/categories", tags=["categories"])


class CategoryIn(BaseModel):
    name: str
    kind: str  # overhead, stage, project_name
    budget: float | None = None  # only used for project_name


@router.get("/")
def list_categories(
    db: Session = Depends(get_db),
    user=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),
):
    q = db.query(Category)

    # ❌ DataEntry must NOT even see project_name
    if user.role == ROLE_DATA_ENTRY:
        q = q.filter(Category.kind != "project_name")

    rows = q.order_by(Category.kind.asc(), Category.name.asc()).all()
    return [{"id": r.id, "name": r.name, "kind": r.kind, "budget": r.budget} for r in rows]


@router.post("/")
def add_category(
    data: CategoryIn,
    db: Session = Depends(get_db),
    user=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),  # ✅ allow DataEntry
):
    name = (data.name or "").strip()
    kind = (data.kind or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    if kind not in ("overhead", "stage", "project_name"):
        raise HTTPException(status_code=400, detail="kind must be overhead|stage|project_name")

    # ❌ DataEntry cannot add project_name
    if user.role == ROLE_DATA_ENTRY and kind == "project_name":
        raise HTTPException(status_code=403, detail="Forbidden")

    # Only allow budget for project_name
    budget = None
    if kind == "project_name":
        budget = float(data.budget) if data.budget is not None else 0.0

    exists = db.query(Category).filter(Category.name == name).first()
    if exists:
        # Only HR/Admin can update budget for project_name
        if kind == "project_name" and data.budget is not None:
            if user.role not in (ROLE_HR, ROLE_ADMIN):
                raise HTTPException(status_code=403, detail="Forbidden")
            exists.budget = budget
            db.commit()
        return {"ok": True, "id": exists.id}

    c = Category(name=name, kind=kind, budget=budget)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"ok": True, "id": c.id}


class UpdateCategoryBudget(BaseModel):
    budget: float


@router.put("/{id}")
def update_category(
    id: int,
    data: CategoryIn,
    db: Session = Depends(get_db),
    user=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),  # ✅ allow DataEntry
):
    category = db.query(Category).filter(Category.id == id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    name = (data.name or "").strip()
    kind = (data.kind or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    if kind not in ("overhead", "stage", "project_name"):
        raise HTTPException(status_code=400, detail="kind must be overhead|stage|project_name")

    # ❌ DataEntry cannot edit project_name
    if user.role == ROLE_DATA_ENTRY and kind == "project_name":
        raise HTTPException(status_code=403, detail="Forbidden")

    # Only allow budget for project_name
    budget = None
    if kind == "project_name":
        budget = float(data.budget) if data.budget is not None else 0.0

    category.name = name
    category.kind = kind
    category.budget = budget
    
    db.commit()
    db.refresh(category)
    return {"ok": True, "id": category.id}


@router.put("/{category_id}/budget")
def update_category_budget(
    category_id: int,
    data: UpdateCategoryBudget,
    db: Session = Depends(get_db),
    _=Depends(require_roles(ROLE_HR, ROLE_ADMIN)),  # ❌ DataEntry cannot touch budgets
):
    row = db.query(Category).filter(Category.id == category_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")

    row.budget = float(data.budget)
    db.commit()
    return {"ok": True, "id": row.id, "budget": row.budget}


@router.delete("/{id}")
def delete_category(
    id: int,
    db: Session = Depends(get_db),
    user=Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY)),  # ✅ allow DataEntry
):
    category = db.query(Category).filter(Category.id == id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # ❌ DataEntry cannot delete project_name
    if user.role == ROLE_DATA_ENTRY and category.kind == "project_name":
        raise HTTPException(status_code=403, detail="Forbidden")

    from ..models import TimeEntry

    # Cascade delete associated time entries
    time_entries = db.query(TimeEntry).filter(TimeEntry.category_id == id).all()
    for entry in time_entries:
        db.delete(entry)

    db.delete(category)
    db.commit()
    return {"ok": True}
