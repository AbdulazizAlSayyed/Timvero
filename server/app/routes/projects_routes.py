from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from ..db import get_db
from ..models import Project, Company
from ..deps import require_roles
from ..config import ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY

router = APIRouter(prefix="/projects", tags=["projects"])

# Pydantic models
class ProjectCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    company_id: int
    status: str = "on_hold"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: float = 0.0
    linked_category_ids: Optional[str] = None

class ProjectUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    actual_completion_date: Optional[date] = None
    budget: Optional[float] = None
    allocated_budget: Optional[float] = None
    spent_amount: Optional[float] = None
    linked_category_ids: Optional[str] = None

class ProjectStatusUpdate(BaseModel):
    status: str
    actual_completion_date: Optional[date] = None

# Helper functions
def validate_project_code(db: Session, code: str, project_id: int = None) -> None:
    """Validate that project code is unique"""
    query = db.query(Project).filter(Project.code == code)
    if project_id:
        query = query.filter(Project.id != project_id)
    
    existing = query.first()
    if existing:
        raise HTTPException(status_code=400, detail="Project code already exists")

def validate_status_transition(current_status: str, new_status: str) -> bool:
    """Allow all status transitions (free movement between any statuses)"""
    # Valid statuses are checked separately, so just allow any transition
    valid_statuses = ["active", "completed", "cancelled", "on_hold"]
    return new_status in valid_statuses

# API Endpoints

@router.get("/")
def list_projects(
    company_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))
):
    """List all projects with optional filtering"""
    query = db.query(Project)
    
    if company_id:
        query = query.filter(Project.company_id == company_id)
    
    if status:
        query = query.filter(Project.status == status)
    
    projects = query.order_by(Project.created_at.desc()).all()
    
    return [{
        "id": proj.id,
        "code": proj.code,
        "name": proj.name,
        "description": proj.description,
        "company_id": proj.company_id,
        "company_name": proj.company.name if proj.company else None,
        "status": proj.status,
        "start_date": proj.start_date.isoformat() if proj.start_date else None,
        "end_date": proj.end_date.isoformat() if proj.end_date else None,
        "actual_completion_date": proj.actual_completion_date.isoformat() if proj.actual_completion_date else None,
        "budget": proj.budget,
        "allocated_budget": proj.allocated_budget or 0.0,
        "spent_amount": proj.spent_amount or 0.0,
        "remaining_budget": proj.budget - (proj.spent_amount or 0.0),
        "linked_category_ids": proj.linked_category_ids,
        "created_at": proj.created_at.isoformat() if proj.created_at else None,
        "updated_at": proj.updated_at.isoformat() if proj.updated_at else None
    } for proj in projects]

@router.post("/")
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN))
):
    """Create a new project"""
    # Validate project code uniqueness
    validate_project_code(db, data.code)
    
    # Validate company exists
    company = db.query(Company).filter(Company.id == data.company_id).first()
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")
    
    # Validate status
    valid_statuses = ["active", "completed", "cancelled", "on_hold"]
    if data.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")
    
    # Create project
    project = Project(
        code=data.code,
        name=data.name,
        description=data.description,
        company_id=data.company_id,
        status=data.status,
        start_date=data.start_date,
        end_date=data.end_date,
        budget=data.budget,
        linked_category_ids=data.linked_category_ids
    )
    
    db.add(project)
    db.commit()
    db.refresh(project)
    
    return {"ok": True, "id": project.id, "code": project.code}

