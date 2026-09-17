import requests
import json
import os

token_res = requests.post("http://127.0.0.1:8000/api/auth/token", data={"username": "admin", "password": "NQp9RGMVFqpyDPxTkiOlgabYub7ybtOG"})
token = token_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

url_create = "http://127.0.0.1:8000/api/runs"
files = {'files': open('tests/brief_low.md', 'rb')}
data = {'repo_root': '/app/data'}

res = requests.post(url_create, headers=headers, files=files, data=data)
if res.status_code not in (200, 201):
    print("Create failed", res.status_code, res.text)
    exit(1)

run_id = res.json()["run_id"]
print("Created run:", run_id)

url_start = f"http://127.0.0.1:8000/api/runs/{run_id}/start"
body = {
    "review_policy": {
        "specification": False,
        "sprint": False
    },
    "auto_approve": True
}
res2 = requests.post(url_start, headers=headers, json=body)
if res2.status_code not in (200, 202):
    print("Start failed", res2.status_code, res2.text)
    exit(1)

print("Started run successfully.")
