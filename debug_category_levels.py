"""
Debug script to test category level addition
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
    
    print("=== Category Level Addition Debug ===")
    
    # First, let's see what categories exist
    print("\n1. Loading existing categories...")
    try:
        categories = api.categories_tree_flat()
        print(f"Found {len(categories)} categories:")
        for cat in categories:
            print(f"   ID: {cat['id']}, Name: {cat['name']}, Level: {cat['level']}, Parent: {cat.get('parent_id')}, Company: {cat['company_id']}")
    except Exception as e:
        print(f"Error loading categories: {e}")
        categories = []
    
    # Try to login first (needed for authenticated endpoints)
    print("\n2. Attempting login...")
    try:
        login_result = api.login("admin", "admin123")
        print(f"Login successful: {login_result}")
    except Exception as e:
        print(f"Login failed: {e}")
        print("Continuing without authentication...")
    
    # Try to add a level 4 category
    print("\n3. Testing level 4 category addition...")
    
    # Find a level 3 category to use as parent
    level3_categories = [cat for cat in categories if cat.get('level') == 3]
    if level3_categories:
        parent_cat = level3_categories[0]
        print(f"Using level 3 category as parent: {parent_cat['name']} (ID: {parent_cat['id']})")
        
        # Try to add level 4 child
        import time
        timestamp = int(time.time())
        test_code = f"TEST_LVL4_{timestamp}"
        test_name = f"Test Level 4 Category {timestamp}"
        
        try:
            result = api.categories_tree_add(
                code=test_code,
                name=test_name,
                parent_id=parent_cat['id'],
                company_id=parent_cat['company_id'],
                category_type="test",
                kind="overhead",
                budget=0.0,
                sort_order=0
            )
            print(f"✅ Level 4 category added successfully!")
            print(f"   Result: {result}")
            
            # Verify it was added
            new_categories = api.categories_tree_flat()
            new_cat = next((c for c in new_categories if c['code'] == test_code), None)
            if new_cat:
                print(f"   Verified: New category at level {new_cat['level']}")
            else:
                print("   Warning: Could not find newly added category")
                
        except Exception as e:
            print(f"❌ Failed to add level 4 category: {e}")
            print(f"   Error type: {type(e).__name__}")
            
            # Try to get more details about the error
            if hasattr(e, 'response'):
                try:
                    error_detail = e.response.json()
                    print(f"   Error details: {error_detail}")
                except:
                    print(f"   Response text: {e.response.text}")
    else:
        print("No level 3 categories found to use as parents")
        
        # Try to add a level 2 category instead (should work)
        print("\n4. Testing level 2 category addition (control test)...")
        companies = api.companies_list()
        if companies:
            company_id = companies[0]['id']
            timestamp = int(time.time())
            test_code = f"TEST_LVL2_{timestamp}"
            test_name = f"Test Level 2 Category {timestamp}"
            
            try:
                result = api.categories_tree_add(
                    code=test_code,
                    name=test_name,
                    parent_id=None,  # Root level
                    company_id=company_id,
                    category_type="test",
                    kind="overhead",
                    budget=0.0,
                    sort_order=0
                )
                print(f"✅ Level 2 category added successfully!")
                print(f"   Result: {result}")
            except Exception as e:
                print(f"❌ Even level 2 failed: {e}")
        else:
            print("No companies found")
            
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()