@router.get("/{project_id}")
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))
):
    """Get detailed information about a specific project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Calculate financial metrics
    spent = project.spent_amount or 0.0
    allocated = project.allocated_budget or 0.0
    budget = project.budget or 0.0
    remaining = budget - spent
    budget_utilization = (spent / budget * 100) if budget > 0 else 0
    
    return {
        "id": project.id,
        "code": project.code,
        "name": project.name,
        "description": project.description,
        "company_id": project.company_id,
        "company_name": project.company.name if project.company else None,
        "status": project.status,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "actual_completion_date": project.actual_completion_date.isoformat() if project.actual_completion_date else None,
        "budget": budget,
        "allocated_budget": allocated,
        "spent_amount": spent,
        "remaining_budget": remaining,
        "budget_utilization": round(budget_utilization, 2),
        "linked_category_ids": project.linked_category_ids,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None
    }

@router.put("/{project_id}")
def update_project(
    project_id: int,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN))
):
    """Update project details"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Update fields if provided
    if data.code is not None:
        validate_project_code(db, data.code, project_id)
        project.code = data.code
    
    if data.name is not None:
        project.name = data.name
    
    if data.description is not None:
        project.description = data.description
    
    if data.status is not None:
        if not validate_status_transition(project.status, data.status):
            raise HTTPException(status_code=400, detail=f"Invalid status transition from {project.status} to {data.status}")
        project.status = data.status
    
    if data.start_date is not None:
        project.start_date = data.start_date
    
    if data.end_date is not None:
        project.end_date = data.end_date
    
    if data.actual_completion_date is not None:
        project.actual_completion_date = data.actual_completion_date
    
    if data.budget is not None:
        project.budget = data.budget
    
    if data.allocated_budget is not None:
        project.allocated_budget = data.allocated_budget
    
    if data.spent_amount is not None:
        project.spent_amount = data.spent_amount
    
    if data.linked_category_ids is not None:
        project.linked_category_ids = data.linked_category_ids
    
    db.commit()
    db.refresh(project)
    
    return {"ok": True, "id": project.id}

@router.patch("/{project_id}/status")
def update_project_status(
    project_id: int,
    data: ProjectStatusUpdate,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN))
):
    """Update project status with validation"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Validate status transition
    if not validate_status_transition(project.status, data.status):
        raise HTTPException(status_code=400, detail=f"Invalid status transition from {project.status} to {data.status}")
    
    # Update status
    project.status = data.status
    
    # Set completion date if moving to completed status
    if data.status == "completed":
        project.actual_completion_date = data.actual_completion_date or date.today()
    
    db.commit()
    db.refresh(project)
    
    return {
        "ok": True, 
        "id": project.id, 
        "status": project.status,
        "actual_completion_date": project.actual_completion_date.isoformat() if project.actual_completion_date else None
    }

@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN))
):
    """Delete a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # TODO: Check for associated time entries and handle accordingly
    # For now, we'll allow deletion but this should be enhanced
    
    db.delete(project)
    db.commit()
    
    return {"ok": True, "message": "Project deleted successfully"}

@router.get("/company/{company_id}/summary")
def get_company_project_summary(
    company_id: int,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))
):
    """Get project summary statistics for a company"""
    # Validate company exists
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    # Get project counts by status
    status_counts = {}
    total_budget = 0.0
    total_spent = 0.0
    
    projects = db.query(Project).filter(Project.company_id == company_id).all()
    
    for project in projects:
        status_counts[project.status] = status_counts.get(project.status, 0) + 1
        total_budget += project.budget or 0.0
        total_spent += project.spent_amount or 0.0
    
    return {
        "company_id": company_id,
        "company_name": company.name,
        "total_projects": len(projects),
        "projects_by_status": status_counts,
        "total_budget": total_budget,
        "total_spent": total_spent,
        "remaining_budget": total_budget - total_spent,
        "budget_utilization": round((total_spent / total_budget * 100) if total_budget > 0 else 0, 2)
    }

@router.get("/status-options")
def get_status_options():
    """Get available project status options"""
    return {
        "statuses": [
            {"value": "active", "label": "Active", "description": "Project is currently in progress"},
            {"value": "completed", "label": "Completed", "description": "Project has been finished successfully"},
            {"value": "cancelled", "label": "Cancelled", "description": "Project was cancelled"},
            {"value": "on_hold", "label": "On Hold", "description": "Project is temporarily suspended"}
        ],
        "transitions": {
            "active": ["completed", "cancelled", "on_hold"],
            "on_hold": ["active", "completed", "cancelled"],
            "completed": [],
            "cancelled": []
        }
    }