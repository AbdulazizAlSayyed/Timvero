import requests
import json

# Base URL for the API
BASE_URL = "http://127.0.0.1:8000"

def get_auth_token():
    """Get authentication token"""
    login_data = {
        "username": "admin",
        "password": "admin123"  # Using correct default password
    }
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    if response.status_code == 200:
        return response.json()["token"]  # Using correct field name
    else:
        print(f"Login failed: {response.text}")
        return None

def test_endpoint(endpoint, params=None):
    """Test an endpoint and return the response"""
    token = get_auth_token()
    if not token:
        return None
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    url = f"{BASE_URL}{endpoint}"
    response = requests.get(url, headers=headers, params=params)
    
    print(f"\n--- Testing {endpoint} ---")
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response Length: {len(data) if isinstance(data, list) else 'N/A'}")
        print(f"Sample Response: {json.dumps(data[:3] if isinstance(data, list) else data, indent=2)[:500]}...")
    else:
        print(f"Error: {response.text}")
    
    return response

def test_reports():
    """Test all report endpoints"""
    print("Testing Reports...")
    
    # Test allocation report
    test_endpoint("/reports/allocation", {"year": 2026, "month": 1})
    
    # Test by-project report
    test_endpoint("/reports/by-project", {"year": 2026, "month": 1})
    
    # Test by-department report
    test_endpoint("/reports/by-department", {"year": 2026, "month": 1})
    
    # Test by-employee report
    test_endpoint("/reports/by-employee", {"year": 2026, "month": 1})
    
    # Test summary report
    test_endpoint("/reports/summary", {"year": 2026, "month": 1})
    
    # Test project budget report
    test_endpoint("/reports/project-budget", {"year": 2026, "month": 1})

def test_timesheets():
    """Test timesheet endpoints"""
    print("\nTesting Timesheets...")
    
    # Test getting an employee's timesheet
    test_endpoint("/timesheet/sheet", {"employee_id": 1, "year": 2026, "month": 1})
    
    # Test getting daily sheet (we need to provide a date)
    test_endpoint("/timesheet/daily-sheet", {"employee_id": 1, "date": "2026-01-15"})

def test_companies():
    """Test company-related endpoints"""
    print("\nTesting Companies...")
    
    # Test getting companies
    test_endpoint("/companies")

def test_employees():
    """Test employee-related endpoints"""
    print("\nTesting Employees...")
    
    # Test getting employees
    test_endpoint("/employees")

def test_categories():
    """Test category-related endpoints"""
    print("\nTesting Categories...")
    
    # Test getting categories
    test_endpoint("/categories")

def test_company_specific_reports():
    """Test company-specific reports"""
    print("\nTesting Company-Specific Reports...")
    
    # Test company summary report for company 1
    test_endpoint("/reports/company-summary", {"year": 2026, "month": 1, "company_id": 1})
    
    # Test company summary without company_id (should show all companies)
    test_endpoint("/reports/company-summary", {"year": 2026, "month": 1})

def test_company_timesheets():
    """Test company-specific timesheets"""
    print("\nTesting Company-Specific Timesheets...")
    
    # Test company timesheet for company 1
    test_endpoint("/timesheet/company-timesheet", {"company_id": 1, "year": 2026, "month": 1})
    
    # Test company daily timesheet for company 1
    test_endpoint("/timesheet/company-daily-timesheet", {"company_id": 1, "date": "2026-01-15"})

if __name__ == "__main__":
    print("Starting comprehensive tests...")
    
    test_reports()
    test_timesheets()
    test_companies()
    test_employees()
    test_categories()
    test_company_specific_reports()
    test_company_timesheets()
    
    print("\nTesting completed!")