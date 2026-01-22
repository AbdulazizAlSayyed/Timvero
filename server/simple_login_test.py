import requests
import json

# Test login
login_data = {
    "username": "admin",
    "password": "admin123"  # Using the default password from the system
}

response = requests.post("http://127.0.0.1:8000/auth/login", json=login_data)
print("Login response:", response.status_code)
print("Login content:", response.text)

if response.status_code == 200:
    token = response.json().get("token")
    print("Token:", token)
    
    # Test a report endpoint
    headers = {"Authorization": f"Bearer {token}"}
    report_response = requests.get("http://127.0.0.1:8000/reports/allocation", 
                                   headers=headers, 
                                   params={"year": 2026, "month": 1})
    print("Report response:", report_response.status_code)
    print("Report content (first 500 chars):", report_response.text[:500])
else:
    print("Login failed, checking if user exists...")
    # Try to get all app users to see what users exist
    try:
        users_response = requests.get("http://127.0.0.1:8000/users")  # This might not exist
        print("Users response:", users_response.status_code, users_response.text)
    except:
        print("Could not access users endpoint")