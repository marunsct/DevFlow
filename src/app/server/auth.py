import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import bcrypt
from pydantic import BaseModel

# Secret key for JWT signing
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "super-secret-key-for-langchain-ui")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

# Database setup
DB_URL = os.environ.get("AUTH_DB_URL", "postgresql://postgres:postgres@db:5432/langchain_auth")

def get_db_connection():
    conn = psycopg2.connect(DB_URL)
    return conn

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                hashed_password TEXT NOT NULL,
                disabled BOOLEAN NOT NULL DEFAULT FALSE
            )
        ''')
        
        # Create default admin user if not exists
        c.execute("SELECT * FROM users WHERE username = 'admin'")
        if not c.fetchone():
            c.execute("INSERT INTO users (username, hashed_password, disabled) VALUES (%s, %s, %s)", 
                     ('admin', get_password_hash('admin'), False))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Warning: Could not initialize database: {e}")

# Initialize DB on module load
init_db()

auth_router = APIRouter()

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

def get_user(username: str) -> Optional[UserInDB]:
    try:
        conn = get_db_connection()
        c = conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT username, hashed_password, disabled FROM users WHERE username = %s", (username,))
        row = c.fetchone()
        conn.close()
        
        if row:
            return UserInDB(
                username=row['username'],
                hashed_password=row['hashed_password'],
                disabled=bool(row['disabled'])
            )
    except Exception as e:
        print(f"Error fetching user: {e}")
    return None

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = get_user(token_data.username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


@auth_router.post("/api/auth/token", response_model=Token, tags=["auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = get_user(form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@auth_router.get("/api/auth/me", response_model=User, tags=["auth"])
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user
