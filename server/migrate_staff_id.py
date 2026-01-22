#!/usr/bin/env python3
"""
Migration script to add staff_id column to employees table
"""
import sqlite3
import os
from pathlib import Path

def migrate_database():
    # Database path
    db_path = "./tempo_tracker.db"
    
    if not os.path.exists(db_path):
        print("Database file not found. The application will create it automatically.")
        return
    
    print(f"Migrating database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if staff_id column already exists
        cursor.execute("PRAGMA table_info(employees)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'staff_id' in columns:
            print("staff_id column already exists. Migration not needed.")
            conn.close()
            return
        
        print("Adding staff_id column...")
        
        # Add the staff_id column (nullable first)
        cursor.execute("ALTER TABLE employees ADD COLUMN staff_id TEXT")
        
        # Populate existing employees with temporary staff IDs
        cursor.execute("SELECT id FROM employees WHERE staff_id IS NULL")
        employees_without_staff_id = cursor.fetchall()
        
        for emp_id, in employees_without_staff_id:
            # Generate temporary staff ID based on existing ID
            temp_staff_id = f"STAFF{emp_id:04d}"
            cursor.execute("UPDATE employees SET staff_id = ? WHERE id = ?", 
                         (temp_staff_id, emp_id))
            print(f"Assigned temporary staff ID {temp_staff_id} to employee {emp_id}")
        
        # Create unique index on staff_id
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_staff_id ON employees(staff_id)")
        
        conn.commit()
        print("Migration completed successfully!")
        
        # Verify the migration
        cursor.execute("SELECT id, staff_id, name FROM employees")
        results = cursor.fetchall()
        print("\nVerification - Current employees:")
        for emp_id, staff_id, name in results:
            print(f"  ID: {emp_id}, Staff ID: {staff_id}, Name: {name}")
            
    except Exception as e:
        print(f"Migration failed: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    migrate_database()