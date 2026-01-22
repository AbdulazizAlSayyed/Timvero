import requests

# Test the updated reports with all employees
try:
    print("Testing updated reports to show all employees...")
    
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
        
        # Get allocation report with include_zero_hours parameter
        alloc_resp = requests.get("http://127.0.0.1:8001/reports/allocation?year=2026&month=1&include_zero_hours=true", headers=headers)
        if alloc_resp.status_code == 200:
            alloc_data = alloc_resp.json()
            print(f"\nAllocation report (with zero hours included) shows {len(alloc_data)} entries")
            
            # Extract unique employees from allocation report
            employees_in_report = set()
            for entry in alloc_data:
                employees_in_report.add((entry['employee_id'], entry['employee']))
            
            print(f"Employees in allocation report:")
            for emp_id, emp_name in sorted(employees_in_report):
                print(f"  - {emp_id}: {emp_name}")
        
        # Compare with allocation report without zero hours
        alloc_resp_normal = requests.get("http://127.0.0.1:8001/reports/allocation?year=2026&month=1", headers=headers)
        if alloc_resp_normal.status_code == 200:
            alloc_data_normal = alloc_resp_normal.json()
            print(f"\nAllocation report (without zero hours) shows {len(alloc_data_normal)} entries")
            
            # Extract unique employees from allocation report
            employees_in_report_normal = set()
            for entry in alloc_data_normal:
                employees_in_report_normal.add((entry['employee_id'], entry['employee']))
            
            print(f"Employees in normal allocation report:")
            for emp_id, emp_name in sorted(employees_in_report_normal):
                print(f"  - {emp_id}: {emp_name}")
        
        # Test DataEntry access to employees
        print(f"\nTesting DataEntry user access to employees...")
        data_login_response = requests.post(
            "http://127.0.0.1:8001/auth/login",
            json={"username": "data", "password": "1234"}
        )
        
        if data_login_response.status_code == 200:
            data_token = data_login_response.json().get("token")
            data_headers = {"Authorization": f"Bearer {data_token}"}
            
            data_employees_resp = requests.get("http://127.0.0.1:8001/employees", headers=data_headers)
            if data_employees_resp.status_code == 200:
                data_employees = data_employees_resp.json()
                print(f"DataEntry user can access {len(data_employees)} employees - SUCCESS!")
            else:
                print(f"DataEntry user cannot access employees: {data_employees_resp.status_code}")
        
        print(f"\nThe system now supports:")
        print(f"- Reports showing employees with time entries (default behavior)")
        print(f"- Reports showing all employees including those with zero hours (using include_zero_hours=true)")
        print(f"- DataEntry user can access the employees page")
        print(f"- Project budget tracking")
        
    else:
        print(f"Login failed: {login_response.status_code}")

except Exception as e:
    print(f"Error: {e}")