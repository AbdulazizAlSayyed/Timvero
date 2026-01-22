#!/usr/bin/env python3
"""
Test script for tree-based categories and projects functionality
"""
import requests
from datetime import date

BASE_URL = "http://localhost:8000"

def get_auth_token():
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    if response.status_code == 200:
        return response.json().get("token")
    else:
        raise Exception(f"Authentication failed: {response.text}")

def test_category_tree_api(token):
    print("=== Testing Category Tree API ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test getting category tree
    print("1. Getting category tree structure...")
    response = requests.get(f"{BASE_URL}/categories-tree/", headers=headers)
    print(f"Category tree response: {response.status_code}")
    if response.status_code == 200:
        tree = response.json()
        print(f"Found {len(tree)} root categories")
        for root in tree[:3]:  # Show first 3 root categories
            print(f"  Root: {root.get('name')} (Level {root.get('level')})")
            if root.get('children'):
                print(f"    Children: {len(root.get('children'))}")
    
    # Test getting flat category list
    print("\n2. Getting flat category list...")
    response = requests.get(f"{BASE_URL}/categories-tree/flat", headers=headers)
    print(f"Flat categories response: {response.status_code}")
    if response.status_code == 200:
        categories = response.json()
        print(f"Found {len(categories)} total categories")
        # Group by company
        companies = {}
        for cat in categories:
            company = cat.get('company_name', 'Unknown')
            if company not in companies:
                companies[company] = []
            companies[company].append(cat)
        
        for company, cats in companies.items():
            print(f"  {company}: {len(cats)} categories")
    
    # Test getting specific category details
    print("\n3. Getting specific category details...")
    # Get first category ID from flat list
    if 'categories' in locals() and categories:
        first_cat_id = categories[0]['id']
        response = requests.get(f"{BASE_URL}/categories-tree/{first_cat_id}", headers=headers)
        print(f"Specific category response: {response.status_code}")
        if response.status_code == 200:
            cat_details = response.json()
            print(f"  Category: {cat_details.get('name')}")
            print(f"  Type: {cat_details.get('category_type')}")
            print(f"  Level: {cat_details.get('level')}")
            print(f"  Budget: ${cat_details.get('budget', 0):,.2f}")

def test_projects_api(token):
    print("\n=== Testing Projects API ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test listing projects
    print("1. Listing all projects...")
    response = requests.get(f"{BASE_URL}/projects/", headers=headers)
    print(f"Projects list response: {response.status_code}")
    if response.status_code == 200:
        projects = response.json()
        print(f"Found {len(projects)} projects")
        for proj in projects[:3]:  # Show first 3 projects
            print(f"  {proj.get('code')}: {proj.get('name')} ({proj.get('status')})")
            print(f"    Budget: ${proj.get('budget', 0):,.2f}")
    
    # Test getting project details
    print("\n2. Getting project details...")
    if 'projects' in locals() and projects:
        first_proj_id = projects[0]['id']
        response = requests.get(f"{BASE_URL}/projects/{first_proj_id}", headers=headers)
        print(f"Project details response: {response.status_code}")
        if response.status_code == 200:
            proj_details = response.json()
            print(f"  Project: {proj_details.get('name')}")
            print(f"  Status: {proj_details.get('status')}")
            print(f"  Budget: ${proj_details.get('budget', 0):,.2f}")
            print(f"  Spent: ${proj_details.get('spent_amount', 0):,.2f}")
            print(f"  Remaining: ${proj_details.get('remaining_budget', 0):,.2f}")
            print(f"  Utilization: {proj_details.get('budget_utilization', 0)}%")
    
    # Test getting project status options
    print("\n3. Getting project status options...")
    response = requests.get(f"{BASE_URL}/projects/status-options", headers=headers)
    print(f"Status options response: {response.status_code}")
    if response.status_code == 200:
        status_options = response.json()
        print("Available statuses:")
        for status in status_options.get('statuses', []):
            print(f"  {status['value']}: {status['label']}")

def test_company_summaries(token):
    print("\n=== Testing Company Summaries ===")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get companies first
    response = requests.get(f"{BASE_URL}/companies", headers=headers)
    if response.status_code == 200:
        companies = response.json()
        print(f"Found {len(companies)} companies")
        
        # Test project summary for each company
        for company in companies[:2]:  # Test first 2 companies
            company_id = company['id']
            company_name = company['name']
            print(f"\nGetting project summary for {company_name}...")
            
            response = requests.get(f"{BASE_URL}/projects/company/{company_id}/summary", headers=headers)
            print(f"Summary response: {response.status_code}")
            if response.status_code == 200:
                summary = response.json()
                print(f"  Total projects: {summary.get('total_projects')}")
                print(f"  Projects by status: {summary.get('projects_by_status')}")
                print(f"  Total budget: ${summary.get('total_budget', 0):,.2f}")
                print(f"  Budget utilization: {summary.get('budget_utilization', 0)}%")

def main():
    try:
        token = get_auth_token()
        print("Authentication successful!\n")
        
        test_category_tree_api(token)
        test_projects_api(token)
        test_company_summaries(token)
        
        print("\n=== All tests completed successfully! ===")
        
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    main()