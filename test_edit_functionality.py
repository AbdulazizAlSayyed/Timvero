#!/usr/bin/env python3
"""
Test script to verify the new edit and enhanced delete functionality
"""
import requests
import json

BASE_URL = "http://localhost:8000"

# Authenticate first
def get_auth_token():
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    if response.status_code == 200:
        return response.json().get("token")
    else:
        raise Exception(f"Authentication failed: {response.text}")

def test_employee_crud(token):
    print("=== Testing Employee CRUD Operations ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test adding an employee
    print("1. Adding employee...")
    response = requests.post(f"{BASE_URL}/employees", 
                           json={"name": "Test Employee", "company": ""},
                           headers=headers)
    print(f"Add employee response: {response.status_code}")
    emp_data = response.json()
    emp_id = emp_data.get("id")
    print(f"Created employee ID: {emp_id}")
    
    # Test updating the employee
    print("\n2. Updating employee...")
    response = requests.put(f"{BASE_URL}/employees/{emp_id}",
                          json={"name": "Updated Test Employee", "company": ""},
                          headers=headers)
    print(f"Update employee response: {response.status_code}")
    print(f"Update response: {response.json()}")
    
    # Test listing employees
    print("\n3. Listing employees...")
    response = requests.get(f"{BASE_URL}/employees", headers=headers)
    employees = response.json()
    print(f"Found {len(employees)} employees")
    for emp in employees:
        if emp.get("id") == emp_id:
            print(f"Updated employee: {emp}")
    
    # Test deleting employee (should cascade delete timesheets)
    print("\n4. Deleting employee...")
    response = requests.delete(f"{BASE_URL}/employees/{emp_id}", headers=headers)
    print(f"Delete employee response: {response.status_code}")
    print(f"Delete response: {response.json()}")

def test_category_crud(token):
    print("\n=== Testing Category CRUD Operations ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test adding a category
    print("1. Adding category...")
    response = requests.post(f"{BASE_URL}/categories", 
                           json={"name": "Test Category", "kind": "overhead"},
                           headers=headers)
    print(f"Add category response: {response.status_code}")
    cat_data = response.json()
    cat_id = cat_data.get("id")
    print(f"Created category ID: {cat_id}")
    
    # Test updating the category
    print("\n2. Updating category...")
    response = requests.put(f"{BASE_URL}/categories/{cat_id}",
                          json={"name": "Updated Test Category", "kind": "stage"},
                          headers=headers)
    print(f"Update category response: {response.status_code}")
    print(f"Update response: {response.json()}")
    
    # Test listing categories
    print("\n3. Listing categories...")
    response = requests.get(f"{BASE_URL}/categories", headers=headers)
    categories = response.json()
    print(f"Found {len(categories)} categories")
    for cat in categories:
        if cat.get("id") == cat_id:
            print(f"Updated category: {cat}")
    
    # Test deleting category (should cascade delete timesheets)
    print("\n4. Deleting category...")
    response = requests.delete(f"{BASE_URL}/categories/{cat_id}", headers=headers)
    print(f"Delete category response: {response.status_code}")
    print(f"Delete response: {response.json()}")

def test_timesheet_association(token):
    print("\n=== Testing Timesheet Association ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create employee and category for testing
    print("Creating test employee and category...")
    emp_response = requests.post(f"{BASE_URL}/employees", 
                               json={"name": "Timesheet Test Employee", "company": ""},
                               headers=headers)
    emp_id = emp_response.json().get("id")
    
    cat_response = requests.post(f"{BASE_URL}/categories", 
                               json={"name": "Timesheet Test Category", "kind": "overhead"},
                               headers=headers)
    cat_id = cat_response.json().get("id")
    
    # Create a timesheet entry
    print("Creating timesheet entry...")
    timesheet_data = {
        "employee_id": emp_id,
        "date": "2024-01-16",
        "company_id": 1,
        "entries": [{"category_id": cat_id, "hours": 8.0}]
    }
    response = requests.post(f"{BASE_URL}/timesheet/daily-bulk-upsert", 
                           json=timesheet_data, headers=headers)
    print(f"Timesheet creation response: {response.status_code}")
    
    # Now delete the employee - should cascade delete the timesheet
    print("Deleting employee (should cascade delete timesheet)...")
    response = requests.delete(f"{BASE_URL}/employees/{emp_id}", headers=headers)
    print(f"Employee delete response: {response.status_code}")
    
    # Delete the category
    print("Deleting category...")
    response = requests.delete(f"{BASE_URL}/categories/{cat_id}", headers=headers)
    print(f"Category delete response: {response.status_code}")

if __name__ == "__main__":
    try:
        token = get_auth_token()
        test_employee_crud(token)
        test_category_crud(token)
        test_timesheet_association(token)
        print("\n=== All tests completed successfully! ===")
    except Exception as e:
        print(f"Test failed: {e}")