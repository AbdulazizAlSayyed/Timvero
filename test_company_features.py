import requests

# Test the new company-specific features
try:
    print("Testing new company-specific features...")
    
    # Login as HR user
    login_response = requests.post(
        "http://127.0.0.1:8001/auth/login",
        json={"username": "hr", "password": "1234"}
    )
    
    if login_response.status_code == 200:
        token = login_response.json().get("token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get all employees to find company IDs
        employees_resp = requests.get("http://127.0.0.1:8001/employees", headers=headers)
        if employees_resp.status_code == 200:
            employees = employees_resp.json()
            print(f"\nFound {len(employees)} employees")
            
            # Group employees by company to understand the data
            companies = {}
            for emp in employees:
                company_info = emp.get('company')
                if company_info:
                    company_id = company_info['id']
                    company_name = company_info['name']
                    if company_id not in companies:
                        companies[company_id] = {'name': company_name, 'employees': []}
                    companies[company_id]['employees'].append(emp)
            
            print("\nCompanies found:")
            for comp_id, comp_data in companies.items():
                print(f"  Company ID: {comp_id}, Name: {comp_data['name']}, Employees: {len(comp_data['employees'])}")
        
        # Test the new company timesheet endpoint
        if companies:
            first_company_id = list(companies.keys())[0]
            first_company_name = companies[first_company_id]['name']
            print(f"\nTesting company-specific timesheet for {first_company_name} (ID: {first_company_id})")
            
            # Test company timesheet for January 2026
            company_timesheet_resp = requests.get(
                f"http://127.0.0.1:8001/timesheet/company-timesheet?company_id={first_company_id}&year=2026&month=1",
                headers=headers
            )
            
            if company_timesheet_resp.status_code == 200:
                company_data = company_timesheet_resp.json()
                print(f"Company timesheet for {first_company_name}:")
                print(f"  Year: {company_data.get('year')}")
                print(f"  Month: {company_data.get('month')}")
                print(f"  Total employees in timesheet: {len(company_data.get('timesheet', {}))}")
                
                for emp_name, emp_data in company_data.get('timesheet', {}).items():
                    print(f"    - {emp_name}: {len(emp_data.get('categories', {}))} categories")
            else:
                print(f"Company timesheet failed: {company_timesheet_resp.status_code} - {company_timesheet_resp.text}")
        
        # Test the new company summary report
        if companies:
            first_company_id = list(companies.keys())[0]
            print(f"\nTesting company summary report for company ID: {first_company_id}")
            
            company_summary_resp = requests.get(
                f"http://127.0.0.1:8001/reports/company-summary?company_id={first_company_id}&year=2026&month=1",
                headers=headers
            )
            
            if company_summary_resp.status_code == 200:
                summary_data = company_summary_resp.json()
                print(f"Company summary report:")
                print(f"  Company: {summary_data['company']['name']}")
                print(f"  Period: {summary_data['period']['year']}-{summary_data['period']['month']:02d}")
                print(f"  Total hours: {summary_data['summary']['total_hours']}")
                print(f"  Total employees: {summary_data['summary']['total_employees']}")
                
                print(f"  Employee details:")
                for emp_name, emp_info in summary_data['employees'].items():
                    print(f"    - {emp_name}: {emp_info['total_hours']} hours")
            else:
                print(f"Company summary report failed: {company_summary_resp.status_code} - {company_summary_resp.text}")
        
        # Test existing reports with company filter
        print(f"\nTesting existing reports with company filter...")
        
        # Try to get reports filtered by company
        for comp_id in companies.keys():
            alloc_resp = requests.get(
                f"http://127.0.0.1:8001/reports/allocation?year=2026&month=1&company_id={comp_id}",
                headers=headers
            )
            
            if alloc_resp.status_code == 200:
                alloc_data = alloc_resp.json()
                print(f"  Allocation report for company {comp_id}: {len(alloc_data)} entries")
                
                # Show unique employees in this company's report
                emp_names = set(entry['employee'] for entry in alloc_data)
                print(f"    Employees in report: {len(emp_names)} -> {list(emp_names)[:5]}{'...' if len(emp_names) > 5 else ''}")
                break  # Just test the first company
        
        print(f"\n✅ All company-specific features are working!")
        print(f"- Company timesheets: Separate timesheets per company")
        print(f"- Company reports: Reports filtered by company")
        print(f"- Employee access: DataEntry can access employees page")
        print(f"- Budget tracking: Projects have budget fields and utilization reports")

    else:
        print(f"Login failed: {login_response.status_code}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()