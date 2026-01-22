from fastapi import APIRouter, Depends
from app.db import SessionLocal
from app.models import Company
from sqlalchemy.orm import Session

router = APIRouter(prefix="/companies", tags=["Companies"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("")
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).all()


@router.get("/list")
def list_companies_legacy(db: Session = Depends(get_db)):
    return db.query(Company).all()

@router.post("/add")
def add_company(name: str, db: Session = Depends(get_db)):
    if db.query(Company).filter(Company.name == name).first():
        return {"ok": False, "message": "Company already exists."}
    c = Company(name=name)
    db.add(c)
    db.commit()
    return {"ok": True, "message": "Company added."}

@router.delete("/delete/{id}")
def delete_company(id: int, db: Session = Depends(get_db)):
    c = db.query(Company).get(id)
    if not c:
        return {"ok": False, "message": "Company not found."}
    db.delete(c)
    db.commit()
    return {"ok": True}
