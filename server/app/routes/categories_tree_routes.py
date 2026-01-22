from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from ..db import get_db
from ..models import Category, Company
from ..deps import require_roles
from ..config import ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY

router = APIRouter(prefix="/categories-tree", tags=["categories-tree"])

# Pydantic models
class CategoryCreate(BaseModel):
    name: str
    code: str
    parent_id: Optional[int] = None
    company_id: int
    category_type: str
    kind: str
    budget: float = 0.0
    sort_order: int = 0
    level: int = 1   # ✅ add this

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    parent_id: Optional[int] = None
    category_type: Optional[str] = None
    kind: Optional[str] = None
    budget: Optional[float] = None
    sort_order: Optional[int] = None

class CategoryMove(BaseModel):
    new_parent_id: Optional[int] = None
    new_sort_order: Optional[int] = None

# Helper functions
def get_category_hierarchy(db: Session, company_id: int = None) -> List[dict]:
    """Get full category hierarchy as nested tree structure"""
    query = db.query(Category)
    if company_id:
        query = query.filter(Category.company_id == company_id)
    
    # Get all categories
    all_categories = query.order_by(Category.level, Category.sort_order, Category.name).all()
    
    # Convert to dictionary for easy lookup
    cat_dict = {cat.id: {
        "id": cat.id,
        "code": cat.code,
        "name": cat.name,
        "level": cat.level,
        "parent_id": cat.parent_id,
        "company_id": cat.company_id,
        "category_type": cat.category_type,
        "kind": cat.kind,
        "budget": cat.budget,
        "allocated_budget": cat.allocated_budget,
        "spent_amount": cat.spent_amount,
        "sort_order": cat.sort_order,
        "created_at": cat.created_at.isoformat() if cat.created_at else None,
        "updated_at": cat.updated_at.isoformat() if cat.updated_at else None,
        "children": []
    } for cat in all_categories}
    
    # Build tree structure
    root_categories = []
    for cat in all_categories:
        cat_data = cat_dict[cat.id]
        if cat.parent_id and cat.parent_id in cat_dict:
            # Add as child to parent
            cat_dict[cat.parent_id]["children"].append(cat_data)
        else:
            # Root level category
            root_categories.append(cat_data)
    
    return root_categories

def validate_category_constraints(db: Session, category_data: CategoryCreate) -> None:
    """Validate category creation constraints"""
    # Check if code already exists
    existing = db.query(Category).filter(Category.code == category_data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category code already exists")
    
    # Validate level constraints
    if category_data.parent_id:
        parent = db.query(Category).filter(Category.id == category_data.parent_id).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Parent category not found")
        
        if parent.level >= 7:
            raise HTTPException(status_code=400, detail="Cannot add children to level 7 categories (maximum depth reached)")
        
        # Set level based on parent
        category_data.level = parent.level + 1
    else:
        # Root level category
        category_data.level = 1
    
    # Validate company exists
    company = db.query(Company).filter(Company.id == category_data.company_id).first()
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")

# API Endpoints

@router.get("/")
def list_categories_tree(
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))
):
    """Get hierarchical category tree structure"""
    return get_category_hierarchy(db, company_id)

@router.get("/flat")
def list_categories_flat(
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))
):
    """Get flat list of categories with parent information"""
    query = db.query(Category)
    if company_id:
        query = query.filter(Category.company_id == company_id)
    
    categories = query.order_by(Category.level, Category.sort_order, Category.name).all()
    
    return [{
        "id": cat.id,
        "code": cat.code,
        "name": cat.name,
        "level": cat.level,
        "parent_id": cat.parent_id,
        "parent_name": cat.parent.name if cat.parent else None,
        "company_id": cat.company_id,
        "company_name": cat.company.name,
        "category_type": cat.category_type,
        "kind": cat.kind,
        "budget": cat.budget,
        "allocated_budget": cat.allocated_budget,
        "spent_amount": cat.spent_amount,
        "sort_order": cat.sort_order
    } for cat in categories]

@router.post("/")
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN))
):
    """Create a new category in the tree structure"""
    # Validate constraints
    validate_category_constraints(db, data)
    
    # Check name uniqueness within same level and parent
    existing_name = db.query(Category).filter(
        Category.name == data.name,
        Category.parent_id == data.parent_id,
        Category.company_id == data.company_id
    ).first()
    
    if existing_name:
        raise HTTPException(status_code=400, detail="Category name already exists at this level")
    
    # Create category
    category = Category(
        name=data.name,
        code=data.code,
        level=data.level,
        parent_id=data.parent_id,
        company_id=data.company_id,
        category_type=data.category_type,
        kind=data.kind,
        budget=data.budget,
        sort_order=data.sort_order
    )
    
    db.add(category)
    db.commit()
    db.refresh(category)
    
    return {"ok": True, "id": category.id, "code": category.code}

