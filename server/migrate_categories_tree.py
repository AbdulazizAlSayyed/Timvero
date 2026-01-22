#!/usr/bin/env python3
"""
Comprehensive migration script for tree-based categories and projects
"""
import sqlite3
import os
from datetime import datetime, date

def backup_database(db_path):
    """Create a backup of the current database"""
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if os.path.exists(db_path):
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"Database backed up to: {backup_path}")
    return backup_path

def migrate_to_tree_structure(conn):
    """Migrate existing flat categories to tree structure"""
    cursor = conn.cursor()
    
    # Rename old categories table
    try:
        cursor.execute("ALTER TABLE categories RENAME TO categories_old")
        print("Renamed old categories table")
    except sqlite3.OperationalError:
        print("Old categories table already renamed or doesn't exist")
    
    # Create new categories table with tree structure
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            parent_id INTEGER REFERENCES categories(id),
            company_id INTEGER NOT NULL REFERENCES companies(id),
            category_type TEXT NOT NULL,
            kind TEXT NOT NULL,
            budget REAL DEFAULT 0.0,
            allocated_budget REAL DEFAULT 0.0,
            spent_amount REAL DEFAULT 0.0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create projects table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            status TEXT NOT NULL DEFAULT 'active',
            start_date DATE,
            end_date DATE,
            actual_completion_date DATE,
            budget REAL NOT NULL DEFAULT 0.0,
            allocated_budget REAL DEFAULT 0.0,
            spent_amount REAL DEFAULT 0.0,
            linked_category_ids TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    print("Created new table structures")

