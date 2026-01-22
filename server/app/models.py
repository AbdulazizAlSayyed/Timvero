from datetime import datetime, date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Date,
    DateTime,
    UniqueConstraint,
    ForeignKey,
)
from sqlalchemy import Text
from sqlalchemy.orm import relationship
from .db import Base


# =========================================================
# 1) Companies Table
# =========================================================
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    employees = relationship("Employee", back_populates="company")
    categories = relationship("Category", back_populates="company")


# =========================================================
# 2) App Users
# =========================================================
class AppUser(Base):
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False)  # HR, DataEntry, Admin


# =========================================================
# 3) Employee Table (linked to Company)
# =========================================================
class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)

    company = relationship("Company", back_populates="employees")


# =========================================================
# 4) Categories (Tree Structure with up to 7 levels)
# =========================================================
class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), unique=True, nullable=False)  # Unique code for identification
    level = Column(Integer, nullable=False, default=1)  # Tree level (1-7)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    
    # Category type and classification
    category_type = Column(String(50), nullable=False)  # department, section, factory, fabrication, installation, steel, aluminum, etc.
    kind = Column(String(30), nullable=False)  # overhead, stage, structural
    
    # Budget and financial tracking
    budget = Column(Float, nullable=True, default=0.0)
    allocated_budget = Column(Float, nullable=True, default=0.0)
    spent_amount = Column(Float, nullable=True, default=0.0)
    
    # Ordering within same level
    sort_order = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    parent = relationship("Category", remote_side=[id], backref="children")
    company = relationship("Company", back_populates="categories")


# =========================================================
# 5) Projects (Separate from Categories)
# =========================================================
class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)  # Unique project code
    name = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    
    # Company association
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    
    # Project status and lifecycle
    status = Column(String(30), nullable=False, default="active")  # active, completed, cancelled, on_hold
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    actual_completion_date = Column(Date, nullable=True)
    
    # Financial tracking
    budget = Column(Float, nullable=False, default=0.0)
    allocated_budget = Column(Float, nullable=True, default=0.0)
    spent_amount = Column(Float, nullable=True, default=0.0)
    
    # Links to categories (can be linked to departments, factories, sections, etc.)
    linked_category_ids = Column(String, nullable=True)  # Comma-separated category IDs
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    company = relationship("Company")
    time_entries = relationship("TimeEntry", back_populates="project")


# =========================================================
# 6) TimeEntry (Daily + company_id + year/month optional)
# =========================================================

from sqlalchemy import Column, Integer, Float, Text, ForeignKey
from sqlalchemy.orm import relationship

class TimeEntry(Base):
    __tablename__ = "time_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)

    # ✅ ربط مع categories الجديد
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)

    # ✅ date TEXT
    date = Column(Text, nullable=True)

    hours = Column(Float, nullable=False, default=0)
    year = Column(Integer, nullable=True)
    month = Column(Integer, nullable=True)

    employee = relationship("Employee", backref="time_entries")
    company = relationship("Company", backref="time_entries")
    project = relationship("Project", back_populates="time_entries")
    category = relationship("Category")   # ✅ اختياري بس مفيد

# =========================================================
# 6) Payments
# =========================================================
class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("employee_id", "year", "month", name="uq_pay"),)


# =========================================================
# 7) Employee Salary
# =========================================================
class EmployeeSalary(Base):
    __tablename__ = "employee_salaries"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    base_salary = Column(Float, nullable=False, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee")