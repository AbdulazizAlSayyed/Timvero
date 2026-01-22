#!/usr/bin/env python3
"""
Test script to verify Staff ID functionality
"""
import requests

BASE_URL = "http://localhost:8000"

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

def test_staff_id_functionality(token):
    print("=== Testing Staff ID Functionality ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test adding employee with Staff ID
    print("1. Adding employee with Staff ID...")
    employee_data = {
        "staff_id": "EMP001",
        "name": "John Doe",
        "company": ""
    }
    response = requests.post(f"{BASE_URL}/employees", json=employee_data, headers=headers)
    print(f"Add employee response: {response.status_code}")
    if response.status_code == 200:
        emp_id = response.json().get("id")
        print(f"Created employee ID: {emp_id}")
    else:
        print(f"Error: {response.text}")
        return
    
    # Test listing employees (should show Staff ID)
    print("\n2. Listing employees...")
    response = requests.get(f"{BASE_URL}/employees", headers=headers)
    if response.status_code == 200:
        employees = response.json()
        print(f"Found {len(employees)} employees:")
        for emp in employees:
            print(f"  ID: {emp.get('id')}, Staff ID: {emp.get('staff_id')}, Name: {emp.get('name')}")
    
    # Test updating employee with new Staff ID
    print("\n3. Updating employee Staff ID...")
    update_data = {
        "staff_id": "EMP001_NEW",
        "name": "John Doe Updated",
        "company": ""
    }
    response = requests.put(f"{BASE_URL}/employees/{emp_id}", json=update_data, headers=headers)
    print(f"Update employee response: {response.status_code}")
    if response.status_code == 200:
        print("Employee updated successfully")
    else:
        print(f"Error: {response.text}")
    
    # Test duplicate Staff ID (should fail)
    print("\n4. Testing duplicate Staff ID (should fail)...")
    duplicate_data = {
        "staff_id": "EMP001_NEW",  # Same as updated employee
        "name": "Jane Smith",
        "company": ""
    }
    response = requests.post(f"{BASE_URL}/employees", json=duplicate_data, headers=headers)
    print(f"Duplicate Staff ID response: {response.status_code}")
    if response.status_code == 400:
        print("✓ Duplicate Staff ID correctly rejected")
    else:
        print(f"Unexpected response: {response.text}")
    
    # Clean up - delete the test employee
    print("\n5. Cleaning up test employee...")
    response = requests.delete(f"{BASE_URL}/employees/{emp_id}", headers=headers)
    print(f"Delete employee response: {response.status_code}")

if __name__ == "__main__":
    try:
        token = get_auth_token()
        test_staff_id_functionality(token)
        print("\n=== Staff ID tests completed successfully! ===")
    except Exception as e:
        print(f"Test failed: {e}")