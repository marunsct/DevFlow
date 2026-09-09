import pytest
from fastapi.testclient import TestClient
import os
import jwt
from datetime import timedelta

# We will need the app
from app.server.api import create_app
from app.server.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    SECRET_KEY,
    ALGORITHM,
    get_user,
    init_db
)

@pytest.fixture
def auth_client(test_db):
    # test_db is a fixture from conftest.py which sets up the database and calls init_db()
    # It also sets AUTH_DB_URL
    app = create_app()
    # We do NOT override get_current_active_user here because we want to test auth
    with TestClient(app) as c:
        yield c

def test_password_hashing():
    pwd = "my_secret_password"
    hashed = get_password_hash(pwd)
    assert verify_password(pwd, hashed)
    assert not verify_password("wrong_password", hashed)
    assert not verify_password(pwd, "bad_hash_format")

def test_create_access_token():
    token = create_access_token({"sub": "testuser"}, expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "testuser"
    assert "exp" in payload
    
    token_default = create_access_token({"sub": "testuser"})
    payload_default = jwt.decode(token_default, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload_default["sub"] == "testuser"

def test_login_success(auth_client, test_db):
    # init_db is called by test_db fixture, which creates 'admin' user with random or set password
    # For testing, let's just insert a test user using the DB URL
    import psycopg2
    
    conn = psycopg2.connect(os.environ["AUTH_DB_URL"])
    c = conn.cursor()
    c.execute("INSERT INTO users (username, hashed_password, disabled) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", 
              ("testuser", get_password_hash("testpass"), False))
    conn.commit()
    conn.close()

    response = auth_client.post(
        "/api/auth/token",
        data={"username": "testuser", "password": "testpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_failure_wrong_password(auth_client, test_db):
    import psycopg2
    conn = psycopg2.connect(os.environ["AUTH_DB_URL"])
    c = conn.cursor()
    c.execute("INSERT INTO users (username, hashed_password, disabled) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", 
              ("testuser2", get_password_hash("testpass"), False))
    conn.commit()
    conn.close()

    response = auth_client.post(
        "/api/auth/token",
        data={"username": "testuser2", "password": "wrongpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 401

def test_login_failure_no_user(auth_client):
    response = auth_client.post(
        "/api/auth/token",
        data={"username": "nonexistent", "password": "testpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 401

def test_read_users_me(auth_client, test_db):
    import psycopg2
    conn = psycopg2.connect(os.environ["AUTH_DB_URL"])
    c = conn.cursor()
    c.execute("INSERT INTO users (username, hashed_password, disabled) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", 
              ("testuser3", get_password_hash("testpass"), False))
    conn.commit()
    conn.close()
    
    # Get token
    token = create_access_token({"sub": "testuser3"})
    
    response = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser3"

def test_read_users_me_unauthorized(auth_client):
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 401

    response = auth_client.get("/api/auth/me", headers={"Authorization": "Bearer bad_token"})
    assert response.status_code == 401

def test_read_users_me_disabled(auth_client, test_db):
    import psycopg2
    conn = psycopg2.connect(os.environ["AUTH_DB_URL"])
    c = conn.cursor()
    c.execute("INSERT INTO users (username, hashed_password, disabled) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", 
              ("testuser4", get_password_hash("testpass"), True))
    conn.commit()
    conn.close()
    
    token = create_access_token({"sub": "testuser4"})
    
    response = auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403  # a disabled account is Forbidden, not a bad request
    assert response.json()["detail"] == "Inactive user"
