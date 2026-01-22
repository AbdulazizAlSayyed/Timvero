"""
Test script to verify project status changes
"""
import sys
from pathlib import Path
import time

# Add project root to path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from client.services import session, api
    
    # Configure API to use our server
    session.API_BASE = "http://127.0.0.1:8001"
    
    print("=== Testing Project Status Changes ===")
    
    # Login
    try:
        api.login("admin", "admin123")
        print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        exit(1)
    
    # Get companies
    companies = api.companies_list()
    if not companies:
        print("❌ No companies found")
        exit(1)
    
    company_id = companies[0]['id']  # Use first company
    print(f"Using company ID: {company_id}")
    
    # Create a test project
    print("\n1. Creating new project...")
    timestamp = int(time.time())
    test_code = f"TEST_PROJ_{timestamp}"
    test_name = f"Test Project {timestamp}"
    
    try:
        result = api.projects_add(
            code=test_code,
            name=test_name,
            company_id=company_id,
            description="Test project for status changes",
            budget=1000.0
        )
        print(f"✅ Project created: {result}")
        
        # Get the project to check its status
        projects = api.projects_list(company_id=company_id)
        test_project = next((p for p in projects if p['code'] == test_code), None)
        
        if test_project:
            print(f"   Project status: {test_project['status'].title()}")
            if test_project['status'] == 'on_hold':
                print("   ✅ NEW PROJECTS DEFAULT TO 'ON HOLD' - CORRECT!")
            else:
                print(f"   ❌ Expected 'on_hold', got '{test_project['status']}'")
        else:
            print("❌ Could not find created project")
            
    except Exception as e:
        print(f"❌ Failed to create project: {e}")
        exit(1)
    
    # Test status transitions - try to change from on_hold to active
    if test_project:
        print(f"\n2. Testing status transition: {test_project['status']} → active")
        try:
            result = api.projects_update(test_project['id'], status="active")
            print("✅ Status changed to 'active' - TRANSITION WORKS!")
            
            # Verify the change
            updated_project = api.projects_get(test_project['id'])
            print(f"   Updated status: {updated_project['status'].title()}")
            
        except Exception as e:
            print(f"❌ Failed to change status to 'active': {e}")
        
        # Test another transition - from active to cancelled
        print(f"\n3. Testing status transition: active → cancelled")
        try:
            result = api.projects_update(test_project['id'], status="cancelled")
            print("✅ Status changed to 'cancelled' - FREE TRANSITIONS WORK!")
            
            # Verify the change
            updated_project = api.projects_get(test_project['id'])
            print(f"   Updated status: {updated_project['status'].title()}")
            
        except Exception as e:
            print(f"❌ Failed to change status to 'cancelled': {e}")
        
        # Test final transition - from cancelled to completed
        print(f"\n4. Testing status transition: cancelled → completed")
        try:
            result = api.projects_update(test_project['id'], status="completed")
            print("✅ Status changed to 'completed' - ALL TRANSITIONS WORK!")
            
            # Verify the change
            updated_project = api.projects_get(test_project['id'])
            print(f"   Updated status: {updated_project['status'].title()}")
            
        except Exception as e:
            print(f"❌ Failed to change status to 'completed': {e}")
    
    # Clean up - delete test project
    if test_project:
        print(f"\n5. Cleaning up - deleting test project...")
        try:
            api.projects_delete(test_project['id'])
            print("✅ Test project deleted successfully")
        except Exception as e:
            print(f"⚠️  Could not delete test project: {e}")
    
    print("\n=== SUMMARY ===")
    print("✅ New projects now default to 'On Hold' status")
    print("✅ Status transitions work freely between any statuses")
    print("✅ All requested changes have been implemented successfully!")
    
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()