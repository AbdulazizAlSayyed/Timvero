"""
Quick test to verify status transitions are working
"""
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from client.services import session, api
    
    # Configure API to use our server
    session.API_BASE = "http://127.0.0.1:8001"
    
    print("=== Testing Specific Status Transitions ===")
    
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
    
    company_id = companies[0]['id']
    print(f"Using company ID: {company_id}")
    
    # Get a project that is in 'active' status
    projects = api.projects_list(company_id=company_id)
    active_project = next((p for p in projects if p['status'] == 'active'), None)
    
    if active_project:
        print(f"Found active project: {active_project['name']} (ID: {active_project['id']})")
        print(f"Current status: {active_project['status']}")
        
        # Try to change from active to on_hold
        print("Attempting: active → on_hold")
        try:
            result = api.projects_update(active_project['id'], status="on_hold")
            print("✅ SUCCESS: active → on_hold")
            
            # Check the new status
            updated_project = api.projects_get(active_project['id'])
            print(f"   New status: {updated_project['status']}")
            
        except Exception as e:
            print(f"❌ FAILED: active → on_hold - {e}")
    else:
        print("No active projects found to test")
    
    # Get a project that is in 'completed' status
    completed_project = next((p for p in projects if p['status'] == 'completed'), None)
    
    if completed_project:
        print(f"\nFound completed project: {completed_project['name']} (ID: {completed_project['id']})")
        print(f"Current status: {completed_project['status']}")
        
        # Try to change from completed to on_hold
        print("Attempting: completed → on_hold")
        try:
            result = api.projects_update(completed_project['id'], status="on_hold")
            print("✅ SUCCESS: completed → on_hold")
            
            # Check the new status
            updated_project = api.projects_get(completed_project['id'])
            print(f"   New status: {updated_project['status']}")
            
        except Exception as e:
            print(f"❌ FAILED: completed → on_hold - {e}")
    else:
        print("No completed projects found to test")
    
    # Get a project that is in 'cancelled' status
    cancelled_project = next((p for p in projects if p['status'] == 'cancelled'), None)
    
    if cancelled_project:
        print(f"\nFound cancelled project: {cancelled_project['name']} (ID: {cancelled_project['id']})")
        print(f"Current status: {cancelled_project['status']}")
        
        # Try to change from cancelled to on_hold
        print("Attempting: cancelled → on_hold")
        try:
            result = api.projects_update(cancelled_project['id'], status="on_hold")
            print("✅ SUCCESS: cancelled → on_hold")
            
            # Check the new status
            updated_project = api.projects_get(cancelled_project['id'])
            print(f"   New status: {updated_project['status']}")
            
        except Exception as e:
            print(f"❌ FAILED: cancelled → on_hold - {e}")
    else:
        print("No cancelled projects found to test")
    
    print("\n=== TEST COMPLETE ===")
    
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()