def migrate_existing_categories(conn):
    """Migrate existing categories to new tree structure"""
    cursor = conn.cursor()
    
    # Check if old categories exist
    try:
        cursor.execute("SELECT COUNT(*) FROM categories_old")
        old_count = cursor.fetchone()[0]
        print(f"Found {old_count} existing categories to migrate")
    except sqlite3.OperationalError:
        print("No old categories table found")
        return
    
    # Get companies
    cursor.execute("SELECT id, name FROM companies")
    companies = cursor.fetchall()
    
    if not companies:
        print("No companies found, creating default companies...")
        cursor.execute("INSERT INTO companies (name) VALUES ('Tempo Glass')")
        cursor.execute("INSERT INTO companies (name) VALUES ('ProSteel')")
        conn.commit()
        cursor.execute("SELECT id, name FROM companies")
        companies = cursor.fetchall()
    
    tempo_id = next((c[0] for c in companies if c[1] == 'Tempo Glass'), companies[0][0])
    prosteel_id = next((c[0] for c in companies if c[1] == 'ProSteel'), companies[1][0] if len(companies) > 1 else companies[0][0])
    
    # Migrate existing categories
    cursor.execute("SELECT id, name, kind, budget FROM categories_old")
    old_categories = cursor.fetchall()
    
    # Create root categories for each company
    root_categories = []
    
    # Tempo Glass hierarchy: Company → Department → Section
    tempo_root = ('TEMP_DEPT_ROOT', 'Departments', 1, None, tempo_id, 'department', 'overhead', 0.0, 0, 0)
    cursor.execute("INSERT INTO categories (code, name, level, parent_id, company_id, category_type, kind, budget, allocated_budget, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", tempo_root)
    tempo_dept_root_id = cursor.lastrowid
    root_categories.append(('Tempo Departments', tempo_dept_root_id))
    
    # ProSteel hierarchy: Company → Department → Factory
    prosteel_root = ('PRO_DEPT_ROOT', 'Departments', 1, None, prosteel_id, 'department', 'overhead', 0.0, 0, 0)
    cursor.execute("INSERT INTO categories (code, name, level, parent_id, company_id, category_type, kind, budget, allocated_budget, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", prosteel_root)
    prosteel_dept_root_id = cursor.lastrowid
    root_categories.append(('ProSteel Departments', prosteel_dept_root_id))
    
    # Distribute existing categories between companies
    for i, (old_id, name, kind, budget) in enumerate(old_categories):
        company_id = tempo_id if i % 2 == 0 else prosteel_id
        parent_id = tempo_dept_root_id if company_id == tempo_id else prosteel_dept_root_id
        
        # Create category code
        clean_name = ''.join(c for c in name if c.isalnum())[:20].upper()
        code = f"CATEGORY_{old_id:03d}_{clean_name}"
        
        # Determine category type based on kind
        category_type = 'section' if company_id == tempo_id else 'factory'
        
        category_data = (code, name, 2, parent_id, company_id, category_type, kind, 
                        float(budget) if budget else 0.0, 0.0, 0, i)
        
        cursor.execute("""
            INSERT INTO categories 
            (code, name, level, parent_id, company_id, category_type, kind, budget, allocated_budget, spent_amount, sort_order) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, category_data)
    
    print(f"Migrated {len(old_categories)} existing categories")

def create_sample_hierarchies(conn):
    """Create sample hierarchical structures for both companies"""
    cursor = conn.cursor()
    
    # Get companies
    cursor.execute("SELECT id, name FROM companies WHERE name IN ('Tempo Glass', 'ProSteel')")
    companies = cursor.fetchall()
    
    tempo_id = next((c[0] for c in companies if c[1] == 'Tempo Glass'), None)
    prosteel_id = next((c[0] for c in companies if c[1] == 'ProSteel'), None)
    
    if not tempo_id or not prosteel_id:
        print("Required companies not found")
        return
    
    print("Creating sample hierarchies...")
    
    # Tempo Glass: Company → Department → Section
    # Create departments
    tempo_departments = [
        ('TEMP_MGMT', 'Management', 'department', 'overhead'),
        ('TEMP_HR', 'Human Resources', 'department', 'overhead'),
        ('TEMP_FINANCE', 'Finance', 'department', 'overhead'),
        ('TEMP_SALES', 'Sales', 'department', 'overhead'),
        ('TEMP_PRODUCTION', 'Production', 'department', 'stage'),
    ]
    
    tempo_dept_ids = []
    for code, name, cat_type, kind in tempo_departments:
        cursor.execute("""
            INSERT INTO categories (code, name, level, parent_id, company_id, category_type, kind, budget, sort_order)
            VALUES (?, ?, 2, NULL, ?, ?, ?, 0.0, ?)
        """, (code, name, tempo_id, cat_type, kind, len(tempo_dept_ids)))
        tempo_dept_ids.append(cursor.lastrowid)
    
    # Create sections under departments
    tempo_sections = [
        (tempo_dept_ids[0], 'Executive', 'section', 'overhead'),  # Management
        (tempo_dept_ids[0], 'Administration', 'section', 'overhead'),
        (tempo_dept_ids[1], 'Recruitment', 'section', 'overhead'),  # HR
        (tempo_dept_ids[1], 'Training', 'section', 'overhead'),
        (tempo_dept_ids[2], 'Accounting', 'section', 'overhead'),   # Finance
        (tempo_dept_ids[2], 'Payroll', 'section', 'overhead'),
        (tempo_dept_ids[3], 'Marketing', 'section', 'overhead'),    # Sales
        (tempo_dept_ids[3], 'Customer Service', 'section', 'overhead'),
        (tempo_dept_ids[4], 'Cutting', 'section', 'stage'),         # Production
        (tempo_dept_ids[4], 'Drilling', 'section', 'stage'),
        (tempo_dept_ids[4], 'Assembly', 'section', 'stage'),
    ]
    
    for parent_id, name, cat_type, kind in tempo_sections:
        clean_name = ''.join(c for c in name if c.isalnum())[:15].upper()
        code = f"TEMP_SEC_{clean_name}"
        cursor.execute("""
            INSERT INTO categories (code, name, level, parent_id, company_id, category_type, kind, budget, sort_order)
            VALUES (?, ?, 3, ?, ?, ?, ?, 0.0, 0)
        """, (code, name, parent_id, tempo_id, cat_type, kind))
    
    # ProSteel: Company → Department → Factory → Fabrication/Installation → Steel/Aluminum
    # Create departments
    prosteel_departments = [
        ('PRO_MGMT', 'Management', 'department', 'overhead'),
        ('PRO_ENGINEERING', 'Engineering', 'department', 'overhead'),
        ('PRO_PRODUCTION', 'Production', 'department', 'structural'),
        ('PRO_QUALITY', 'Quality Control', 'department', 'overhead'),
    ]
    
    prosteel_dept_ids = []
    for code, name, cat_type, kind in prosteel_departments:
        cursor.execute("""
            INSERT INTO categories (code, name, level, parent_id, company_id, category_type, kind, budget, sort_order)
            VALUES (?, ?, 2, NULL, ?, ?, ?, 0.0, ?)
        """, (code, name, prosteel_id, cat_type, kind, len(prosteel_dept_ids)))
        prosteel_dept_ids.append(cursor.lastrowid)
    
    # Create factories under Production department
    factories = [
        (prosteel_dept_ids[2], 'Factory A', 'factory', 'structural'),  # Production dept
        (prosteel_dept_ids[2], 'Factory B', 'factory', 'structural'),
    ]
    
    factory_ids = []
    for parent_id, name, cat_type, kind in factories:
        clean_name = ''.join(c for c in name if c.isalnum())[:10].upper()
        code = f"PRO_FAC_{clean_name}"
        cursor.execute("""
            INSERT INTO categories (code, name, level, parent_id, company_id, category_type, kind, budget, sort_order)
            VALUES (?, ?, 3, ?, ?, ?, ?, 0.0, ?)
        """, (code, name, parent_id, prosteel_id, cat_type, kind, len(factory_ids)))
        factory_ids.append(cursor.lastrowid)
    
    # Create Fabrication and Installation under each factory
    process_types = ['Fabrication', 'Installation']
    materials = ['Steel', 'Aluminum']
    
    for factory_id in factory_ids:
        for process in process_types:
            process_clean = process.upper()
            process_code = f"PRO_{process_clean}_{factory_id}"
            cursor.execute("""
                INSERT INTO categories (code, name, level, parent_id, company_id, category_type, kind, budget, sort_order)
                VALUES (?, ?, 4, ?, ?, 'process', 'structural', 0.0, ?)
            """, (process_code, process, factory_id, prosteel_id, process_types.index(process)))
            
            process_id = cursor.lastrowid
            
            # Create material categories under fabrication
            if process == 'Fabrication':
                for material in materials:
                    mat_clean = material.upper()
                    mat_code = f"PRO_{mat_clean}_{process_id}"
                    cursor.execute("""
                        INSERT INTO categories (code, name, level, parent_id, company_id, category_type, kind, budget, sort_order)
                        VALUES (?, ?, 5, ?, ?, 'material', 'structural', 0.0, ?)
                    """, (mat_code, material, process_id, prosteel_id, materials.index(material)))

def create_sample_projects(conn):
    """Create sample projects for both companies"""
    cursor = conn.cursor()
    
    # Get companies
    cursor.execute("SELECT id, name FROM companies WHERE name IN ('Tempo Glass', 'ProSteel')")
    companies = cursor.fetchall()
    
    if not companies:
        return
    
    tempo_id = next((c[0] for c in companies if c[1] == 'Tempo Glass'), companies[0][0])
    prosteel_id = next((c[0] for c in companies if c[1] == 'ProSteel'), companies[1][0] if len(companies) > 1 else companies[0][0])
    
    print("Creating sample projects...")
    
    # Sample projects for Tempo Glass
    tempo_projects = [
        ('TEMPO_RES001', 'Residential Building Project', 'Large residential complex construction', tempo_id, 'active', 500000.0),
        ('TEMPO_COM001', 'Commercial Office Tower', 'Corporate office building', tempo_id, 'active', 1200000.0),
        ('TEMPO_IND001', 'Industrial Facility', 'Manufacturing plant construction', tempo_id, 'completed', 800000.0),
    ]
    
    # Sample projects for ProSteel
    prosteel_projects = [
        ('PRO_BRD001', 'Bridge Construction', 'Steel bridge for highway', prosteel_id, 'active', 2500000.0),
        ('PRO_SKY001', 'Skyscraper Framework', 'High-rise building steel structure', prosteel_id, 'active', 3500000.0),
        ('PRO_INF001', 'Infrastructure Project', 'Public infrastructure development', prosteel_id, 'on_hold', 1800000.0),
    ]
    
    all_projects = tempo_projects + prosteel_projects
    
    for code, name, desc, company_id, status, budget in all_projects:
        cursor.execute("""
            INSERT INTO projects 
            (code, name, description, company_id, status, budget, start_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (code, name, desc, company_id, status, budget, date.today(), datetime.now()))

def verify_migration(conn):
    """Verify the migration was successful"""
    cursor = conn.cursor()
    
    print("\n=== Migration Verification ===")
    
    # Check categories
    cursor.execute("SELECT COUNT(*) FROM categories")
    cat_count = cursor.fetchone()[0]
    print(f"Total categories: {cat_count}")
    
    # Check projects
    cursor.execute("SELECT COUNT(*) FROM projects")
    proj_count = cursor.fetchone()[0]
    print(f"Total projects: {proj_count}")
    
    # Show sample hierarchy
    cursor.execute("""
        SELECT c.id, c.code, c.name, c.level, c.category_type, co.name as company
        FROM categories c
        JOIN companies co ON c.company_id = co.id
        WHERE c.level <= 3
        ORDER BY co.name, c.level, c.sort_order
        LIMIT 10
    """)
    sample_cats = cursor.fetchall()
    print("\nSample category hierarchy:")
    for cat in sample_cats:
        print(f"  Level {cat[3]}: {cat[5]} - {cat[2]} ({cat[4]})")
    
    # Show projects
    cursor.execute("""
        SELECT p.code, p.name, p.status, p.budget, co.name as company
        FROM projects p
        JOIN companies co ON p.company_id = co.id
        ORDER BY co.name, p.created_at
    """)
    projects = cursor.fetchall()
    print("\nSample projects:")
    for proj in projects:
        print(f"  {proj[4]} - {proj[1]} ({proj[2]}, ${proj[3]:,.2f})")

def migrate_database():
    db_path = "./tempo_tracker.db"
    
    if not os.path.exists(db_path):
        print("Database file not found. The application will create it automatically.")
        return
    
    print(f"Migrating database: {db_path}")
    
    try:
        # Backup database
        backup_database(db_path)
        
        conn = sqlite3.connect(db_path)
        
        # Perform migration steps
        migrate_to_tree_structure(conn)
        migrate_existing_categories(conn)
        create_sample_hierarchies(conn)
        create_sample_projects(conn)
        
        conn.commit()
        print("Migration completed successfully!")
        
        # Verify results
        verify_migration(conn)
        
    except Exception as e:
        print(f"Migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    migrate_database()