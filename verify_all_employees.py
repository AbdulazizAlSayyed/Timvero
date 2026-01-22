import requests

# Verify that reports return data for all employees
try:
    print("Verifying reports return data for all employees...")
    
    # Login as HR user
    login_response = requests.post(
        "http://127.0.0.1:8001/auth/login",
        json={"username": "hr", "password": "1234"}
    )
    
    if login_response.status_code == 200:
        token = login_response.json().get("token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get all employees first
        employees_resp = requests.get("http://127.0.0.1:8001/employees", headers=headers)
        if employees_resp.status_code == 200:
            employees = employees_resp.json()
            print(f"\nTotal employees in system: {len(employees)}")
            print("All employees:")
            for emp in employees:
                print(f"  - {emp['id']}: {emp['name']} (Company: {emp['company']['name'] if emp['company'] else 'None'})")
        
        # Get allocation report (should show all employees with time entries)
        alloc_resp = requests.get("http://127.0.0.1:8001/reports/allocation?year=2026&month=1", headers=headers)
        if alloc_resp.status_code == 200:
            alloc_data = alloc_resp.json()
            print(f"\nAllocation report shows {len(alloc_data)} entries")
            
            # Extract unique employees from allocation report
            employees_in_report = set()
            for entry in alloc_data:
                employees_in_report.add((entry['employee_id'], entry['employee']))
            
            print(f"Employees with time entries in allocation report:")
            for emp_id, emp_name in sorted(employees_in_report):
                print(f"  - {emp_id}: {emp_name}")
        
        # Get by-employee report (should show all employees with time entries)
        emp_resp = requests.get("http://127.0.0.1:8001/reports/by-employee?year=2026&month=1", headers=headers)
        if emp_resp.status_code == 200:
            emp_data = emp_resp.json()
            print(f"\nBy-employee report shows {len(emp_data)} entries")
            
            # Extract unique employees from by-employee report
            employees_in_emp_report = set()
            for entry in emp_data:
                employees_in_emp_report.add((entry['employee_id'], entry['employee']))
            
            print(f"Employees in by-employee report:")
            for emp_id, emp_name in sorted(employees_in_emp_report):
                print(f"  - {emp_id}: {emp_name}")
        
        print(f"\nNote: Reports show employees that have time entries for the specified period.")
        print(f"If an employee has no time entries for year=2026&month=1, they won't appear in the reports.")
        print(f"To see all employees regardless of time entries, use the GET /employees endpoint.")
        
    else:
        print(f"Login failed: {login_response.status_code}")

except Exception as e:
    print(f"Error: {e}")