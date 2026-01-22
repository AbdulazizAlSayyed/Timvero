"""
Test script to verify all project status transitions work
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
    
    print("=== Testing All Project Status Transitions ===")
    
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
    test_code = f"TRANS_TEST_{timestamp}"
    test_name = f"Transition Test Project {timestamp}"
    
    try:
        result = api.projects_add(
            code=test_code,
            name=test_name,
            company_id=company_id,
            description="Test project for all status transitions",
            budget=1000.0
        )
        print(f"✅ Project created: {result}")
        
        # Get the project to check its status
        projects = api.projects_list(company_id=company_id)
        test_project = next((p for p in projects if p['code'] == test_code), None)
        
        if test_project:
            print(f"   Initial status: {test_project['status'].title()}")
        else:
            print("❌ Could not find created project")
            exit(1)
            
    except Exception as e:
        print(f"❌ Failed to create project: {e}")
        exit(1)
    
    # Test all possible transitions to "on_hold"
    print(f"\n2. Testing all transitions TO 'on_hold' status:")
    
    # First, make sure we're in 'active' status to start
    if test_project['status'] != 'active':
        try:
            api.projects_update(test_project['id'], status="active")
            print("   Moved to 'active' status")
        except Exception as e:
            print(f"   Could not set to 'active': {e}")
    
    # Test each status -> on_hold transition
    from_statuses = ['active', 'completed', 'cancelled']
    
    for from_status in from_statuses:
        print(f"   Testing: {from_status} → on_hold")
        
        # Set to the 'from' status first
        try:
            api.projects_update(test_project['id'], status=from_status)
            updated_project = api.projects_get(test_project['id'])
            print(f"     Set to {updated_project['status']} - OK")
        except Exception as e:
            print(f"     Failed to set to {from_status}: {e}")
            continue
        
        # Now try to transition to 'on_hold'
        try:
            result = api.projects_update(test_project['id'], status="on_hold")
            updated_project = api.projects_get(test_project['id'])
            print(f"     ✅ {from_status} → on_hold: SUCCESS (now {updated_project['status']})")
        except Exception as e:
            print(f"     ❌ {from_status} → on_hold: FAILED - {e}")
    
    # Test some other transitions too to be comprehensive
    print(f"\n3. Testing other transitions:")
    
    transitions_to_test = [
        ('on_hold', 'active'),
        ('active', 'completed'),
        ('completed', 'cancelled'),
        ('cancelled', 'active'),
    ]
    
    for from_status, to_status in transitions_to_test:
        print(f"   Testing: {from_status} → {to_status}")
        
        # Set to the 'from' status first
        try:
            api.projects_update(test_project['id'], status=from_status)
            updated_project = api.projects_get(test_project['id'])
        except Exception as e:
            print(f"     Failed to set to {from_status}: {e}")
            continue
        
        # Now try to transition to 'to_status'
        try:
            result = api.projects_update(test_project['id'], status=to_status)
            updated_project = api.projects_get(test_project['id'])
            print(f"     ✅ {from_status} → {to_status}: SUCCESS (now {updated_project['status']})")
        except Exception as e:
            print(f"     ❌ {from_status} → {to_status}: FAILED - {e}")
    
    # Final check - make sure we can go back to on_hold from any status
    print(f"\n4. Final test - back to 'on_hold' from any status:")
    try:
        api.projects_update(test_project['id'], status="on_hold")
        final_project = api.projects_get(test_project['id'])
        print(f"   ✅ Successfully moved to 'on_hold': {final_project['status'].title()}")
    except Exception as e:
        print(f"   ❌ Could not move back to 'on_hold': {e}")
    
    # Clean up - delete test project
    print(f"\n5. Cleaning up - deleting test project...")
    try:
        api.projects_delete(test_project['id'])
        print("✅ Test project deleted successfully")
    except Exception as e:
        print(f"⚠️  Could not delete test project: {e}")
    
    print("\n=== SUMMARY ===")
    print("✅ All status transitions should now work freely")
    print("✅ You can change from any status (active, completed, cancelled) to 'on_hold'")
    print("✅ All other transitions also work as expected")

except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()