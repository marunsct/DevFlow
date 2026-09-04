import time
import requests
import json
import os

BASE_URL = "http://localhost:8000/api"

def run_e2e_test():
    print("Starting E2E test...")
    
    # 1. Create a dummy file for upload
    with open("test_product.md", "w") as f:
        f.write("# Test Product Intake\n\nThis is a test product requirement document.")
        
    print("Authenticating...")
    login_data = {"username": "admin", "password": "admin"}
    token_resp = requests.post(f"{BASE_URL}/auth/token", data=login_data)
    if token_resp.status_code != 200:
        print(f"Failed to authenticate: {token_resp.text}")
        return
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Upload file and create run
    print("Creating run...")
    with open("test_product.md", "rb") as f:
        files = {"files": ("test_product.md", f, "text/markdown")}
        response = requests.post(f"{BASE_URL}/runs", files=files, headers=headers)
        
    if response.status_code != 201:
        print(f"Failed to create run: {response.text}")
        return
        
    data = response.json()
    run_id = data["run_id"]
    print(f"Run created with ID: {run_id}")
    
    # 3. Start run
    print("Starting run...")
    start_payload = {
        "review_policy": {},
        "artifact_directory": "/home/arun/Desktop/langchain",
        "allow_subdirectories": True,
        "auto_approve": True
    }
    response = requests.post(f"{BASE_URL}/runs/{run_id}/start", json=start_payload, headers=headers)
    if response.status_code != 202:
        print(f"Failed to start run: {response.text}")
        return
        
    print("Run started. Polling status...")
    
    # 4. Poll status
    max_retries = 60
    for i in range(max_retries):
        time.sleep(2)
        response = requests.get(f"{BASE_URL}/runs/{run_id}", headers=headers)
        if response.status_code != 200:
            print(f"Failed to get run status: {response.text}")
            continue
            
        status_data = response.json()
        status = status_data["status"]
        current_stage = status_data.get("current_stage")
        
        print(f"Status: {status} | Stage: {current_stage}")
        
        if status == "waiting_for_review":
            print("Run is waiting for review. Fetching pending review...")
            review_resp = requests.get(f"{BASE_URL}/runs/{run_id}/review", headers=headers)
            print("Pending review:", review_resp.json())
            
            # Submit review decision (approve)
            print("Submitting review decision (approve)...")
            review_payload = {"action": "approve", "comment": "Looks good from E2E test."}
            # The API expects form data
            requests.post(f"{BASE_URL}/runs/{run_id}/review", data=review_payload, headers=headers)
            time.sleep(2)
            
        elif status == "waiting_for_approval":
            print("Run is waiting for approval. Fetching pending approval...")
            approval_resp = requests.get(f"{BASE_URL}/runs/{run_id}/approval", headers=headers)
            print("Pending approval:", approval_resp.json())
            
            # Submit approval decision (approve)
            print("Submitting approval decision (approve)...")
            approval_payload = {"action": "approve", "reason": "Approved by E2E test."}
            requests.post(f"{BASE_URL}/runs/{run_id}/approval", json=approval_payload, headers=headers)
            time.sleep(2)
            
        elif status in ("completed", "failed", "cancelled"):
            print(f"Run finished with status: {status}")
            break
            
    print("Fetching final artifacts...")
    artifacts_resp = requests.get(f"{BASE_URL}/runs/{run_id}/artifacts", headers=headers)
    print("Final artifacts:", artifacts_resp.json())
    
    # Cleanup
    if os.path.exists("test_product.md"):
        os.remove("test_product.md")
        
    print("E2E test completed.")

if __name__ == "__main__":
    run_e2e_test()
