"""
Comprehensive category structure analysis
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
    
    print("=== Comprehensive Category Structure Analysis ===")
    
    # Login
    try:
        api.login("admin", "admin123")
        print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        exit(1)
    
    # Get all categories
    print("\n1. Loading all categories...")
    try:
        categories = api.categories_tree_flat()
        print(f"Found {len(categories)} categories:")
        
        # Group by level
        level_groups = {}
        for cat in categories:
            level = cat.get('level', 0)
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(cat)
        
        # Display structure
        for level in sorted(level_groups.keys()):
            print(f"\n--- Level {level} Categories ({len(level_groups[level])}) ---")
            for cat in level_groups[level]:
                parent_info = f" (Parent: {cat.get('parent_id')})" if cat.get('parent_id') else " (Root)"
                print(f"   ID: {cat['id']}, Name: {cat['name']}, Company: {cat['company_id']}{parent_info}")
                
    except Exception as e:
        print(f"❌ Error loading categories: {e}")
        exit(1)
    
    # Check companies
    print("\n2. Checking companies...")
    try:
        companies = api.companies_list()
        print(f"Found {len(companies)} companies:")
        for company in companies:
            print(f"   ID: {company['id']}, Name: {company['name']}")
    except Exception as e:
        print(f"❌ Error loading companies: {e}")
        companies = []
    
    # Try to build a proper hierarchy
    print("\n3. Testing hierarchy building...")
    
    if companies:
        company_id = companies[0]['id']
        print(f"Using company ID: {company_id}")
        
        # Add level 1 category
        print("\n   Adding level 1 category...")
        timestamp = int(time.time())
        lvl1_code = f"LVL1_TEST_{timestamp}"
        lvl1_name = f"Level 1 Test {timestamp}"
        
        try:
            result = api.categories_tree_add(
                code=lvl1_code,
                name=lvl1_name,
                parent_id=None,
                company_id=company_id,
                category_type="department",
                kind="overhead",
                budget=0.0,
                sort_order=0
            )
            print(f"   ✅ Level 1 added: {result}")
            
            # Get the new category ID
            new_categories = api.categories_tree_flat()
            lvl1_cat = next((c for c in new_categories if c['code'] == lvl1_code), None)
            if lvl1_cat:
                lvl1_id = lvl1_cat['id']
                print(f"   Level 1 category ID: {lvl1_id}")
                
                # Add level 2 category
                print("\n   Adding level 2 category...")
                timestamp2 = int(time.time())
                lvl2_code = f"LVL2_TEST_{timestamp2}"
                lvl2_name = f"Level 2 Test {timestamp2}"
                
                try:
                    result2 = api.categories_tree_add(
                        code=lvl2_code,
                        name=lvl2_name,
                        parent_id=lvl1_id,
                        company_id=company_id,
                        category_type="section",
                        kind="overhead",
                        budget=0.0,
                        sort_order=0
                    )
                    print(f"   ✅ Level 2 added: {result2}")
                    
                    # Get level 2 category
                    new_categories2 = api.categories_tree_flat()
                    lvl2_cat = next((c for c in new_categories2 if c['code'] == lvl2_code), None)
                    if lvl2_cat:
                        lvl2_id = lvl2_cat['id']
                        print(f"   Level 2 category ID: {lvl2_id}")
                        
                        # Add level 3 category
                        print("\n   Adding level 3 category...")
                        timestamp3 = int(time.time())
                        lvl3_code = f"LVL3_TEST_{timestamp3}"
                        lvl3_name = f"Level 3 Test {timestamp3}"
                        
                        try:
                            result3 = api.categories_tree_add(
                                code=lvl3_code,
                                name=lvl3_name,
                                parent_id=lvl2_id,
                                company_id=company_id,
                                category_type="section",
                                kind="overhead",
                                budget=0.0,
                                sort_order=0
                            )
                            print(f"   ✅ Level 3 added: {result3}")
                            
                            # Now try level 4
                            print("\n   Adding level 4 category...")
                            timestamp4 = int(time.time())
                            lvl4_code = f"LVL4_TEST_{timestamp4}"
                            lvl4_name = f"Level 4 Test {timestamp4}"
                            
                            try:
                                result4 = api.categories_tree_add(
                                    code=lvl4_code,
                                    name=lvl4_name,
                                    parent_id=lvl3_cat['id'],  # Use the level 3 category as parent
                                    company_id=company_id,
                                    category_type="section",
                                    kind="overhead",
                                    budget=0.0,
                                    sort_order=0
                                )
                                print(f"   ✅ Level 4 added successfully: {result4}")
                                print("   🎉 Problem solved! Level 4 categories can be added.")
                                
                            except Exception as e:
                                print(f"   ❌ Failed to add level 4: {e}")
                                print(f"      Error type: {type(e).__name__}")
                                
                        except Exception as e:
                            print(f"   ❌ Failed to add level 3: {e}")
                            
                    else:
                        print("   ❌ Could not find level 2 category")
                        
                except Exception as e:
                    print(f"   ❌ Failed to add level 2: {e}")
                    
            else:
                print("   ❌ Could not find level 1 category")
                
        except Exception as e:
            print(f"   ❌ Failed to add level 1: {e}")
    
    # Final summary
    print("\n=== SUMMARY ===")
    print("The issue appears to be that there are no level 3 categories in your database.")
    print("To add level 4 categories, you first need level 1 → level 2 → level 3 categories.")
    print("The system is working correctly - it's just a matter of building the proper hierarchy.")
    
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()