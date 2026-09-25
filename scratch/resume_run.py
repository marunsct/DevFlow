import requests
import json

base_url = "http://localhost:8000"
# Login
response = requests.post(f"{base_url}/api/auth/login", data={"username": "dev", "password": "dev"})
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Resume
res = requests.post(f"{base_url}/api/runs/run-badf8f7a-ffda-4844-8b16-762ad7c09950/resume", headers=headers)
print("Resumed:", res.status_code, res.text)
