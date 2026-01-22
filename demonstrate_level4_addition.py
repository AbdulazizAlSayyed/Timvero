"""
Demonstration of adding level 4 categories correctly
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
    
    print("=== How to Add Level 4 Categories Successfully ===")
    
    # Login
    try:
        api.login("admin", "admin123")
        print("✅ Login successful")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        exit(1)
    
    # Get all categories organized by company and level
    print("\n1. Analyzing current category structure...")
    try:
        categories = api.categories_tree_flat()
        
        # Organize by company and level
        company_structure = {}
        for cat in categories:
            company_id = cat['company_id']
            level = cat.get('level', 1)
            
            if company_id not in company_structure:
                company_structure[company_id] = {}
            if level not in company_structure[company_id]:
                company_structure[company_id][level] = []
                
            company_structure[company_id][level].append(cat)
        
        # Get company names
        companies = api.companies_list()
        company_names = {c['id']: c['name'] for c in companies}
        
        print("\nCurrent structure by company:")
        for company_id, levels in company_structure.items():
            company_name = company_names.get(company_id, f"Company {company_id}")
            print(f"\n{company_name} (ID: {company_id}):")
            
            for level in sorted(levels.keys()):
                count = len(levels[level])
                print(f"  Level {level}: {count} categories")
                if level <= 3:  # Show sample categories for lower levels
                    for cat in levels[level][:3]:  # Show first 3
                        parent_info = f" (Parent: {cat.get('parent_id')})" if cat.get('parent_id') else " (Root)"
                        print(f"    - {cat['name']}{parent_info}")
                    if len(levels[level]) > 3:
                        print(f"    ... and {len(levels[level]) - 3} more")
                        
    except Exception as e:
        print(f"❌ Error analyzing structure: {e}")
        exit(1)
    
    # Demonstrate adding level 4 to ProSteel (which has level 3 parents)
    print("\n2. Demonstrating level 4 addition to ProSteel...")
    
    # Find ProSteel company
    prosteel_id = None
    for company in companies:
        if company['name'] == 'ProSteel':
            prosteel_id = company['id']
            break
    
    if not prosteel_id:
        print("❌ ProSteel company not found")
        exit(1)
        
    print(f"Using ProSteel (ID: {prosteel_id})")
    
    # Find a level 3 category in ProSteel to use as parent
    level3_categories = [
        cat for cat in categories 
        if cat['company_id'] == prosteel_id and cat.get('level') == 3
    ]
    
    if not level3_categories:
        print("❌ No level 3 categories found in ProSteel")
        # Let's create one
        print("Creating a level 3 category first...")
        
        # Find level 2 parent
        level2_categories = [
            cat for cat in categories 
            if cat['company_id'] == prosteel_id and cat.get('level') == 2
        ]
        
        if level2_categories:
            parent_level2 = level2_categories[0]
            print(f"Using level 2 '{parent_level2['name']}' as parent")
            
            timestamp = int(time.time())
            lvl3_code = f"DEMO_LVL3_{timestamp}"
            lvl3_name = f"Demo Level 3 {timestamp}"
            
            try:
                result = api.categories_tree_add(
                    code=lvl3_code,
                    name=lvl3_name,
                    parent_id=parent_level2['id'],
                    company_id=prosteel_id,
                    category_type="section",
                    kind="overhead",
                    budget=0.0,
                    sort_order=0
                )
                print(f"✅ Created level 3 category: {result}")
                
                # Refresh categories list
                categories = api.categories_tree_flat()
                level3_categories = [
                    cat for cat in categories 
                    if cat['company_id'] == prosteel_id and cat.get('level') == 3 and cat['code'] == lvl3_code
                ]
                
            except Exception as e:
                print(f"❌ Failed to create level 3: {e}")
                exit(1)
        else:
            print("❌ No level 2 categories found in ProSteel either")
            exit(1)
    
    if level3_categories:
        parent_level3 = level3_categories[0]
        print(f"Using level 3 '{parent_level3['name']}' (ID: {parent_level3['id']}) as parent")
        
        # Now add level 4 category
        timestamp = int(time.time())
        lvl4_code = f"DEMO_LVL4_{timestamp}"
        lvl4_name = f"Demo Level 4 {timestamp}"
        
        try:
            result = api.categories_tree_add(
                code=lvl4_code,
                name=lvl4_name,
                parent_id=parent_level3['id'],
                company_id=prosteel_id,
                category_type="section",
                kind="overhead",
                budget=0.0,
                sort_order=0
            )
            print(f"✅ SUCCESS! Level 4 category added: {result}")
            print(f"   Category: {lvl4_name}")
            print(f"   Parent: {parent_level3['name']} (Level 3)")
            print(f"   Company: ProSteel")
            print("🎉 Your system can successfully add level 4 categories!")
            
        except Exception as e:
            print(f"❌ Failed to add level 4: {e}")
            print(f"   Error type: {type(e).__name__}")
            if hasattr(e, 'response'):
                try:
                    error_detail = e.response.json()
                    print(f"   Error details: {error_detail}")
                except:
                    print(f"   Response text: {e.response.text}")
    
    # Final instructions
    print("\n=== HOW TO ADD LEVEL 4 CATEGORIES IN YOUR APPLICATION ===")
    print("1. Select 'ProSteel' company (not 'Tempo Glass')")
    print("2. Find a level 3 category to use as parent (like 'Factory A' or 'Factory B')")
    print("3. Right-click on the level 3 category and select 'Add Child'")
    print("4. Enter the new category details")
    print("5. The system will automatically set it as level 4")
    
    print("\nThe issue was that you were likely trying to add level 4 categories")
    print("under Tempo Glass, which only has categories up to level 3.")
    print("ProSteel has the full hierarchy including level 4 and 5 categories.")
    
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback
    traceback.print_exc()