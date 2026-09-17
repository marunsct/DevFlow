import requests
import json
import os

token_res = requests.post("http://127.0.0.1:8000/api/auth/token", data={"username": "admin", "password": "NQp9RGMVFqpyDPxTkiOlgabYub7ybtOG"})
token = token_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

url = "http://127.0.0.1:8000/api/runs/run-000c53d9-9d37-4bc5-9f9f-f4d5e07b7bb9/logs?limit=500"
res = requests.get(url, headers=headers)
print(json.dumps(res.json(), indent=2))
