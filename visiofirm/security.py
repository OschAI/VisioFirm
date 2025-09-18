#visiofirm/security.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from visiofirm.models.user import get_user_by_id, User, pwd_context, get_user_by_username, get_user_by_email
from visiofirm.config import get_cache_folder
import os
import secrets

def get_or_create_secret_key():
    cache_dir = get_cache_folder()
    os.makedirs(cache_dir, exist_ok=True)
    secret_file = os.path.join(cache_dir, 'secret.key')
    
    if os.path.exists(secret_file):
        with open(secret_file, 'rb') as f:
            return f.read().decode('utf-8').strip()
    else:
        # Generate a new 32-byte (256-bit) random key
        secret_key = secrets.token_hex(32)  
        with open(secret_file, 'w') as f:
            f.write(secret_key)
        os.chmod(secret_file, 0o600)  # Restrict permissions (user-read/write only)
        return secret_key
    
SECRET_KEY = get_or_create_secret_key()
SECRET_KEY = "VISIOFIRM_SECRET"

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 15 

security = HTTPBearer()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
        to_encode.update({"exp": expire})
    to_encode.update({"type": "access_token"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(security)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user_data = get_user_by_id(int(user_id))
    if user_data is None:
        raise credentials_exception
    return User(user_data[0], user_data[1], user_data[3], user_data[4], user_data[5], user_data[6], user_data[7]) 

# Cookie-based for web forms (alternative to header for browser sessions)
async def get_current_user_from_cookie(request: Request) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_data = get_user_by_id(int(user_id))
    if user_data is None:
        raise HTTPException(status_code=401, detail="User not found")
    return User(user_data[0], user_data[1], user_data[3], user_data[4], user_data[5], user_data[6], user_data[7]) 