@router.get("/{category_id}")
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN, ROLE_DATA_ENTRY))
):
    """Get specific category with full details"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Get children count
    children_count = db.query(Category).filter(Category.parent_id == category_id).count()
    
    # Get path from root to this category
    path = []
    current = category
    while current:
        path.append({
            "id": current.id,
            "name": current.name,
            "level": current.level
        })
        current = current.parent
    
    return {
        "id": category.id,
        "code": category.code,
        "name": category.name,
        "level": category.level,
        "parent_id": category.parent_id,
        "parent_name": category.parent.name if category.parent else None,
        "company_id": category.company_id,
        "company_name": category.company.name,
        "category_type": category.category_type,
        "kind": category.kind,
        "budget": category.budget,
        "allocated_budget": category.allocated_budget,
        "spent_amount": category.spent_amount,
        "sort_order": category.sort_order,
        "children_count": children_count,
        "path": list(reversed(path)),
        "created_at": category.created_at.isoformat() if category.created_at else None,
        "updated_at": category.updated_at.isoformat() if category.updated_at else None
    }

@router.put("/{category_id}")
def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN))
):
    """Update category details"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Update fields if provided
    if data.name is not None:
        # Check name uniqueness within same level and parent
        existing_name = db.query(Category).filter(
            Category.name == data.name,
            Category.parent_id == category.parent_id,
            Category.company_id == category.company_id,
            Category.id != category_id
        ).first()
        
        if existing_name:
            raise HTTPException(status_code=400, detail="Category name already exists at this level")
        category.name = data.name
    
    if data.code is not None:
        # Check code uniqueness
        existing_code = db.query(Category).filter(
            Category.code == data.code,
            Category.id != category_id
        ).first()
        
        if existing_code:
            raise HTTPException(status_code=400, detail="Category code already exists")
        category.code = data.code
    
    if data.category_type is not None:
        category.category_type = data.category_type
    
    if data.kind is not None:
        category.kind = data.kind
    
    if data.budget is not None:
        category.budget = data.budget
    
    if data.sort_order is not None:
        category.sort_order = data.sort_order
    
    db.commit()
    db.refresh(category)
    
    return {"ok": True, "id": category.id}

@router.post("/{category_id}/move")
def move_category(
    category_id: int,
    data: CategoryMove,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN))
):
    """Move category to new parent or change sort order"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Validate new parent
    if data.new_parent_id is not None:
        if data.new_parent_id == category_id:
            raise HTTPException(status_code=400, detail="Cannot move category to itself")
        
        if data.new_parent_id == category.parent_id:
            # No change in parent
            pass
        else:
            new_parent = db.query(Category).filter(Category.id == data.new_parent_id).first()
            if not new_parent:
                raise HTTPException(status_code=400, detail="New parent category not found")
            
            # Check for circular references
            current = new_parent
            while current:
                if current.id == category_id:
                    raise HTTPException(status_code=400, detail="Cannot move category to its own descendant")
                current = current.parent
            
            # Check level constraints
            if new_parent.level >= 7:
                raise HTTPException(status_code=400, detail="Cannot move to level 7 category (maximum depth reached)")
            
            category.parent_id = data.new_parent_id
            category.level = new_parent.level + 1
    
    # Update sort order if provided
    if data.new_sort_order is not None:
        category.sort_order = data.new_sort_order
    
    db.commit()
    db.refresh(category)
    
    return {"ok": True, "id": category.id, "level": category.level}

@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN))
):
    """Delete category and all its descendants"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    # Check if category has children
    children = db.query(Category).filter(Category.parent_id == category_id).all()
    if children:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete category with {len(children)} child categories. Delete children first or use cascade delete."
        )
    
    from ..models import TimeEntry
    
    # Cascade delete associated time entries
    time_entries = db.query(TimeEntry).filter(TimeEntry.category_id == category_id).all()
    for entry in time_entries:
        db.delete(entry)
    
    # Delete the category
    db.delete(category)
    db.commit()
    
    return {"ok": True, "message": "Category deleted successfully"}

@router.delete("/{category_id}/cascade")
def delete_category_cascade(
    category_id: int,
    db: Session = Depends(get_db),
    user = Depends(require_roles(ROLE_HR, ROLE_ADMIN))
):
    """Delete category and recursively delete all descendants"""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    
    def delete_category_recursive(cat_id: int):
        # Get all children
        children = db.query(Category).filter(Category.parent_id == cat_id).all()
        
        # Recursively delete children first
        for child in children:
            delete_category_recursive(child.id)
        
        # Delete time entries for this category
        from ..models import TimeEntry
        time_entries = db.query(TimeEntry).filter(TimeEntry.category_id == cat_id).all()
        for entry in time_entries:
            db.delete(entry)
        
        # Delete the category
        cat_to_delete = db.query(Category).filter(Category.id == cat_id).first()
        if cat_to_delete:
            db.delete(cat_to_delete)
    
    # Start recursive deletion
    delete_category_recursive(category_id)
    db.commit()
    
    return {"ok": True, "message": "Category and all descendants deleted successfully"}