import httpx
import time
import sys

BASE_URL = "http://localhost:8000"
PASSWORD = "NQp9RGMVFqpyDPxTkiOlgabYub7ybtOG"

def main():
    run_id = sys.argv[1]
    
    print("Logging in...")
    with httpx.Client(base_url=BASE_URL) as client:
        resp = client.post("/api/auth/token", data={"username": "admin", "password": PASSWORD})
        resp.raise_for_status()
        token = resp.json()["access_token"]
        
        client.headers["Authorization"] = f"Bearer {token}"
        
        print("Polling status...")
        last_log_offset = 0
        while True:
            try:
                resp = client.get(f"/api/runs/{run_id}")
                resp.raise_for_status()
                data = resp.json()
                status = data["status"]
                
                # fetch logs
                resp_logs = client.get(f"/api/runs/{run_id}/logs?limit=100&offset={last_log_offset}")
                if resp_logs.status_code == 200:
                    logs = resp_logs.json().get("logs", [])
                    for log in logs:
                        print(f"[{log.get('timestamp')}] {log.get('event_type')}: {log.get('message')}")
                    last_log_offset += len(logs)
                    
                if status in ("completed", "failed", "cancelled", "waiting_for_approval", "waiting_for_review"):
                    print(f"Run ended in state: {status}")
                    if status == "failed":
                        print("Error:", data.get("error"))
                    break
            except Exception as e:
                print(f"Error polling: {e}")
            
            time.sleep(5)

if __name__ == "__main__":
    main()
