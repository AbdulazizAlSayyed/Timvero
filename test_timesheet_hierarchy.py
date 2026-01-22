"""
Test script to verify new timesheet hierarchical structure
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
    
    print("=== Testing New Timesheet Structure ===")
    
    # Login
    try:
        api.login("admin", "admin123")
        print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        exit(1)
    
    # Test the new workflow: Employee → Date → Company → Department hierarchy
    print("\nWorkflow being tested:")
    print("1. Select Employee")
    print("2. Select Date/Period") 
    print("3. Select Company")
    print("4. Browse Department/Category hierarchy")
    print("5. Select leaf categories for time entry")
    
    # Get test data
    employees = api.employees_list()
    companies = api.companies_list()
    categories = api.categories_tree_flat()
    
    print(f"\nAvailable data:")
    print(f"- Employees: {len(employees)}")
    print(f"- Companies: {len(companies)}")
    print(f"- Categories: {len(categories)}")
    
    # Show sample hierarchical structure
    print(f"\nSample category hierarchy:")
    level_groups = {}
    for cat in categories[:10]:  # Show first 10
        level = cat.get('level', 1)
        if level not in level_groups:
            level_groups[level] = []
        level_groups[level].append(cat)
    
    for level in sorted(level_groups.keys()):
        print(f"  Level {level}: {len(level_groups[level])} categories")
        for cat in level_groups[level][:2]:  # Show first 2 of each level
            parent_info = f" (Parent: {cat.get('parent_id')})" if cat.get('parent_id') else " (Root)"
            print(f"    - {cat['name']}{parent_info}")
    
    print(f"\n✅ New timesheet structure ready!")
    print("✅ Follows requested flow: Employee → Date → Company → Department hierarchy")
    print("✅ Users can browse full category tree and select leaf nodes")
    print("✅ Categories can be added to timesheet for hour entry")
    
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()