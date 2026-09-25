import requests
import json

base_url = "http://localhost:8000"
login_data = {"username": "admin", "password": "NQp9RGMVFqpyDPxTkiOlgabYub7ybtOG"}
response = requests.post(f"{base_url}/api/auth/token", data=login_data)
if response.status_code == 200:
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{base_url}/api/runs/run-badf8f7a-ffda-4844-8b16-762ad7c09950", headers=headers)
    print("Run:", res.status_code, res.text)
else:
    print("Login failed:", response.status_code, response.text)
