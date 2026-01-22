"""
Test script to verify API connectivity and core functionality
without requiring the full GUI
"""
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Test API connectivity
try:
    from client.services import session, api
    
    # Update API base to our server port
    session.API_BASE = "http://127.0.0.1:8001"
    
    print("Testing API connectivity...")
    
    # Test companies endpoint
    try:
        companies = api.companies_list()
        print(f"✓ Companies endpoint working. Found {len(companies)} companies:")
        for company in companies:
            print(f"  - {company.get('name', 'Unknown')} (ID: {company.get('id')})")
    except Exception as e:
        print(f"✗ Companies endpoint failed: {e}")
    
    # Test categories endpoint
    try:
        categories = api.categories_list()
        print(f"✓ Categories endpoint working. Found {len(categories)} categories")
    except Exception as e:
        print(f"✗ Categories endpoint failed: {e}")
        
    # Test employees endpoint  
    try:
        employees = api.employees_list()
        print(f"✓ Employees endpoint working. Found {len(employees)} employees")
    except Exception as e:
        print(f"✗ Employees endpoint failed: {e}")
        
    print("\nAPI tests completed!")
    
except ImportError as e:
    print(f"Import error: {e}")
    print("This likely means required packages are not installed.")
except Exception as e:
    print(f"Unexpected error: {e}")